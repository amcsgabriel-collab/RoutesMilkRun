import copy
import math
from dataclasses import dataclass, field
from typing import Iterable, Callable, TypeVar

from .general_algorithms import utc_now_iso
from .hub import Hub
from .kpi_set import KPISet
from .regional_hub_view import HubLike
from .routes.direct_route import DirectRoute
from .routes.route import Route
from .shipper import Shipper
from .trip import Trip

T = TypeVar("T")

def _sum(items: Iterable[T], fn: Callable[[T], float]) -> float:
    return sum(fn(item) for item in items)

def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0

def with_vehicles(fn):
    def wrapper(self):
        kpis = fn(self)
        result = copy.copy(kpis)
        result.vehicles = self.kpi_vehicles
        return result

    return property(wrapper)


@dataclass
class Scenario:
    """
        Heavy scenario state (stored as pickle).
        Contains actual domain objects.
        """

    name: str

    shippers: dict[str, Shipper]

    hubs: set[HubLike] = field(default_factory=set)
    draft_hubs: set[HubLike] | None = None

    trips: set[Trip] = field(default_factory=set)
    draft_trips: set[Trip] | None = None
    lock_block_available_routes: list[Route] = field(default_factory=list)
    blocked_routes: list[Route] = field(default_factory=list)
    locked_routes: list[Route] = field(default_factory=list)

    is_baseline: bool = field(default=False)
    kpi_vehicles: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def copy(self):
        return copy.deepcopy(self)

    def get_in_use_trips(self) -> set[Trip]:
        return self.draft_trips or self.trips

    def create_draft_trips(self) -> None:
        if not self.draft_trips:
            self.draft_trips = {t.copy() for t in self.trips}

    def create_draft_hubs(self) -> None:
        if not self.draft_hubs:
            self.draft_hubs = {copy.deepcopy(h) for h in self.hubs}

    def get_in_use_hubs(self):
        """ Get draft hubs if they exist, else get saved hubs. """
        if self.draft_hubs:
            return self.draft_hubs
        else:
            return self.hubs

    def refresh_lock_block_available_routes(self):
        """Refresh the list of current routes available to be blocked / locked."""
        direct_routes = [
            route
            for trip in self.get_in_use_trips()
            for route in (trip.parts_route, trip.empties_route)
            if route is not None
               and route not in self.locked_routes
               and route not in self.blocked_routes
        ]

        hub_routes = [
            route
            for hub in self.get_in_use_hubs()
            for route in (
                    list(hub.parts_first_leg_routes)
                    + list(hub.empties_first_leg_routes)
            )
            if route is not None
               and route not in self.locked_routes
               and route not in self.blocked_routes
        ]

        self.lock_block_available_routes = direct_routes + hub_routes
        return self.lock_block_available_routes

    def find_route(self, route_shippers_key, flow_direction) -> Route | None:
        """Search for the specified route by shippers/key and flow direction."""
        flow_direction = flow_direction.lower()

        for trip in self.get_in_use_trips():
            route = trip.parts_route if flow_direction == "parts" else trip.empties_route
            if (
                    route is not None
                    and route.demand.pattern.shippers_key == route_shippers_key
            ):
                return route

        for hub in self.get_in_use_hubs():
            first_leg_routes = (
                hub.parts_first_leg_routes
                if flow_direction == "parts"
                else hub.empties_first_leg_routes
            )

            for route in first_leg_routes:
                if route.demand.shipper.cofor == route_shippers_key:
                    return route

                if frozenset([route.demand.shipper.cofor]) == route_shippers_key:
                    return route

        raise KeyError("Route requested does not exist.")

    def lock_route(self, route: Route) -> None:
        """ Adds specified route to the 'locked routes' list."""
        if route in self.blocked_routes:
            raise RuntimeError('Cannot lock blocked route.')
        route.is_locked = True
        self.locked_routes.append(route)

    def unlock_route(self, route: Route) -> None:
        """ Removes specified route from the 'locked routes' list."""
        route.is_locked = False
        self.locked_routes.remove(route)

    def block_route(self, route: Route) -> None:
        """ Adds specified route to the 'blocked routes' list."""
        if route.demand.pattern.transport_concept == "FTL":
            raise ValueError('Cannot block FTL routes.')
        if route in self.locked_routes:
            raise RuntimeError('Cannot block locked routes.')
        route.is_blocked = True
        self.blocked_routes.append(route)

    def unblock_route(self, route: Route) -> None:
        """ Removes specified route from the 'blocked routes' list."""
        route.is_blocked = False
        self.blocked_routes.remove(route)

    @property
    def parts_trips(self):
        return {t for t in self.get_in_use_trips() if t.parts_route is not None}

    @property
    def empties_trips(self):
        return {t for t in self.get_in_use_trips() if t.empties_route is not None}

    @property
    def parts_direct_shippers(self):
        """ COFOR Keyed dictionary of shippers with parts volume currently in direct routes."""
        return {shipper.cofor: shipper
                for trip in self.parts_trips
                for shipper in trip.parts_route.demand.pattern.shippers
                }

    @property
    def empties_direct_shippers(self):
        """ COFOR Keyed dictionary of shippers with empties volume currently in direct routes."""
        return {shipper.cofor: shipper
                for trip in self.empties_trips
                for shipper in trip.empties_route.demand.pattern.shippers
                }

    @property
    def direct_shippers(self):
        """ COFOR Keyed dictionary of all shippers currently in direct routes."""
        return self.empties_direct_shippers | self.parts_direct_shippers

    @property
    def hub_shippers(self):
        """ COFOR Keyed dictionary of shippers currently in hubs."""
        return {shipper.cofor: shipper
                for hub in self.get_in_use_hubs()
                for shipper in hub.shippers}

    @property
    def parts_hub_shippers(self):
        """ COFOR Keyed dictionary of shippers currently in hubs."""
        return {shipper.cofor: shipper
                for hub in self.get_in_use_hubs()
                for shipper in hub.shippers
                if shipper.has_parts_demand
                }

    @property
    def empties_hub_shippers(self):
        """ COFOR Keyed dictionary of shippers currently in hubs."""
        return {shipper.cofor: shipper
                for hub in self.get_in_use_hubs()
                if hub.has_empties_flow
                for shipper in hub.shippers
                if shipper.has_empties_demand
                }

    @property
    def hub_swap_direct_shippers(self):
        return {s for s in self.direct_shippers.keys() if s not in self.hub_shippers}

    def locked_shippers(self) -> list[Shipper]:
        """ Shippers that are currently in locked routes and can't be further optimized, locked or blocked"""
        return [shipper for route in self.locked_routes for shipper in route.demand.pattern.shippers]

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
        for hub in self.get_in_use_hubs():
            if shipper in hub.shippers:
                return getattr(hub, "core_hub", hub)
        raise KeyError('Shipper passed is not in one of currently in use Hubs.')

    def find_shipper_trips(self, shipper, flow_direction):
        """Find the trips that contain a shipper on the requested flow."""
        trips = []
        flow_direction = flow_direction.lower()

        for trip in self.get_in_use_trips():
            route = trip.parts_route if flow_direction == "parts" else trip.empties_route
            if route is None:
                continue
            if shipper in route.demand.pattern.shippers:
                trips.append(trip)

        return trips

    @property
    def first_leg_routes(self):
        return self.parts_first_leg_routes | self.empties_first_leg_routes

    @property
    def linehaul_routes(self):
        return self.parts_linehaul_routes | self.empties_linehaul_routes

    @property
    def parts_first_leg_routes(self):
        return {
            route
            for hub in self.get_in_use_hubs()
            for route in hub.parts_first_leg_routes
        }

    @property
    def empties_first_leg_routes(self):
        return {
            route
            for hub in self.get_in_use_hubs()
            if hub.has_empties_flow
            for route in hub.empties_first_leg_routes
        }

    @property
    def parts_linehaul_routes(self):
        return {
            hub.parts_linehaul_route
            for hub in self.get_in_use_hubs()
        }

    @property
    def empties_linehaul_routes(self):
        return {
            hub.empties_linehaul_route
            for hub in self.get_in_use_hubs()
            if hub.has_empties_flow
        }


    @staticmethod
    def _route_total_cost(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.total_cost)

    @staticmethod
    def _route_total_cost_with_context(
            routes_with_context: Iterable[tuple[DirectRoute, bool, float]]
    ) -> float:
        return _sum(
            routes_with_context,
            lambda x: x[0].get_total_cost(is_roundtrip=x[1]) * x[2]
        )

    @staticmethod
    def _route_trucks(routes: Iterable[Route]) -> float:
        return _sum(routes, lambda r: r.frequency)

    @staticmethod
    def _route_utilization_numerator(routes: Iterable[Route]) -> float:
        routes = tuple(routes)
        return _sum(routes, lambda r: r.max_utilization * r.frequency)

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
    def parts_all_shippers(self):
        return self.parts_direct_shippers | self.parts_hub_shippers

    @property
    def empties_all_shippers(self):
        return self.empties_direct_shippers | self.empties_hub_shippers

    @property
    def all_shippers(self):
        return self.direct_shippers | self.hub_shippers

    def unassigned_shippers(self):
        return

    def _get_direct_kpis(
            self,
            flow_direction: str | None = None,
            concept: str | None = None,
    ) -> KPISet:
        total_cost = 0.0
        trucks = 0.0
        utilization_numerator = 0.0
        weight = 0.0
        volume = 0.0
        loading_meters = 0.0

        for trip in self.get_in_use_trips():
            candidate_routes = []

            if flow_direction in (None, "parts") and trip.parts_route is not None:
                candidate_routes.append(trip.parts_route)

            if flow_direction in (None, "empties") and trip.empties_route is not None:
                candidate_routes.append(trip.empties_route)

            if concept is not None:
                candidate_routes = [
                    route
                    for route in candidate_routes
                    if route.demand.pattern.transport_concept == concept
                ]

            for route in candidate_routes:
                allocation = trip.route_allocation(route.demand.flow_direction)

                total_cost += route.get_total_cost(is_roundtrip=trip.is_roundtrip) * allocation
                trucks += route.frequency * allocation
                utilization_numerator += route.max_utilization * route.frequency * allocation
                weight += route.demand.weight * allocation
                volume += route.demand.volume * allocation
                loading_meters += route.demand.loading_meters * allocation

        return KPISet(
            total_cost=total_cost,
            trucks=trucks,
            utilization_numerator=utilization_numerator,
            weight=weight,
            volume=volume,
            loading_meters=loading_meters,
        )

    @with_vehicles
    def ftl_parts_kpis(self):
        return self._get_direct_kpis(flow_direction="parts", concept="FTL")

    @with_vehicles
    def ftl_empties_kpis(self):
        return self._get_direct_kpis(flow_direction="empties", concept="FTL")

    @with_vehicles
    def ftl_all_kpis(self):
        return self._get_direct_kpis(concept="FTL")

    @with_vehicles
    def mr_parts_kpis(self):
        return self._get_direct_kpis(flow_direction="parts", concept="MR")

    @with_vehicles
    def mr_empties_kpis(self):
        return self._get_direct_kpis(flow_direction="empties", concept="MR")

    @with_vehicles
    def mr_all_kpis(self):
        return self._get_direct_kpis(concept="MR")

    @with_vehicles
    def direct_parts_kpis(self):
        return self._get_direct_kpis(flow_direction="parts")

    @with_vehicles
    def direct_empties_kpis(self):
        return self._get_direct_kpis(flow_direction="empties")

    @with_vehicles
    def direct_all_kpis(self):
        return self._get_direct_kpis()

    @staticmethod
    def _sum_hub_kpis(hubs, attr_name: str) -> KPISet:
        result = KPISet()
        for hub in hubs:
            result += getattr(hub, attr_name)
        return result

    @with_vehicles
    def hub_parts_first_leg_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_parts_first_leg_kpis")

    @with_vehicles
    def hub_empties_first_leg_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_empties_first_leg_kpis")

    @with_vehicles
    def hub_all_first_leg_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_all_first_leg_kpis")

    @with_vehicles
    def hub_parts_linehaul_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_parts_linehaul_kpis")

    @with_vehicles
    def hub_empties_linehaul_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_empties_linehaul_kpis")

    @with_vehicles
    def hub_all_linehaul_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_all_linehaul_kpis")

    @with_vehicles
    def hub_parts_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_parts_kpis")

    @with_vehicles
    def hub_empties_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_empties_kpis")

    @with_vehicles
    def hub_all_kpis(self):
        return self._sum_hub_kpis(self.get_in_use_hubs(), "hub_all_kpis")

    @with_vehicles
    def global_parts_kpis(self):
        return self.direct_parts_kpis + self.hub_parts_kpis

    @with_vehicles
    def global_empties_kpis(self):
        return self.direct_empties_kpis + self.hub_empties_kpis

    @with_vehicles
    def global_total_kpis(self):
        return self.direct_all_kpis + self.hub_all_kpis

    @staticmethod
    def _json_number(value):
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    # Other properties
    @property
    def summary(self):
        return {
            "name": self.name,
            "has_draft": self.draft_trips is not None or self.draft_hubs is not None,
            "total_cost": self._json_number(self.global_total_kpis.total_cost),
            "trucks": self._json_number(self.global_total_kpis.trucks),
            "utilization": self._json_number(self.global_total_kpis.utilization),
        }

    def save(self):
        if self.is_baseline:
            raise ValueError("Cannot replace baseline routes.")
        if self.draft_trips:
            self.trips = self.draft_trips
            self.draft_trips = None
        if self.draft_hubs:
            self.hubs = self.draft_hubs
            self.draft_hubs = None

    def discard_draft(self):
        self.draft_trips = None
        self.draft_hubs = None



