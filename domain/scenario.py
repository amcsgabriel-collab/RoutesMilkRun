import copy
from dataclasses import dataclass, field
from typing import Iterable, Callable, TypeVar

import pandas as pd

from domain.general_algorithms import utc_now_iso
from domain.hub import Hub
from domain.kpi_set import KPISet
from domain.routes.direct_route import DirectRoute
from domain.routes.route import Route
from domain.shipper import Shipper
from domain.trip import Trip

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

    trips: set[Trip] = field(default_factory=set)
    draft_trips: set[Trip] = field(default_factory=set)
    lock_block_available_routes: list[DirectRoute] = field(default_factory=list)
    blocked_routes: list[DirectRoute] = field(default_factory=list)
    locked_routes: list[DirectRoute] = field(default_factory=list)

    is_baseline: bool = field(default=False)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def copy(self):
        return copy.deepcopy(self)

    def get_in_use_trips(self) -> set[Trip]:
        return self.draft_trips or self.trips

    def create_draft_trips(self) -> None:
        if not self.draft_trips:
            self.draft_trips = {t.copy() for t in self.trips}

    def get_in_use_hubs(self):
        """ Get draft hubs if they exist, else get saved hubs. """
        if self.draft_hubs:
            return self.draft_hubs
        else:
            return self.hubs

    def refresh_lock_block_available_routes(self):
        """ Refresh the list of current routes available to be blocked / locked. """
        self.lock_block_available_routes = [
            trip.parts_route
            for trip in self.get_in_use_trips()
            if trip.parts_route is not None
            and trip.parts_route not in self.locked_routes
               and trip.parts_route not in self.blocked_routes
        ] + [
            trip.empties_route
            for trip in self.get_in_use_trips()
            if trip.empties_route is not None
            and trip.empties_route not in self.locked_routes
               and trip.empties_route not in self.blocked_routes
        ]
        return self.lock_block_available_routes

    def find_route(self, route_shippers_key, flow_direction) -> DirectRoute | None:
        """Search for the specified route by the shippers it contains, in the specified direction."""
        for t in self.get_in_use_trips():
            route = t.parts_route if flow_direction == "parts" else t.empties_route
            if route is not None and route.demand.pattern.shippers_key == route_shippers_key:
                return route
        raise KeyError(f"Route requested does not exist.")

    def lock_route(self, route: DirectRoute) -> None:
        """ Adds specified route to the 'locked routes' list."""
        if route in self.blocked_routes:
            raise RuntimeError('Cannot lock blocked route.')
        self.locked_routes.append(route)

    def unlock_route(self, route: DirectRoute) -> None:
        """ Removes specified route from the 'locked routes' list."""
        self.locked_routes.remove(route)

    def block_route(self, route: DirectRoute) -> None:
        """ Adds specified route to the 'blocked routes' list."""
        if route.demand.pattern.transport_concept == "FTL":
            raise ValueError('Cannot block FTL routes.')
        if route in self.locked_routes:
            raise RuntimeError('Cannot block locked routes.')
        self.blocked_routes.append(route)

    def unblock_route(self, route: DirectRoute) -> None:
        """ Removes specified route from the 'blocked routes' list."""
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
        """ Finds the Hub that contains a shipper. """
        for hub in self.get_in_use_hubs():
            if shipper in hub.shippers:
                return hub
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
    def all_shippers(self):
        return self.direct_shippers | self.hub_shippers

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

    @property
    def ftl_parts_kpis(self):
        return self._get_direct_kpis(flow_direction="parts", concept="FTL")

    @property
    def ftl_empties_kpis(self):
        return self._get_direct_kpis(flow_direction="empties", concept="FTL")

    @property
    def ftl_all_kpis(self):
        return self._get_direct_kpis(concept="FTL")

    @property
    def mr_parts_kpis(self):
        return self._get_direct_kpis(flow_direction="parts", concept="MR")

    @property
    def mr_empties_kpis(self):
        return self._get_direct_kpis(flow_direction="empties", concept="MR")

    @property
    def mr_all_kpis(self):
        return self._get_direct_kpis(concept="MR")

    @property
    def direct_parts_kpis(self):
        return self._get_direct_kpis(flow_direction="parts")

    @property
    def direct_empties_kpis(self):
        return self._get_direct_kpis(flow_direction="empties")

    @property
    def direct_all_kpis(self):
        return self._get_direct_kpis()

    # KPIs to be displayed at the UI dashboard
    def _get_route_kpis(self, routes):
        return KPISet(
            total_cost=self._route_total_cost(routes),
            trucks=self._route_trucks(routes),
            utilization_numerator=self._route_utilization_numerator(routes),
            weight=self._route_weight(routes),
            volume=self._route_volume(routes),
            loading_meters=self._route_loading_meters(routes),
        )

    @property
    def hub_parts_first_leg_kpis(self):
        routes = self.parts_first_leg_routes
        return KPISet(
            total_cost=self._route_total_cost(routes),
        )

    @property
    def hub_empties_first_leg_kpis(self):
        routes = self.empties_first_leg_routes
        return KPISet(
            total_cost=self._route_total_cost(routes),
        )

    @property
    def hub_all_first_leg_kpis(self):
        return self.hub_parts_first_leg_kpis + self.hub_empties_first_leg_kpis

    @property
    def hub_parts_linehaul_kpis(self):
        return self._get_route_kpis(self.parts_linehaul_routes)

    @property
    def hub_empties_linehaul_kpis(self):
        return self._get_route_kpis(self.empties_linehaul_routes)

    @property
    def hub_all_linehaul_kpis(self):
        return self.hub_parts_linehaul_kpis + self.hub_empties_linehaul_kpis

    @property
    def hub_parts_kpis(self):
        return self.hub_parts_first_leg_kpis + self.hub_parts_linehaul_kpis

    @property
    def hub_empties_kpis(self):
        return self.hub_empties_first_leg_kpis + self.hub_empties_linehaul_kpis

    @property
    def hub_all_kpis(self):
        return self.hub_parts_kpis + self.hub_empties_kpis

    @property
    def global_parts_kpis(self):
        return self.direct_parts_kpis + self.hub_parts_kpis

    @property
    def global_empties_kpis(self):
        return self.direct_empties_kpis + self.hub_empties_kpis

    @property
    def global_total_kpis(self):
        return self.direct_all_kpis + self.hub_all_kpis

    # Other properties
    @property
    def summary(self):
        return {
            "name": self.name,
            "total_cost": self.global_total_kpis.total_cost,
            "trucks": self.global_total_kpis.trucks,
            "utilization": self.global_total_kpis.utilization,
        }

    def export_trips_debug(self):
        trip_id_number = 0
        frames = []
        for trip in self.get_in_use_trips():
            trip_id_number += 1
            frames.append(trip.export_table(trip_id_number))

        debug = pd.concat(frames, ignore_index=True)
        debug.to_csv('debug_trips.csv', sep=';', decimal=',', index=False)


    def save(self):
        self.export_trips_debug()
        if self.is_baseline:
            raise ValueError("Cannot replace baseline routes.")
        if self.draft_trips:
            self.trips = self.draft_trips
            self.draft_trips = set()


