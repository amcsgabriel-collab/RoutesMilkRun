"""
Project object: Current "Solver", should contain all the context data, the specified GRAF file, all the domain objects
created, should manage all the scenarios and regions, and should enable continuing with an optimization after closing
(saved states).

should have a "meta" object to enable quick reading/saving without having to read all data at once.
"""
import copy
from dataclasses import dataclass, field
import datetime as dt
from typing import Optional, Set, Dict, Any

from domain.data_structures import Plant, Vehicle
from domain.hub import Hub
from domain.operational_route import OperationalRoute
from domain.route_pattern import RoutePattern
from domain.shipper import Shipper
import uuid


# --------------------------------------------------------------
# Helpers

def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())

# --------------------------------------------------------------
# Scenario
@dataclass
class Scenario:
    """
        Heavy scenario state (stored as pickle).
        Contains actual domain objects.
        """

    name: str
    hub_shippers: dict[str, Shipper]
    direct_shippers: dict[str, Shipper]
    is_baseline: str = field(default=False)
    routes: Set[OperationalRoute] = field(default_factory=set)
    draft_routes: Set[OperationalRoute] = field(default=None)
    hubs: set[Hub] = field(default_factory=set)
    draft_hubs: set[Hub] = field(default_factory=set)
    lock_block_available_routes: list[OperationalRoute] = field(default_factory=list)
    blocked_routes: list[OperationalRoute] = field(default_factory=list)
    locked_routes: list[OperationalRoute] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    statuses: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def copy(self):
        return copy.deepcopy(self)

    def get_in_use_routes(self):
        if self.draft_routes:
            return self.draft_routes
        else:
            return self.routes

    def get_in_use_hubs(self):
        if self.draft_hubs:
            return self.draft_hubs
        else:
            return self.hubs

    def refresh_lock_block_available_routes(self):
        self.lock_block_available_routes = [
            route
            for route in self.get_in_use_routes()
            if route not in self.locked_routes
               and route not in self.blocked_routes
        ]
        return self.lock_block_available_routes

    def find_route(self, route_shippers_key):
        for r in self.get_in_use_routes():
            if r.pattern.shippers_key == route_shippers_key:
                return r
        return None

    def lock_route(self, route):
        if route in self.blocked_routes:
            raise RuntimeError('Cannot lock blocked route.')
        self.locked_routes.append(route)

    def unlock_route(self, route):
        self.locked_routes.remove(route)

    def block_route(self, route):
        if route.pattern.transport_concept == "FTL":
            raise ValueError('Cannot block FTL routes.')
        if route in self.locked_routes:
            raise RuntimeError('Cannot block locked routes.')
        self.blocked_routes.append(route)

    def unblock_route(self, route):
        self.blocked_routes.remove(route)

    def get_shippers_from_key(self, shippers_key):
        return frozenset(self.direct_shippers[shipper_cofor] for shipper_cofor in shippers_key)

    def swap_shipper_network(self, shipper):
        if shipper in self.hub_shippers:
            self.hub_shippers.pop(shipper.cofor)
            self.direct_shippers[shipper.cofor] = shipper
        elif shipper in self.direct_shippers:
            self.direct_shippers.pop(shipper.cofor)
            self.hub_shippers[shipper.cofor] = shipper

    @property
    def all_shippers(self):
        return self.direct_shippers | self.hub_shippers

    @property
    def ftl_routes(self):
        return {r for r in self.get_in_use_routes() if r.pattern.transport_concept == "FTL"}

    @property
    def ftl_total_cost(self) -> Optional[float]:
        return sum(r.total_cost for r in self.ftl_routes)

    @property
    def ftl_trucks(self):
        return sum(r.frequency for r in self.ftl_routes)

    @property
    def ftl_utilization(self):
        return sum(r.max_utilization * r.frequency
            for r in self.ftl_routes) * 100 / (self.ftl_trucks if self.ftl_trucks else 1)

    @property
    def ftl_weight(self):
        return sum(r.pattern.weight for r in self.ftl_routes)

    @property
    def ftl_volume(self):
        return sum(r.pattern.volume for r in self.ftl_routes)

    @property
    def ftl_loading_meters(self):
        return sum(r.pattern.loading_meters for r in self.ftl_routes)

    @property
    def ftl_euro_per_truck(self):
        return self.ftl_total_cost / self.ftl_trucks

    @property
    def ftl_volume_per_truck(self):
        return self.ftl_volume / self.ftl_trucks

    @property
    def mr_routes(self):
        return {r for r in self.get_in_use_routes() if r.pattern.transport_concept == "MR"}

    @property
    def mr_total_cost(self) -> Optional[float]:
        return sum(r.total_cost for r in self.mr_routes)

    @property
    def mr_trucks(self):
        return sum(r.frequency for r in self.mr_routes)

    @property
    def mr_utilization(self):
        return sum(r.max_utilization * r.frequency
                   for r in self.mr_routes) * 100 / (self.mr_trucks if self.mr_trucks else 1)

    @property
    def mr_weight(self):
        return sum(r.pattern.weight for r in self.mr_routes)

    @property
    def mr_volume(self):
        return sum(r.pattern.volume for r in self.mr_routes)

    @property
    def mr_loading_meters(self):
        return sum(r.pattern.loading_meters for r in self.mr_routes)

    @property
    def mr_euro_per_truck(self):
        return self.mr_total_cost / self.mr_trucks

    @property
    def mr_volume_per_truck(self):
        return self.mr_volume / self.mr_trucks

    @property
    def direct_routes(self):
        return {r for r in self.get_in_use_routes()}

    @property
    def direct_total_cost(self) -> Optional[float]:
        return sum(r.total_cost for r in self.direct_routes)

    @property
    def direct_trucks(self):
        return sum(r.frequency for r in self.direct_routes)

    @property
    def direct_utilization(self) -> float:
        return sum(
            r.max_utilization * r.frequency
            for r in self.direct_routes) * 100 / self.direct_trucks \
            if self.direct_trucks > 0 \
            else 0

    @property
    def direct_weight(self):
        return sum(r.pattern.weight for r in self.direct_routes)

    @property
    def direct_volume(self):
        return sum(r.pattern.volume for r in self.direct_routes)

    @property
    def direct_loading_meters(self):
        return sum(r.pattern.loading_meters for r in self.direct_routes)

    @property
    def direct_euro_per_truck(self):
        return self.direct_total_cost / self.direct_trucks

    @property
    def direct_volume_per_truck(self):
        return self.direct_volume / self.direct_trucks

    # HUB FIRST LEG KPIs

    @property
    def first_leg_total_cost(self) -> Optional[float]:
        return sum(h.first_leg_cost for h in self.get_in_use_hubs())

    @property
    def first_leg_weight(self):
        return sum(r.shipper.weight for h in self.get_in_use_hubs() for r in h.first_leg_routes)

    @property
    def first_leg_volume(self):
        return sum(r.shipper.volume for h in self.get_in_use_hubs() for r in h.first_leg_routes)

    @property
    def first_leg_loading_meters(self):
        return sum(r.shipper.loading_meters for h in self.get_in_use_hubs() for r in h.first_leg_routes)

    # HUB LINEHAUL KPIs

    @property
    def linehaul_total_cost(self) -> Optional[float]:
        return sum(h.linehaul_cost for h in self.get_in_use_hubs())

    @property
    def linehaul_trucks(self) -> Optional[float]:
        return sum(h.linehaul_frequency for h in self.get_in_use_hubs())

    @property
    def linehaul_utilization(self) -> Optional[float]:
        return sum(
            h.linehaul_utilization * h.linehaul_frequency
            for h in self.get_in_use_hubs()) * 100 / self.linehaul_trucks \
            if self.linehaul_trucks > 0 \
            else 0

    @property
    def linehaul_weight(self):
        return sum(h.linehaul_weight for h in self.get_in_use_hubs())

    @property
    def linehaul_volume(self):
        return sum(h.linehaul_volume for h in self.get_in_use_hubs())

    @property
    def linehaul_loading_meters(self):
        return sum(h.linehaul_loading_meters for h in self.get_in_use_hubs())

    @property
    def linehaul_euro_per_truck(self):
        return self.linehaul_total_cost / self.linehaul_trucks

    @property
    def linehaul_volume_per_truck(self):
        return self.linehaul_volume / self.linehaul_trucks

    # HUB TOTAL KPIs

    @property
    def hub_total_cost(self) -> Optional[float]:
        return sum(h.total_cost for h in self.get_in_use_hubs())

    @property
    def hub_trucks(self) -> int:
        return sum(h.linehaul_frequency for h in self.get_in_use_hubs())

    @property
    def hub_utilization(self):
        return self.linehaul_utilization

    @property
    def hub_weight(self):
        return self.linehaul_weight

    @property
    def hub_volume(self):
        return self.linehaul_volume

    @property
    def hub_loading_meters(self):
        return self.linehaul_loading_meters

    @property
    def hub_euro_per_truck(self):
        return self.linehaul_euro_per_truck

    @property
    def hub_volume_per_truck(self):
        return self.linehaul_volume_per_truck

    # GLOBAL TOTAL KPIs

    @property
    def total_cost(self):
        return self.direct_total_cost + self.hub_total_cost

    @property
    def total_trucks(self):
        return self.direct_trucks + self.hub_trucks

    @property
    def overall_utilization(self):
        return (self.hub_utilization * self.hub_trucks + self.direct_utilization * self.direct_trucks) / self.total_trucks * 100

    @property
    def total_weight(self):
        return self.direct_weight + self.hub_weight

    @property
    def total_volume(self):
        return self.direct_volume + self.hub_volume

    @property
    def total_loading_meters(self):
        return self.direct_loading_meters + self.hub_loading_meters

    @property
    def average_euro_per_truck(self):
        return (self.direct_euro_per_truck * self.direct_trucks + self.hub_euro_per_truck * self.hub_trucks) / self.total_trucks

    @property
    def average_volume_per_truck(self):
        return (self.direct_volume_per_truck * self.direct_trucks + self.hub_volume_per_truck * self.hub_trucks) / self.total_trucks

    # Other properties

    @property
    def summary(self):
        return {
            "name": self.name,
            "direct_total_cost": self.direct_total_cost,
            "direct_trucks": self.direct_trucks,
            "direct_utilization": self.direct_utilization,
            "hub_total_cost": self.hub_total_cost,
            "hub_trucks": self.hub_trucks,
            "updated_at": self.updated_at,
        }

    @property
    def locked_shippers(self):
        return [s for route in self.locked_routes for s in route.pattern.shippers]

    @property
    def unlocked_shippers(self):
        return [s for s in self.direct_shippers if s not in self.locked_shippers]

    def save(self):
        if self.is_baseline:
            raise ValueError("Cannot replace baseline routes.")
        if self.draft_routes:
            self.routes = self.draft_routes
            self.draft_routes = set()


