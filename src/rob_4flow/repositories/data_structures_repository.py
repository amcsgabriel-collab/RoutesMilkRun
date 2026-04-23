# repositories/base_repository.py
import pandas as pd

from ..domain.data_structures import Plant, Carrier, Seller


class PlantRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_plant(self) -> Plant:
        row = self._df.iloc[0]
        return Plant(
            cofor=row["Plant COFOR"],
            name=row["Plant Name"],
            # zip=row["Plant Zip"],
            coordinates=(row["Plant Latitude"], row["Plant Longitude"]),
        )


class CarrierRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def _get_carriers(self, prefix: str = "") -> dict[str, Carrier]:
        prefix = f"{prefix} " if prefix else ""

        return {
            row[f"{prefix}Carrier ID"]: Carrier(
                cofor=row[f"{prefix}Carrier COFOR"],
                id=row[f"{prefix}Carrier ID"],
                name=row[f"{prefix}Carrier Name"],
                group=row[f"{prefix}Carrier Short Name"],
            )
            for _, row in self._df.drop_duplicates(f"{prefix}Carrier ID").iterrows()
        }

    def get_all(self) -> dict[str, Carrier]:
        return self._get_carriers()

    def get_all_hub(self) -> dict[str, dict[str, Carrier]]:
        return {'first_leg': self._get_carriers("First Leg"),
                'linehaul': self._get_carriers("Linehaul")}


class SellerRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_by_shipper(self) -> dict[str, list[Seller]]:
        """Returns a dict keyed by shipper COFOR for easy lookup downstream."""
        sellers: dict[str, set[Seller]] = {}
        for _, row in self._df.iterrows():
            seller = Seller(
                cofor=row["Seller COFOR"],
                name=row["SELLER NAME"],
                zip=row["SELLER ZIP CODE"],
                city=row["SELLER CITY"],
                country=row["SELLER COUNTRY"],
                docks=row["Docks (,)"]
            )
            sellers.setdefault(row["Shipper COFOR"], set()).add(seller)
        return sellers

