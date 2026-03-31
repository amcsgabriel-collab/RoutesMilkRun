import copy
from dataclasses import dataclass, field
from typing import Iterable, Callable, TypeVar, Set

from domain.general_algorithms import utc_now_iso
from domain.hub import Hub
from domain.kpi_set import KPISet
from domain.routes.direct_route import DirectRoute
from domain.routes.route import Route
from domain.shipper import Shipper

T = TypeVar("T")

def _sum(items: Iterable[T], fn: Callable[[T], float]) -> float:
    return sum(fn(item) for item in items)

def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0

@dataclass
class Scenario:
    """
        Heavy scenario state (stored as pickle).
        Contains actual domain objects.
        """

    name: str

    hubs: set[Hub] = field(default_factory=set)
    draft_hubs: set[Hub] = field(default_factory=set)

    routes: Set[DirectRoute] = field(default_factory=set)
    draft_routes: Set[DirectRoute] = field(default_factory=set)
    lock_block_available_routes: list[DirectRoute] = field(default_factory=list)
    blocked_routes: list[DirectRoute] = field(default_factory=list)
    locked_routes: list[DirectRoute] = field(default_factory=list)

    is_baseline: bool = field(default=False)
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

    @property
    def direct_shippers(self):
        """ COFOR Keyed dictionary of shippers currently in direct routes."""
        return {shipper.cofor: shipper
                for route in self.get_in_use_routes()
                for shipper in route.pattern.shippers}

    @property
    def hub_shippers(self):
        """ COFOR Keyed dictionary of shippers currently in hubs."""
        return {shipper.cofor: shipper
                for hub in self.get_in_use_hubs()
                for shipper in hub.shippers}

    @property
    def locked_shippers(self):
        return [s for route in self.locked_routes for s in route.pattern.shippers]

    @property
    def unlocked_shippers(self):
        """ List of shippers that are not locked"""
        return [s for s in self.direct_shippers.values() if s not in self.locked_shippers]

    def get_shippers_from_key(self, shippers_key):
        """ Gets a frozenset of shippers based on list of COFORs"""
        return frozenset(self.direct_shippers[shipper_cofor] for shipper_cofor in shippers_key)

    def get_hub_by_cofor(self, hub_cofor:str) -> Hub:
        """ Finds the Hub by the specified COFOR. """
        for hub in self.get_in_use_hubs():
            if hub.cofor == hub_cofor:
                return hub
        raise KeyError('Hub COFOR specified does not exist.')

    def find_shipper_hub(self, shipper: Shipper) -> Hub:
        """ Finds the Hub that contains a shipper. """
        for hub in self.get_in_use_hubs():
            if shipper in hub.shippers:
                return hub
        raise KeyError('Shipper passed is not in one of currently in use Hubs.')

    def find_shipper_routes(self, shipper):
        """ Finds the DirectRoute object that contains a shipper. """
        routes = []
        for route in self.get_in_use_routes():
            if shipper in route.pattern.shippers:
                routes.append(route)
        if routes:
            return routes
        raise KeyError('Shipper passed is not in one of currently in use Direct Routes.')

    def create_draft_routes(self) -> None:
        """ Creates a draft in current scenario by copying current routes."""
        if self.draft_routes:
            return
        else: self.draft_routes = {r.copy() for r in self.routes}

    def _routes_by_concept(self, concept: str | None = None) -> set[DirectRoute]:
        """ Get all DirectRoutes with specified transport concept. """
        routes = self.get_in_use_routes()
        if concept is None:
            return set(routes)
        return {r for r in routes if r.pattern.transport_concept == concept}

    @staticmethod
    def _route_total_cost(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.total_cost)

    @staticmethod
    def _route_trucks(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.frequency)

    @staticmethod
    def _route_utilization_numerator(routes: Iterable[Route]) -> float:
        routes = tuple(routes)
        weighted_utilization = _sum(routes, lambda r: r.max_utilization * r.frequency)
        return weighted_utilization

    @staticmethod
    def _route_weight(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.weight)

    @staticmethod
    def _route_volume(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.volume)

    @staticmethod
    def _route_loading_meters(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.loading_meters)

    @property
    def all_shippers(self):
        return self.direct_shippers | self.hub_shippers

    @property
    def ftl_routes(self):
        return self._routes_by_concept("FTL")

    @property
    def mr_routes(self):
        return self._routes_by_concept("MR")

    @property
    def first_leg_routes(self):
        return {route for hub in self.get_in_use_hubs() for route in hub.first_leg_routes}

    @property
    def linehaul_routes(self):
        return {hub.linehaul_route for hub in self.get_in_use_hubs()}

    # KPIs to be displayed at the UI dashboard
    def _get_kpis(self, routes):
        return KPISet(
            total_cost=self._route_total_cost(routes),
            trucks=self._route_trucks(routes),
            utilization_numerator=self._route_utilization_numerator(routes),
            weight=self._route_weight(routes),
            volume=self._route_volume(routes),
            loading_meters=self._route_loading_meters(routes),
        )

    @property
    def ftl_kpis(self):
        return self._get_kpis(self.ftl_routes)

    @property
    def mr_kpis(self):
        return self._get_kpis(self.mr_routes)

    @property
    def direct_kpis(self):
        return self.mr_kpis + self.ftl_kpis

    @property
    def hub_first_leg_kpis(self):
        return KPISet(total_cost=_sum(self.first_leg_routes, lambda r: r.total_cost))

    @property
    def hub_linehaul_kpis(self):
        return self._get_kpis(self.linehaul_routes)

    @property
    def hub_kpis(self):
        return self.hub_first_leg_kpis + self.hub_linehaul_kpis

    @property
    def global_total_kpis(self):
        return self.direct_kpis + self.hub_kpis

    # Other properties
    @property
    def summary(self):
        return {
            "name": self.name,
            "direct_total_cost": self.direct_kpis.total_cost,
            "direct_trucks": self.direct_kpis.trucks,
            "direct_utilization": self.direct_kpis.utilization,
            "hub_total_cost": self.hub_kpis.total_cost,
            "hub_trucks": self.hub_kpis.trucks,
            "updated_at": self.updated_at,
        }

    def save(self):
        if self.is_baseline:
            raise ValueError("Cannot replace baseline routes.")
        if self.draft_routes:
            self.routes = self.draft_routes
            self.draft_routes = set()