import pandas as pd

from ..domain.data_structures import Vehicle


class VehicleRepository:
    def __init__(
            self,
            vehicles_df: pd.DataFrame
    ) -> None:
        self.vehicles_df = vehicles_df

    def extract_vehicles(self) -> dict[str, Vehicle]:
        return {
            row['Name']:
            Vehicle(
                id=row['Name'],
                weight_capacity=row['Max weight'],
                volume_capacity=row['Max volume'],
                loading_meters_capacity=row['Max Ldm'],
            )  for _, row in self.vehicles_df.iterrows()
        }