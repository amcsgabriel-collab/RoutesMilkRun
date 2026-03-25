import pandas as pd

from domain.data_structures import Carrier, Seller
from domain.shipper import Shipper


class ShipperRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_all(
        self,
        carriers: dict[str, Carrier],
        sellers_by_shipper: dict[str, list[Seller]],
        hub_shippers: bool = False
    ) -> dict[str, Shipper]:
        return {
            row["Shipper COFOR"]: Shipper(
                cofor=row["Shipper COFOR"],
                name=row["SHIPPER NAME"],
                original_network='hub' if "HUB COFOR" in row else 'direct',
                zip_code=row["SHIPPER  ZIP CODE"],
                city=row["SHIPPER CITY"],
                street=row["SHIPPER STREET"],
                country=row["SHIPPER COUNTRY"],
                sourcing_region=row["SHIPPER SOURCING REGION"],
                weight=row["Avg. Weight / week"],
                volume=row["Avg. Volume / week"],
                loading_meters=row["Avg. Loading Meters / week"],
                carrier=carriers[row["First Leg Carrier ID"] if hub_shippers else row["Carrier ID"] ],
                sellers=sellers_by_shipper.get(row["Shipper COFOR"], []),
                coordinates=(row["Latitude"], row["Longitude"]),
            )
            for _, row in self._df.iterrows()
        }