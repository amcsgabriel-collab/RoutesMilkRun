import copy

import pandas as pd

from domain.routes.direct_route import DirectRoute
from domain.routes.route import Route
from domain.shipper import Shipper


class Trip:
    def __init__(
            self,
            parts_route: DirectRoute | None,
            empties_route: DirectRoute | None,
            frequency: int,
            roundtrip_id: int | None = None,
            name: str | None = None,
    ):
        self.name = name
        self.parts_route = parts_route
        self.empties_route = empties_route
        self.frequency = frequency
        self.roundtrip_id = roundtrip_id
        self.tariff = None

    def _key(self):
        return (
            self.parts_route.demand.pattern if self.parts_route else None,
            self.empties_route.demand.pattern if self.empties_route else None,
            self.frequency,
            self.roundtrip_id,
            self.name
        )

    def __eq__(self, other):
        if not isinstance(other, Trip):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def copy(self):
        return copy.deepcopy(self)

    def get_all_shippers(self) -> list[Shipper]:
        return ([s for s in self.parts_route.demand.pattern.shippers] +
                [s for s in self.empties_route.demand.pattern.shippers])

    @property
    def is_roundtrip(self) -> bool:
        return self.parts_route is not None and self.empties_route is not None

    @property
    def is_empty(self) -> bool:
        return self.parts_route is None and self.empties_route is None

    def select_direction(self, flow_direction):
        return self.parts_route if flow_direction == "parts" else self.empties_route

    def route_allocation(self, flow_direction) -> float:
        route = self.select_direction(flow_direction)
        return min(self.frequency / route.frequency, 1) if route and route.frequency else 0

    @property
    def classification(self):
        if self.is_roundtrip:
            return "R"
        elif not self.is_empty:
            return "S"
        else:
            return "N/D"

    def _build_route_key(self, route: Route) -> str:
        prefix = route.demand.pattern.mr_cluster if route.demand.pattern.transport_concept == "MR" else "FT"
        route_name = route.demand.pattern.get_name(self.roundtrip_id) \
            if route.demand.pattern.is_new_pattern \
            else route.demand.pattern.route_name.split("/")[0]
        suffix = f"#{route.demand.flow_direction}{self.classification}"
        return f"{prefix}_{route_name}{suffix}"

    def export_dataframe(self) -> pd.DataFrame:
        frames = []
        if self.parts_route is not None:
            frames.append(
                self.parts_route.export_dataframe(
                    tour_name=self._build_route_key(self.parts_route),
                    roundtrip_id=self.roundtrip_id,
                    frequency=self.frequency,
                )
            )
        if self.empties_route is not None:
            frames.append(
                self.empties_route.export_dataframe(
                    tour_name=self._build_route_key(self.empties_route),
                    roundtrip_id=self.roundtrip_id,
                    frequency=self.frequency,
                )
            )
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @property
    def total_cost(self):
        parts_cost = self.parts_route.get_total_cost(is_roundtrip=self.is_roundtrip) if self.parts_route else 0
        empties_cost = self.empties_route.get_total_cost(is_roundtrip=self.is_roundtrip) if self.empties_route else 0
        return parts_cost + empties_cost

    @property
    def summary(self):
        return {
            "roundtrip_id": self.roundtrip_id,
            "frequency": self.frequency,
            "parts_route": self.parts_route.summary(self.is_roundtrip) if self.parts_route else None,
            "empties_route": self.empties_route.summary(self.is_roundtrip) if self.empties_route else None,
        }

    def export_table(self, trip_id_number):
        rows = []

        def add_route_rows(route: DirectRoute | None):
            if route is None:
                return

            shippers = list(route.demand.pattern.shippers)
            if not shippers:
                return

            for shipper in shippers:
                demand = shipper.parts_demand if route.demand.flow_direction == "parts" else shipper.empties_demand

                rows.append({
                    "trip_unique_number": trip_id_number,
                    "roundtrip_id": self.roundtrip_id,
                    "trip_classification": self.classification,
                    "flow_direction": route.demand.flow_direction,
                    "transport_concept": route.demand.pattern.transport_concept,
                    "route_name": route.demand.pattern.route_name,
                    "shipper": shipper.cofor,
                    "route_shipper_allocation": route.demand.pattern.shipper_allocation[shipper],
                    "weight": demand.weight,
                    "volume": demand.volume,
                    "loading_meters": demand.loading_meters,
                    "route_weight": route.demand.weight,
                    "route_volume": route.demand.volume,
                    "route_loading_meters": route.demand.loading_meters,
                    "trip_weight": route.demand.weight * self.route_allocation(route.demand.flow_direction),
                    "trip_volume": route.demand.volume * self.route_allocation(route.demand.flow_direction),
                    "trip_loading_meters": route.demand.loading_meters * self.route_allocation(route.demand.flow_direction),
                    "trip_frequency": self.frequency,
                    "route_frequency": route.frequency,
                    "allocation": self.route_allocation(flow_direction=route.demand.flow_direction),
                })

        add_route_rows(self.parts_route)
        add_route_rows(self.empties_route)

        return pd.DataFrame(rows)
