from dataclasses import dataclass
from typing import Protocol, Literal

import pandas as pd

from .hub import Hub
from .kpi_set import KPISet
from .routes.first_leg_route import FirstLegRoute


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

    @property
    def empties_pre_carriage_costs(self):
        return sum(r.total_cost for r in self.empties_first_leg_routes)

    @property
    def empties_total_cost(self):
        return self.empties_pre_carriage_costs + self.empties_linehaul_route.total_cost

    @property
    def parts_pre_carriage_costs(self):
        return sum(r.total_cost for r in self.parts_first_leg_routes)

    @property
    def parts_total_cost(self):
        return self.parts_pre_carriage_costs + self.parts_linehaul_route.total_cost

    @property
    def pre_carriage_costs(self):
        return self.parts_pre_carriage_costs + self.empties_pre_carriage_costs


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
        cost_share = self._parts_linehaul_share()

        return KPISet(
            total_cost=self.parts_linehaul_route.total_cost * cost_share,
            trucks=self.parts_linehaul_route.frequency * cost_share,
            utilization_numerator=(
                    self.parts_linehaul_route.max_utilization
                    * self.parts_linehaul_route.frequency
                    * cost_share
            ),
            weight=sum(s.parts_demand.weight for s in self.parts_shippers),
            volume=sum(s.parts_demand.volume for s in self.parts_shippers),
            loading_meters=sum(s.parts_demand.loading_meters for s in self.parts_shippers),
        )

    @property
    def hub_empties_linehaul_kpis(self) -> KPISet:
        if not self.has_empties_flow:
            return KPISet()

        cost_share = self._empties_linehaul_share()

        return KPISet(
            total_cost=self.empties_linehaul_route.total_cost * cost_share,
            trucks=self.empties_linehaul_route.frequency * cost_share,
            utilization_numerator=(
                    self.empties_linehaul_route.max_utilization
                    * self.empties_linehaul_route.frequency
                    * cost_share
            ),
            weight=sum(s.empties_demand.weight for s in self.empties_shippers),
            volume=sum(s.empties_demand.volume for s in self.empties_shippers),
            loading_meters=sum(s.empties_demand.loading_meters for s in self.empties_shippers),
        )

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

    def generate_route_name(self, flow_direction):
        direction = "P" if flow_direction == "parts" else "E"
        trip_type = "R" if self.has_empties_flow else "S"
        return f"GD_{self.name} #{direction}{trip_type}"

    def to_dataframe(self):
        rows = []

        def append_flow_rows(
                flow: Literal["parts", "empties"],
                first_leg_routes: set[FirstLegRoute],
                linehaul_route,
                flow_code: str,
        ) -> None:
            routes = sorted(
                first_leg_routes,
                key=lambda r: ((r.shipper.name or "").lower(), (r.shipper.cofor or "").lower())
            )

            first_hub_row = True

            for route in routes:
                route_name = self.generate_route_name(flow)
                shipper = route.demand.shipper
                demand = shipper.parts_demand if flow_code == "P" else shipper.empties_demand
                sellers = sorted(
                    demand.sellers,
                    key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
                )

                first_shipper_row = True

                for seller in sellers:
                    route_row = {
                        'Route name': route_name,
                        'HUB Name': self.name,
                        'Shipper COFOR': shipper.cofor,
                        'Seller COFOR': seller.cofor,
                        'Hybrid COFOR': seller.cofor,
                        'Plant COFOR': self.plant.cofor,
                        'Parts or Empties': flow_code,
                        'Docks (,)': '',
                        'First pickup': '',
                        'Total transit time (days)': '',
                        'First delivery': '',
                        'Carrier COFOR': shipper.carrier.cofor,
                        'Carrier ID': shipper.carrier.id,
                        'Carrier name': shipper.carrier.name,
                        'Means of Transport': route.vehicle.id,
                        'Transport Concept': 'todo',
                        'SELLER NAME': seller.name,
                        'SELLER ZIP CODE': seller.zip,
                        'SELLER CITY': seller.city,
                        'SELLER COUNTRY': seller.country,
                        'SHIPPER NAME': shipper.name,
                        'SHIPPER  ZIP CODE': shipper.zip_code,
                        'SHIPPER CITY': shipper.city,
                        'SHIPPER STREET': shipper.street,
                        'SHIPPER COUNTRY': shipper.country,
                        'SHIPPER SOURCING REGION': shipper.sourcing_region,
                        'HEV: empties truck loading begins at Stellantis Plant': '',
                        'HEE: empties truck leaving plant site at Stellantis Plant': '',
                        'HMD: parts truck arrival at shipper location': '',
                        'HEF: parts truck leaving shipper location': '',
                        'Pick Mon': '',
                        'Pick Tue': '',
                        'Pick Wed': '',
                        'Pick Thu': '',
                        'Pick Fri': '',
                        'Pick Sat': '',
                        'Pick Sun': '',
                        'Frequency / week': route.frequency,
                        'DEL Mon': '',
                        'DEL Tue': '',
                        'DEL Wed': '',
                        'DEL Thu': '',
                        'DEL Fri': '',
                        'DEL Sat': '',
                        'DEL Sun': '',
                        'HAS: parts truck arrival at Stellantis plant': '',
                        'Parts truck unloading starts in last dock at Stellantis Plant': '',
                        'HDE: Empties truck arrival at supplier': '',
                        'Empties truck unloading complete at supplier location': '',
                        'PLE: HAS': '',
                        'PLE: HRQ/HEE Dock 1': '',
                        'PLE: HRQ/HEE Dock 2': '',
                        'PLE: HRQ/HEE Dock 3': '',
                        'PLE: HRQ/HEE Dock 4': '',
                        'PLE: HRQ/HEE Dock 5': '',
                        'PLE: HRQ/HEE Dock 6': '',
                        'PLE: HRQ/HEE Dock 7': '',
                        'PLE: HRQ/HEE Dock 8': '',
                        'Avg. Loading Meters / week': demand.loading_meters if first_shipper_row else '',
                        'Avg. Weight / week': demand.weight if first_shipper_row else '',
                        'Avg. Volume / week': demand.volume if first_shipper_row else '',
                        'Avg. Loading Meters / week (Linehaul)': linehaul_route.loading_meters if first_hub_row else '',
                        'Avg. Loading Meters / transport': (
                            linehaul_route.loading_meters / linehaul_route.frequency
                            if first_hub_row and linehaul_route.frequency else (0 if first_hub_row else '')
                        ),
                        'Avg. Weight / week (Linehaul)': linehaul_route.weight if first_hub_row else '',
                        'Avg. Weight / transport': (
                            linehaul_route.weight / linehaul_route.frequency
                            if first_hub_row and linehaul_route.frequency else (0 if first_hub_row else '')
                        ),
                        'Avg. Volume / week on route': linehaul_route.volume if first_hub_row else '',
                        'Avg. Volume / transport': (
                            linehaul_route.volume / linehaul_route.frequency
                            if first_hub_row and linehaul_route.frequency else (0 if first_hub_row else '')
                        ),
                        'Avg. Loading meter utilization in %': linehaul_route.loading_meters_utilization if first_hub_row else '',
                        'Avg. Weight utilization in %': linehaul_route.weight_utilization if first_hub_row else '',
                        'Avg. Volume utilization in %': linehaul_route.volume_utilization if first_hub_row else '',
                        'Max. Utilization in %': linehaul_route.utilization if first_hub_row else '',
                        'Pre/on carriage total costs': self.pre_carriage_costs if first_hub_row else '',
                        'Pre/on carriage costs per week': self.pre_carriage_costs if first_hub_row else '',
                        'Linehaul total costs': linehaul_route.route_cost if first_hub_row else '',
                        'Linehaul costs per week': linehaul_route.total_cost if first_hub_row else '',
                        '[PERS. COLUMN] Original Network': shipper.original_network,
                    }
                    rows.append(route_row)
                    first_shipper_row = False
                    first_hub_row = False

        append_flow_rows(
            flow="parts",
            first_leg_routes=self.parts_first_leg_routes,
            linehaul_route=self.parts_linehaul_route,
            flow_code="P",
        )

        if self.has_empties_flow:
            append_flow_rows(
                flow="empties",
                first_leg_routes=self.empties_first_leg_routes,
                linehaul_route=self.empties_linehaul_route,
                flow_code="E",
            )

        return pd.DataFrame(rows)
