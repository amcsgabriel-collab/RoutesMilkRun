from typing import Literal

import pandas as pd

from ..domain.data_structures import Carrier, Seller
from ..domain.demand import Demand
from ..domain.shipper import Shipper


class ShipperRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_all(
        self,
        carriers: dict[str, Carrier],
        sellers_by_shipper: dict[str, list[Seller]],
        are_hub_shippers: bool = False,
    ) -> dict[str, Shipper]:
        shippers: dict[str, Shipper] = {}

        for cofor, group in self._df.groupby("Shipper COFOR"):
            first_row = group.iloc[0]
            original_network = "hub" if "HUB COFOR" in group.columns else "direct"
            sellers = sellers_by_shipper.get(cofor, [])

            parts_row = group[group["Parts or Empties"] == "P"]
            empties_row = group[group["Parts or Empties"] == "E"]

            def build_demand(row_df: pd.DataFrame, demand_type: Literal["P", "E"]) -> Demand:
                if row_df.empty:
                    return Demand(
                        weight=0.0,
                        volume=0.0,
                        loading_meters=0.0,
                        sellers=[],
                        type=demand_type,
                        original_network=original_network,
                    )

                row = row_df.iloc[0]
                return Demand(
                    weight=row["Avg. Weight / week"],
                    volume=row["Avg. Volume / week"],
                    loading_meters=row["Avg. Loading Meters / week"],
                    sellers=sellers,
                    type=demand_type,
                    original_network=original_network,
                )

            shippers[cofor] = Shipper(
                cofor=cofor,
                name=first_row["SHIPPER NAME"],
                original_network=original_network,
                zip_code=first_row["SHIPPER  ZIP CODE"],
                city=first_row["SHIPPER CITY"],
                street=first_row["SHIPPER STREET"],
                country=first_row["SHIPPER COUNTRY"],
                sourcing_region=first_row["SHIPPER SOURCING REGION"],
                parts_demand=build_demand(parts_row, "P"),
                empties_demand=build_demand(empties_row, "E"),
                carrier=carriers[
                    first_row["First Leg Carrier ID"] if are_hub_shippers else first_row["Carrier ID"]
                ],
                coordinates=(first_row["Latitude"], first_row["Longitude"]),
            )

        return shippers