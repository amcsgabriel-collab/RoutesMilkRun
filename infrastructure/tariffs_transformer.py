import pandas as pd

from settings import TARIFFS_COLUMNS_DIRECT, TARIFFS_COLUMNS_HUB, TARIFFS_COLUMNS_LTL


class TariffsTransformer:
    def __init__(self, tariffs_dataframe):
        self.tariffs_dataframe = tariffs_dataframe
        self.transformed_tariffs = None
        self.filtered_tariffs = None

    def transform_tariffs(self, tariffs_type, plant_cofor: str = None, hubs: list[str] = None):
        self.transformed_tariffs = self.tariffs_dataframe.copy()
        self.filter_itms_mode(tariffs_type)
        self.filter_relevant_columns(tariffs_type)
        self.rename_tariffs_columns(tariffs_type)
        self.split_tariffs_key()
        self.filter_tariffs(tariffs_type, hubs=hubs, plant_cofor=plant_cofor)
        if tariffs_type == 'ftl':
            self.melt_tariffs_deviation_bucket()
            self.melt_tariffs_trip_type()
            self.filter_st_only()
        else:
            self.melt_tariffs_chargeable_weight(tariffs_type)
        return self.filtered_tariffs

    def filter_itms_mode(self, tariffs_type):
        itms_mode = "FTL / MR" if tariffs_type == 'ftl' else "LTL / GRP / HUB"
        self.transformed_tariffs = self.transformed_tariffs[self.transformed_tariffs['iTMS_Mode'] == itms_mode]

    def filter_relevant_columns(self, tariffs_type):
        if tariffs_type == 'ftl':
            source = TARIFFS_COLUMNS_DIRECT
        elif tariffs_type == 'ltl':
            source = TARIFFS_COLUMNS_LTL
        elif tariffs_type == 'hub':
            source = TARIFFS_COLUMNS_HUB
        else:
            raise ValueError(f"Unexpected Tariff Type: {tariffs_type}.")

        columns = [c['raw'] for c in source]
        self.transformed_tariffs = self.transformed_tariffs[columns]

    def rename_tariffs_columns(self, tariffs_type):
        if tariffs_type == 'ftl':
            source = TARIFFS_COLUMNS_DIRECT
        elif tariffs_type == 'ltl':
            source = TARIFFS_COLUMNS_LTL
        elif tariffs_type == 'hub':
            source = TARIFFS_COLUMNS_HUB
        else:
            raise ValueError(f"Unexpected Tariff Type: {tariffs_type}.")

        self.transformed_tariffs = self.transformed_tariffs.rename(
            columns={c['raw']: c['final'] for c in source}
        )

    def split_tariffs_key(self):

        parts = self.transformed_tariffs["Tariff Key"].str.split("---")
        parts = parts.apply(lambda x: [p.strip() for p in x] if isinstance(x, list) else x)

        part_count = parts.str.len()

        self.transformed_tariffs["Carrier Short Name"] = parts.str[0]
        self.transformed_tariffs["Destination COFOR"] = parts.str[-1]
        self.transformed_tariffs["Origin Code"] = parts.str[-2]

        self.transformed_tariffs["Means of Transport"] = None

        mask_4 = part_count == 4
        mask_5 = part_count == 5

        self.transformed_tariffs.loc[mask_4, "Means of Transport"] = parts[mask_4].str[1]
        self.transformed_tariffs.loc[mask_5, "Means of Transport"] = parts[mask_5].str[2]

        invalid = ~part_count.isin([3, 4, 5])
        if invalid.any():
            bad_counts = sorted(part_count[invalid].unique().tolist())
            raise ValueError(f"Unexpected Tariff Key format with parts counts: {bad_counts}")

        self.transformed_tariffs = self.transformed_tariffs.drop(columns=["Tariff Key"])

    def filter_tariffs(self, tariffs_type, plant_cofor=None, hubs=None):
        if tariffs_type == 'ftl':
            filter_array = self.transformed_tariffs['Destination COFOR'].eq(plant_cofor)
        else:
            filter_array = self.transformed_tariffs['Destination COFOR'].isin(hubs)

        self.filtered_tariffs = self.transformed_tariffs.loc[filter_array]

    def melt_tariffs_deviation_bucket(self):
        self.filtered_tariffs = self.filtered_tariffs.melt(
            id_vars=[
                'Carrier Short Name',
                'Means of Transport',
                'Origin Code',
                'Destination COFOR',
                'iTMS Mode',
                'ST',
                'RT',
                'Currency'
            ],
            value_vars=[
                'Small (0-30km)',
                'Low (30-50 km)',
                'Medium (50-100km)',
                'High (100-150km)',
                '>150km'
            ],
            var_name='Deviation Bucket',
            value_name='Stop Cost'
        )

    def melt_tariffs_trip_type(self):
        self.filtered_tariffs = self.filtered_tariffs.melt(
            id_vars=[
                'Carrier Short Name',
                'Means of Transport',
                'Origin Code',
                'Destination COFOR',
                'iTMS Mode',
                'Deviation Bucket',
                'Currency',
                'Stop Cost'
            ],
            value_vars=[
                'ST',
                'RT',
            ],
            var_name='Trip Type',
            value_name='Base Cost'
        )

    def filter_st_only(self):
        self.filtered_tariffs = self.filtered_tariffs[self.filtered_tariffs['Trip Type'] == 'ST']

    def melt_tariffs_chargeable_weight(self, tariffs_type: str):
        if tariffs_type == 'ltl':
            value_vars = [
                '<=200_LTL',
                '<=600_LTL',
                '<=1000_LTL',
                '<=2000_LTL',
                '<=4000_LTL',
                '<=10000_LTL',
                '<=15000_LTL',
                '<=20000_LTL',
                '<=25000_LTL',
                '>25000_LTL'
            ]
        elif tariffs_type == 'hub':
            value_vars = [
                '<=3000_HUB',
                '<=5000_HUB',
                '<=7000_HUB',
                '<=10000_HUB',
                '<=15000_HUB',
                '<=20000_HUB',
                '>20000_HUB'
            ]
        else:
            raise ValueError(f"Unexpected Tariffs type: {tariffs_type.upper()}.")

        self.filtered_tariffs = self.filtered_tariffs.melt(
            id_vars=[
                'Carrier Short Name',
                'Means of Transport',
                'Origin Code',
                'Destination COFOR',
                'iTMS Mode',
                'Currency',
                'Min Price',
                'Max Price',
            ],
            value_vars=value_vars,
            var_name='Chargeable Weight Bracket',
            value_name='Cost per 100kg'
        )
