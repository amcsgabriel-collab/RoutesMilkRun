from collections import defaultdict

from rob_4flow.domain.routes.direct_route import DirectRoute
from ..solver_input_parsing import SolverInputs
from ..solver_state import MilkRunSolverState


class RouteDominanceFilter:
    def __init__(
        self,
        inputs: SolverInputs,
        state: MilkRunSolverState,
    ):
        self.inputs = inputs
        self.state = state

    def apply(self) -> None:
        self.state.parts_routes = self._filter_routes_by_zip_dominant_vehicle(
            self.state.parts_routes
        )
        self.state.empties_routes = self._filter_routes_by_zip_dominant_vehicle(
            self.state.empties_routes
        )

        self.state.parts_routes = self._filter_routes_by_pattern_frequency(
            self.state.parts_routes
        )
        self.state.empties_routes = self._filter_routes_by_pattern_frequency(
            self.state.empties_routes
        )

        filtered_cache_keys = (
            self.state.parts_routes
            | self.state.empties_routes
            | self.inputs.locked_parts_routes
            | self.inputs.locked_empties_routes
        )

        self.state.route_frequency = {
            route: value
            for route, value in self.state.route_frequency.items()
            if route in filtered_cache_keys
        }
        self.state.route_total_cost = {
            route: value
            for route, value in self.state.route_total_cost.items()
            if route in filtered_cache_keys
        }
        self.state.route_roundtrip_total_cost = {
            route: value
            for route, value in self.state.route_roundtrip_total_cost.items()
            if route in filtered_cache_keys
        }
        self.state.route_pair_delta = {
            route: value
            for route, value in self.state.route_pair_delta.items()
            if route in filtered_cache_keys
        }

    def _filter_routes_by_zip_dominant_vehicle(
        self,
        routes: set[DirectRoute],
    ) -> set[DirectRoute]:
        routes_by_zip: dict[str, list[DirectRoute]] = defaultdict(list)
        kept_routes = set()

        for route in routes:
            routes_by_zip[route.starting_point.zip_code].append(route)

        for zip_routes in routes_by_zip.values():
            best_parts_vehicle = self._pick_best_vehicle_for_zip(
                [r for r in zip_routes if r.demand.flow_direction == "parts"],
                cost_getter=lambda r: r.tariff.base_cost,
            )
            best_empties_vehicle = self._pick_best_vehicle_for_zip(
                [r for r in zip_routes if r.demand.flow_direction == "empties"],
                cost_getter=lambda r: r.tariff.base_cost,
            )
            best_roundtrip_vehicle = self._pick_best_vehicle_for_zip(
                zip_routes,
                cost_getter=lambda r: r.tariff.roundtrip_base_cost,
            )

            allowed_vehicle_ids = {
                vehicle_id
                for vehicle_id in (
                    best_parts_vehicle,
                    best_empties_vehicle,
                    best_roundtrip_vehicle,
                )
                if vehicle_id is not None
            }

            if not allowed_vehicle_ids:
                kept_routes.update(zip_routes)
                continue

            kept_routes.update(
                route
                for route in zip_routes
                if route.vehicle.id in allowed_vehicle_ids
            )

        return kept_routes

    @staticmethod
    def _pick_best_vehicle_for_zip(
        routes: list[DirectRoute],
        cost_getter,
    ) -> str | None:
        if not routes:
            return None

        best_by_vehicle: dict[str, tuple[float, str]] = {}

        for route in routes:
            vehicle_id = route.vehicle.id
            candidate = (cost_getter(route), vehicle_id)

            current_best = best_by_vehicle.get(vehicle_id)
            if current_best is None or candidate < current_best:
                best_by_vehicle[vehicle_id] = candidate

        return min(best_by_vehicle.values())[1]

    def _filter_routes_by_pattern_frequency(
        self,
        routes: set[DirectRoute],
    ) -> set[DirectRoute]:
        routes_by_pattern: dict[tuple, list[DirectRoute]] = defaultdict(list)
        kept_routes = set()

        for route in routes:
            signature = (
                route.demand.pattern,
                route.starting_point.zip_code,
                route.demand.flow_direction,
            )
            routes_by_pattern[signature].append(route)

        for same_pattern_routes in routes_by_pattern.values():
            min_frequency = min(
                self.state.route_frequency[route]
                for route in same_pattern_routes
            )
            kept_routes.update(
                route
                for route in same_pattern_routes
                if self.state.route_frequency[route] == min_frequency
            )

        return kept_routes