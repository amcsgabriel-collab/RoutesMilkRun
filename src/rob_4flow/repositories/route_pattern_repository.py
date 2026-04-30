import pandas as pd

from ..domain.data_structures import Plant
from ..domain.routes.route_pattern import RoutePattern
from ..domain.shipper import Shipper


class RoutePatternRepository:
    def __init__(self, df: pd.DataFrame, distance_function):
        self._df = df
        self._distance_function = distance_function

    def get_all(
        self,
        shippers_by_cofor: dict[str, Shipper],
        plant: Plant,
    ) -> dict[str, set[RoutePattern]]:

        patterns_by_vehicle: dict[str, set[RoutePattern]] = {}
        for route_name, group in self._df.groupby("Route name"):
            vehicle_id = group["Means of Transport"].iloc[0]
            flow_direction = group['Parts or Empties'].iloc[0]
            shippers = {
                shippers_by_cofor[row["Shipper COFOR"]]
                for _, row in group.iterrows()
                if row["Shipper COFOR"] in shippers_by_cofor
            }
            if not shippers:
                continue
            pattern = RoutePattern(
                shippers=shippers,
                plant=plant,
                route_name=route_name,
                tour=group['Tour name'].iloc[0],
                flow_direction="parts" if flow_direction == "P" else "empties",
            )

            shipper_route_weight = (
                self._df[self._df["Parts or Empties"] == flow_direction]
                .groupby(["Shipper COFOR", "Route name"])["Avg. Weight / week"]
                .sum()
            )

            shipper_total_weight = shipper_route_weight.groupby(level=0).sum()

            for shipper in shippers:
                route_weight = shipper_route_weight.get(
                    (shipper.cofor, pattern.route_name),
                    0.0,
                )
                total_weight = shipper_total_weight.get(shipper.cofor, 0.0)

                pattern.shipper_allocation[shipper] = (
                    float(route_weight) / float(total_weight)
                    if total_weight
                    else 0.0
                )

            pattern.order_shippers(self._distance_function)
            pattern.calculate_deviation(self._distance_function)

            patterns_by_vehicle.setdefault(vehicle_id, set()).add(pattern)

        return patterns_by_vehicle
