import pandas as pd

from domain.data_structures import Carrier, Vehicle, Plant
from domain.hub import Hub
from domain.shipper import Shipper


class HubRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_all(
        self,
        carriers: dict[str, dict[str, Carrier]],
        shippers: dict[str, Shipper],
        vehicles: dict[str, Vehicle],
        plant: Plant,
    ) -> set[Hub]:
        return {
            Hub(
                route=group["Route name"].iloc[0],
                cofor=hub_cofor,
                name=group["HUB name"].iloc[0],
                country=group["Hub Country"].iloc[0],
                zip_code=group["Hub Zip Code"].iloc[0],
                plant=plant,
                shippers=[
                    s
                    for cofor, s in shippers.items()
                    if cofor in group["Shipper COFOR"].tolist()
                ],
                first_leg_carrier=carriers["first_leg"][group["First Leg Carrier ID"].iloc[0]],
                first_leg_vehicle=vehicles[group["First Leg Means of Transport"].iloc[0]],
                linehaul_carrier=carriers["linehaul"].get(group["Linehaul Carrier ID"].iloc[0]),
                linehaul_vehicle=vehicles[group["Linehaul Means of Transport"].iloc[0]],
                linehaul_transport_concept=group["Linehaul Transport concept"].iloc[0],
                coordinates=(group["Hub Latitude"].iloc[0], group["Hub Longitude"].iloc[0]),
                has_empties_flow=self._has_empties_flow(group),
            )
            for hub_cofor, group in self._df.groupby("HUB COFOR", sort=False)
        }

    @staticmethod
    def _has_empties_flow(group: pd.DataFrame) -> bool:
        return (
            "Parts or Empties" in group.columns
            and (group["Parts or Empties"] == "E").any()
        )
