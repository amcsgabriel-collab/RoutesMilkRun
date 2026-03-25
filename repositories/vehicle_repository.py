import pandas as pd

from domain.data_structures import Vehicle


class VehicleRepository:
    def __init__(
            self,
            vehicles_df: pd.DataFrame
    ) -> None:
        self.vehicles_df = vehicles_df

    def extract_vehicles(self) -> dict[str, Vehicle]:
        return {
            row['id']:
            Vehicle(
                id=row['id'],
                weight_capacity=row['weight'],
                volume_capacity=row['volume'],
                loading_meters_capacity=row['loading meters'],
            )  for _, row in self.vehicles_df.iterrows()
        }