import pandas as pd

from domain.exceptions import MissingHelperDataError, CarriersNotInHelperError


class DemandDataTransformer:
    def __init__(self,
                 demand_database: pd.DataFrame,
                 carrier_helper: pd.DataFrame | None = None,
                 plant_name_helper: pd.DataFrame | None = None,
                 locations: pd.DataFrame | None = None,
                 is_hub_database:bool = False
                 ) -> None:

        self.aggregated_database = None
        self.database = demand_database
        self.carrier_helper = carrier_helper
        self.plant_name_helper = plant_name_helper
        self.locations = locations
        self.is_hub_database = is_hub_database

    def transform_database(self):

        if self.carrier_helper is None or self.plant_name_helper is None or self.locations is None:
            raise MissingHelperDataError()
        self.add_plant_name()
        self.add_plant_coordinates()
        self.add_shipper_coordinates()
        if self.is_hub_database:
            self.add_hub_location_data()
            self.split_linehaul_first_leg_columns()
        self.add_carrier_consolidated_name()
        self.filter_parts_only()
        return self.database

    def split_linehaul_first_leg_columns(self):

        def split_column(column: str) -> pd.Series:
            return self.database[column].astype(str).str.split(" / ")

        def create_linehaul_first_leg_columns(original_col_name):
            first_leg_col_name = f"First Leg {original_col_name}"
            linehaul_col_name = f"Linehaul {original_col_name}"

            split = split_column(original_col_name)
            self.database[first_leg_col_name] = split.str[0]
            self.database[linehaul_col_name] = split.str[1]

        columns = ['Means of Transport', 'Transport concept', 'Carrier ID', 'Carrier COFOR', 'Carrier Name']
        for col in columns:
            print(col)
            create_linehaul_first_leg_columns(col)


    def add_carrier_consolidated_name(self):

        def get_carrier_short_name(prefix: str = None):
            adj_prefix = f"{prefix} " if prefix else ""
            id_column = f"{adj_prefix}Carrier ID"

            missing_carriers = (
                set(self.database[id_column].unique())
                .difference(self.carrier_helper["Carrier ID Helper"].unique())
            )
            if missing_carriers:
                raise CarriersNotInHelperError(missing_carriers)

            carrier_helper = self.carrier_helper.copy()
            carrier_helper.rename(columns={'Carrier Short Name': f"{adj_prefix}Carrier Short Name"}, inplace=True)
            self.database = self.database.merge(
                carrier_helper,
                how="left",
                left_on=id_column,
                right_on = "Carrier ID Helper",
            )

        if self.is_hub_database:
            get_carrier_short_name("First Leg")
            get_carrier_short_name("Linehaul")
        else:
            self.database.rename(columns={"Carrier name": "Carrier Name"}, inplace=True)
            get_carrier_short_name()


    def add_plant_name(self):
        self.database = self.database.merge(
            self.plant_name_helper,
            how="left",
            on="Plant COFOR"
        )

    def add_plant_coordinates(self):
        locations = self.locations.copy()
        locations = locations[['Key', 'Latitude', 'Longitude']]
        locations.columns = ['Plant COFOR', 'Plant Latitude', 'Plant Longitude']
        self.database = self.database.merge(
            locations,
            how="left",
            on="Plant COFOR",
        )

    def add_shipper_coordinates(self):
        locations = self.locations.copy()
        locations = locations[['Key', 'Latitude', 'Longitude']]
        locations.columns = ['Shipper COFOR', 'Latitude', 'Longitude']
        self.database = self.database.merge(
            locations,
            how="left",
            on="Shipper COFOR"
        )

    def add_hub_location_data(self):
        locations = self.locations.copy()
        locations.rename(columns={
            'Key': 'HUB COFOR',
            'Latitude': 'Hub Latitude',
            'Longitude': 'Hub Longitude',
            'ZIP Code': 'Hub Zip Code',
            'Country': 'Hub Country'},
            inplace=True
        )
        locations['Hub Country'] = locations['Hub Country'].str.split(" ").str[0]
        self.database = self.database.merge(
            locations,
            how="left",
            on="HUB COFOR"
        )
        locations.to_csv('hub_zip_codes.csv')

    def filter_parts_only(self):
        self.database = self.database[self.database['Parts or Empties'] == 'P'] #TODO: Remove once empties implemented.

    def aggregate_database_by_shipper(self):
        key = ['Shipper COFOR']
        self.aggregated_database = (
            self.database
            .groupby(key, as_index=False)
            .agg(self.make_aggregation_dict(key))
        )
        return self.aggregated_database

    def make_aggregation_dict(
            self,
             key
    ) -> dict:
        agg_dict = {
            'Avg. Volume / week': "sum",
            'Avg. Weight / week': "sum",
            'Avg. Loading Meters / week': "sum"
        }
        # Automatically keep all other columns (first occurrence)
        non_seller_cols = [
            column for column in self.database.columns
            if column not in agg_dict
               and column not in key
        ]
        for col in non_seller_cols:
            agg_dict[col] = "first"
        return agg_dict


    def export_database(self):
        pass

    def aggregated_database_by_route(self):
        key = ['Route name', 'Shipper COFOR']
        self.aggregated_database = (
            self.database
            .groupby(key, as_index=False)
            .agg(self.make_aggregation_dict(key))
        )
        return self.aggregated_database