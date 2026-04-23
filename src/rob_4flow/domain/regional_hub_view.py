from dataclasses import dataclass
from typing import Protocol

from .hub import Hub
from .kpi_set import KPISet


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0

class HubLike(Protocol):
    cofor: str
    shippers: set
    has_empties_flow: bool

    @property
    def parts_first_leg_routes(self): ...
    @property
    def empties_first_leg_routes(self): ...
    @property
    def parts_linehaul_route(self): ...
    @property
    def empties_linehaul_route(self): ...


@dataclass(frozen=True)
class RegionalHubView:
    core_hub: Hub
    region: str

    @property
    def coordinates(self):
        return self.core_hub.coordinates

    @property
    def plant(self):
        return self.core_hub.plant

    @property
    def formatted_coordinates(self):
        return self.core_hub.formatted_coordinates

    @property
    def cofor(self) -> str:
        return self.core_hub.cofor

    @property
    def name(self):
        return getattr(self.core_hub, "name", self.core_hub.cofor)

    @property
    def has_empties_flow(self) -> bool:
        return self.core_hub.has_empties_flow

    @property
    def summary(self):
        return self.core_hub.summary

    @property
    def shippers(self):
        return {
            shipper
            for shipper in self.core_hub.shippers
            if getattr(shipper, "sourcing_region", None) == self.region
        }

    @property
    def parts_shippers(self):
        return {
            s for s in self.shippers
            if (
                s.parts_demand.weight != 0.0
                or s.parts_demand.volume != 0.0
                or s.parts_demand.loading_meters != 0.0
            )
        }

    @property
    def empties_shippers(self):
        return {
            s for s in self.shippers
            if (
                s.empties_demand.weight != 0.0
                or s.empties_demand.volume != 0.0
                or s.empties_demand.loading_meters != 0.0
            )
        }

    @property
    def parts_first_leg_routes(self):
        return {
            route
            for route in self.core_hub.parts_first_leg_routes
            if route.demand.starting_point in self.parts_shippers
        }

    @property
    def empties_first_leg_routes(self):
        if not self.has_empties_flow:
            return set()
        return {
            route
            for route in self.core_hub.empties_first_leg_routes
            if route.demand.starting_point in self.empties_shippers
        }

    @property
    def parts_linehaul_route(self):
        return self.core_hub.parts_linehaul_route

    @property
    def empties_linehaul_route(self):
        return self.core_hub.empties_linehaul_route

    @staticmethod
    def _sum_route_cost(routes) -> float:
        return sum(route.total_cost for route in routes)

    def _parts_linehaul_share(self) -> float:
        route = self.parts_linehaul_route

        total = route.demand.loading_meters
        regional = sum(s.parts_demand.loading_meters for s in self.parts_shippers)
        if total:
            return _safe_div(regional, total)

        total = route.demand.volume
        regional = sum(s.parts_demand.volume for s in self.parts_shippers)
        if total:
            return _safe_div(regional, total)

        total = route.demand.weight
        regional = sum(s.parts_demand.weight for s in self.parts_shippers)
        return _safe_div(regional, total)

    def _empties_linehaul_share(self) -> float:
        if not self.has_empties_flow:
            return 0.0

        route = self.empties_linehaul_route

        total = route.demand.loading_meters
        regional = sum(s.empties_demand.loading_meters for s in self.empties_shippers)
        if total:
            return _safe_div(regional, total)

        total = route.demand.volume
        regional = sum(s.empties_demand.volume for s in self.empties_shippers)
        if total:
            return _safe_div(regional, total)

        total = route.demand.weight
        regional = sum(s.empties_demand.weight for s in self.empties_shippers)
        return _safe_div(regional, total)

    @staticmethod
    def _allocated_route_kpis(route, share: float) -> KPISet:
        return KPISet(
            total_cost=route.total_cost * share,
            trucks=route.frequency * share,
            utilization_numerator=route.max_utilization * route.frequency * share,
            weight=route.weight * share,
            volume=route.volume * share,
            loading_meters=route.loading_meters * share,
        )

    @property
    def hub_parts_first_leg_kpis(self) -> KPISet:
        return KPISet(
            total_cost=self._sum_route_cost(self.parts_first_leg_routes),
        )

    @property
    def hub_empties_first_leg_kpis(self) -> KPISet:
        if not self.has_empties_flow:
            return KPISet()
        return KPISet(
            total_cost=self._sum_route_cost(self.empties_first_leg_routes),
        )

    @property
    def hub_all_first_leg_kpis(self) -> KPISet:
        return self.hub_parts_first_leg_kpis + self.hub_empties_first_leg_kpis

    @property
    def hub_parts_linehaul_kpis(self) -> KPISet:
        share = self._parts_linehaul_share()
        return self._allocated_route_kpis(self.parts_linehaul_route, share)

    @property
    def hub_empties_linehaul_kpis(self) -> KPISet:
        if not self.has_empties_flow:
            return KPISet()
        share = self._empties_linehaul_share()
        return self._allocated_route_kpis(self.empties_linehaul_route, share)

    @property
    def hub_all_linehaul_kpis(self) -> KPISet:
        return self.hub_parts_linehaul_kpis + self.hub_empties_linehaul_kpis

    @property
    def hub_parts_kpis(self) -> KPISet:
        return self.hub_parts_first_leg_kpis + self.hub_parts_linehaul_kpis

    @property
    def hub_empties_kpis(self) -> KPISet:
        return self.hub_empties_first_leg_kpis + self.hub_empties_linehaul_kpis

    @property
    def hub_all_kpis(self) -> KPISet:
        return self.hub_parts_kpis + self.hub_empties_kpis