# --------------------------------------------------------------
# Sourcing Region
@dataclass
class SourcingRegion:
    name: str
    scenarios: dict[str, Scenario]
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


# --------------------------------------------------------------
# Project
@dataclass()
class ProjectContext:
    plant: Plant
    vehicles: list[Vehicle]
    ftl_tariffs: dict
    ltl_tariffs: dict
    regions: dict[str, SourcingRegion]


@dataclass
class ProjectMeta:
    graf_file_path: str
    name: str = 'new project'
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_saved_at: bool | None = None
    current_region: str = None
    current_scenario: str = None
    context_file_path: str | None = None
    rob_file_path: str | None = None
    schema_version: int = 1


@dataclass
class Project:
    meta: ProjectMeta
    context: ProjectContext

    @property
    def name(self):
        return self.meta.name

    @property
    def regions_list(self):
        return [region for region in self.context.regions.keys()]

    @property
    def current_region(self):
        return self.context.regions[self.meta.current_region]

    @property
    def scenarios_list(self):
        return [scenario for scenario in self.current_region.scenarios.keys()]

    @property
    def current_scenario(self):
        return self.current_region.scenarios[self.meta.current_scenario]

    @property
    def plant(self):
        return self.context.plant

    @property
    def summary(self):
        return {
            "meta": {
                "name": self.name,
                "current_region": self.current_region.name,
                "current_scenario": self.current_scenario.name,
            },
            "context": {
                "plant_name": self.plant.name
            }
        }

    def create_pattern(self, shippers_key):
        return RoutePattern(self.current_scenario.get_shippers_from_key(shippers_key), self.plant)
