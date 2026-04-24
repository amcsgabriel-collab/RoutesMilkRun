"""
Solver orchestration for route optimization.

This module contains the high-level optimization flow used to generate
optimized operational routes for the current project scenario.

The optimization is split into two subproblems:
- Milk run shippers: solved through a mixed-integer optimization model
  that selects the cheapest combination of feasible multi-stop routes
  while covering each eligible shipper exactly once.
- FTL-exclusive shippers: solved deterministically by creating
  single-shipper patterns and selecting the cheapest vehicle/tariff
  option for each one.

Locked routes from the scenario are preserved as preselected direct routes
and participate in final trip assembly, including roundtrip pairing where possible.

Shippers already covered by locked routes are excluded from optimization.
User-blocked route patterns are also excluded from candidate generation.
"""
import csv
from collections import defaultdict
from pathlib import Path

import pulp

from ..domain.data_structures import Plant
from ..domain.domain_algorithms import make_haversine_cache
from ..domain.exceptions import NonOptimalSolutionError
from ..domain.project import Project
from ..domain.routes.direct_route import DirectRoute
from ..domain.routes.route_pattern import RoutePattern
from ..domain.shipper import Shipper
from ..domain.trip import Trip
from .roundtrip_combination_algorithm import iterate_trip_combination
from .route_pattern_creation_iterator import iterate_creation_of_route_patterns
from .tariff_service import TariffService
from .vehicle_permutation_service import VehiclePermutationService


def _group_key(route: DirectRoute) -> tuple:
    return route.carrier.group, route.vehicle.id, route.starting_point.zip_code


def _append_grouped_routes(
    target: dict[tuple, list[DirectRoute]],
    routes: set[DirectRoute],
) -> None:
    for route in routes:
        target[_group_key(route)].append(route)


class Solver:
    def __init__(self, project: Project, progress_tracker):
        self.project = project
        self.progress_tracker = progress_tracker

        locked_parts_shippers = {
            shipper
            for route in project.current_scenario.locked_routes
            for shipper in route.demand.pattern.shippers
            if route.demand.flow_direction == "parts"
        }
        locked_empties_shippers = {
            shipper
            for route in project.current_scenario.locked_routes
            for shipper in route.demand.pattern.shippers
            if route.demand.flow_direction == "empties"
        }

        self.filtered_parts_shippers = {
            shipper
            for shipper in project.current_scenario.parts_direct_shippers.values()
            if shipper not in locked_parts_shippers and shipper.has_parts_demand
        }
        self.filtered_empties_shippers = {
            shipper
            for shipper in project.current_scenario.empties_direct_shippers.values()
            if shipper not in locked_empties_shippers and shipper.has_empties_demand
        }

        self.locked_parts_routes = {
            route
            for route in project.current_scenario.locked_routes
            if route.demand.flow_direction == "parts"
        }
        self.locked_empties_routes = {
            route
            for route in project.current_scenario.locked_routes
            if route.demand.flow_direction == "empties"
        }

        self.solution_trips = set()
        self.blocked_patterns = {
            r.demand.pattern for r in project.current_scenario.blocked_routes
        }
        self.vehicle_permutation_service = VehiclePermutationService(
            project.context.vehicles
        )
        self.mr_solver: MilkRunSolver = None

    def run(self):
        self.progress_tracker("Solver initialized. Setting up the optimization model...")
        self.progress_tracker(
            f"Eligible shippers: {len(self.filtered_parts_shippers)} parts, "
            f"{len(self.filtered_empties_shippers)} empties"
        )

        self.solve_milkrun_shippers()
        self.combine_solutions()

        self.progress_tracker(f"Solution assembled into {len(self.solution_trips)} trips")
        return self.solution_trips

    def solve_milkrun_shippers(self):
        self.mr_solver = MilkRunSolver(
            parts_shippers=self.filtered_parts_shippers,
            empties_shippers=self.filtered_empties_shippers,
            existing_trips=self.project.current_region.scenarios["AS-IS"].trips,
            plant=self.project.plant,
            vehicle_permutation_service=self.vehicle_permutation_service,
            tariffs_service=self.project.context.tariffs_service,
            blocked_patterns=self.blocked_patterns,
            fixed_parts_routes=self.locked_parts_routes,
            fixed_empties_routes=self.locked_empties_routes,
            progress_tracker=self.progress_tracker,
        )
        self.mr_solver.build()
        self.mr_solver.solve()

    def combine_solutions(self):
        selected_parts_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)
        selected_empties_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)

        mr_parts_routes = self.mr_solver.solution_parts_routes if self.mr_solver else set()
        mr_empties_routes = (
            self.mr_solver.solution_empties_routes if self.mr_solver else set()
        )

        all_parts_routes = self.locked_parts_routes | mr_parts_routes
        all_empties_routes = self.locked_empties_routes | mr_empties_routes

        for route in all_parts_routes:
            selected_parts_by_group[_group_key(route)].append(route)

        for route in all_empties_routes:
            selected_empties_by_group[_group_key(route)].append(route)

        self.solution_trips = iterate_trip_combination(
            selected_parts_by_group=selected_parts_by_group,
            selected_empties_by_group=selected_empties_by_group,
            pair_allocations=(
                self.mr_solver.solution_pair_allocations if self.mr_solver else {}
            ),
        )


class MilkRunSolver:
    MAX_PARTNERS_PER_ROUTE = 4

    def __init__(
        self,
        parts_shippers: set[Shipper],
        empties_shippers: set[Shipper],
        existing_trips: set[Trip],
        plant: Plant,
        vehicle_permutation_service: VehiclePermutationService,
        tariffs_service: TariffService,
        progress_tracker,
        blocked_patterns: set[RoutePattern] | None = None,
        fixed_parts_routes: set[DirectRoute] | None = None,
        fixed_empties_routes: set[DirectRoute] | None = None,
    ):
        self.progress_tracker = progress_tracker
        self.progress_tracker("Preparing Shippers")

        self.parts_shippers = parts_shippers
        self.empties_shippers = empties_shippers

        self.ftl_parts_shippers = {
            s for s in self.parts_shippers if s.is_ftl_exclusive_parts
        }
        self.ftl_empties_shippers = {
            s for s in self.empties_shippers if s.is_ftl_exclusive_empties
        }

        self.mr_parts_shippers = {
            s for s in self.parts_shippers if not s.is_ftl_exclusive_parts
        }
        self.mr_empties_shippers = {
            s for s in self.empties_shippers if not s.is_ftl_exclusive_empties
        }

        self.progress_tracker(
            f"Shippers prepared: {len(self.parts_shippers)} parts "
            f"({len(self.mr_parts_shippers)} MR, {len(self.ftl_parts_shippers)} FTL), "
            f"{len(self.empties_shippers)} empties "
            f"({len(self.mr_empties_shippers)} MR, {len(self.ftl_empties_shippers)} FTL)"
        )

        self.progress_tracker("Verifying existing network setup")

        self.existing_trips = existing_trips
        self.existing_parts_patterns = {
            t.parts_route.demand.pattern
            for t in self.existing_trips
            if t.parts_route is not None
        }
        self.existing_empties_patterns = {
            t.empties_route.demand.pattern
            for t in self.existing_trips
            if t.empties_route is not None
        }

        self.plant = plant
        self.vehicle_permutation_service = vehicle_permutation_service
        self.tariffs_service = tariffs_service

        self.blocked_patterns = blocked_patterns
        self.fixed_parts_routes = fixed_parts_routes or set()
        self.fixed_empties_routes = fixed_empties_routes or set()

        self.progress_tracker(
            f"Existing network verified: {len(self.existing_trips)} existing trips, "
            f"{len(self.fixed_parts_routes)} fixed parts routes, "
            f"{len(self.fixed_empties_routes)} fixed empties routes"
        )

        self.progress_tracker("Preparing solution placeholders")

        self.parts_patterns: set[RoutePattern] = set()
        self.empties_patterns: set[RoutePattern] = set()
        self.parts_routes: set[DirectRoute] = set()
        self.empties_routes: set[DirectRoute] = set()

        self.parts_routes_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)
        self.empties_routes_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)

        self.fixed_parts_routes_by_group: dict[tuple, list[DirectRoute]] = defaultdict(
            list
        )
        self.fixed_empties_routes_by_group: dict[
            tuple, list[DirectRoute]
        ] = defaultdict(list)

        _append_grouped_routes(self.fixed_parts_routes_by_group, self.fixed_parts_routes)
        _append_grouped_routes(
            self.fixed_empties_routes_by_group, self.fixed_empties_routes
        )

        self.feasible_pair_allocations: list[tuple[DirectRoute, DirectRoute]] = []
        self.pair_saving_per_frequency: dict[
            tuple[DirectRoute, DirectRoute], float
        ] = {}
        self.pairs_by_parts_route: dict[
            DirectRoute, list[tuple[DirectRoute, DirectRoute]]
        ] = defaultdict(list)
        self.pairs_by_empties_route: dict[
            DirectRoute, list[tuple[DirectRoute, DirectRoute]]
        ] = defaultdict(list)

        self.route_frequency: dict[DirectRoute, int] = {}
        self.route_total_cost: dict[DirectRoute, float] = {}
        self.route_roundtrip_total_cost: dict[DirectRoute, float] = {}
        self.route_pair_delta: dict[DirectRoute, float] = {}

        self.pair_frequency = None
        self.solution_pair_allocations: dict[tuple[DirectRoute, DirectRoute], int] = {}

        self.model = None
        self.use_parts_route_bin = None
        self.use_empties_route_bin = None

        self.solve_status = "Not Solved Yet"
        self.solution_parts_routes = set()
        self.solution_empties_routes = set()
        self.solution_trips = set()

    @property
    def all_patterns(self):
        return self.parts_patterns.union(self.empties_patterns)

    def build(self):
        self.progress_tracker("Generating route pattern candidates")
        self.generate_route_patterns()
        self.progress_tracker(
            f"Generated {len(self.parts_patterns)} parts patterns and "
            f"{len(self.empties_patterns)} empties patterns"
        )

        self.apply_ordering_to_route_patterns()
        self.progress_tracker(
            "Applied shipper ordering and deviation calculation to route patterns"
        )

        self.remove_high_deviation_route_patterns()
        self.progress_tracker(
            f"Retained {len(self.parts_patterns)} parts patterns and "
            f"{len(self.empties_patterns)} empties patterns after deviation filter"
        )

        self.progress_tracker("Permutating pattern candidates into vehicles")

        new_parts_routes = self.vehicle_permutation_service.permutate(self.parts_patterns)
        self.tariffs_service.assign_ftl_mr_routes(new_parts_routes)
        self.parts_routes = {r for r in new_parts_routes if r.total_cost > 0}

        new_empties_routes = self.vehicle_permutation_service.permutate(
            self.empties_patterns
        )
        self.tariffs_service.assign_ftl_mr_routes(new_empties_routes)
        self.empties_routes = {r for r in new_empties_routes if r.total_cost > 0}

        self.progress_tracker(
            f"Created {len(self.parts_routes)} feasible parts routes and "
            f"{len(self.empties_routes)} feasible empties routes"
        )

        self.build_route_caches()
        self.progress_tracker(
            f"Built route caches for {len(self.route_frequency)} total routes"
        )

        self.remove_dominated_routes()
        self.progress_tracker(
            f"Retained {len(self.parts_routes)} non-dominated parts routes and "
            f"{len(self.empties_routes)} non-dominated empties routes"
        )

        self.rebuild_route_group_indexes()
        self.build_feasible_pair_allocations()
        self.progress_tracker(
            f"Built {len(self.feasible_pair_allocations)} feasible roundtrip pair allocations"
        )

        self.rebuild_route_group_indexes()
        self.run_conservative_lp_route_pruning()
        self.progress_tracker(
            f"Retained {len(self.parts_routes)} parts routes and "
            f"{len(self.empties_routes)} empties routes after conservative LP pruning"
        )

        self.run_conservative_lp_pair_pruning()
        self.progress_tracker(
            f"Retained {len(self.feasible_pair_allocations)} feasible roundtrip pair allocations "
            f"after conservative LP pair pruning"
        )


        self.progress_tracker("Building optimization Model")
        self.build_model()
        stats = self.get_model_stats()
        self.progress_tracker(
            "\n".join([
                "Optimization model ready:",
                f"  Constraints: {stats['constraints']}",
                f"  Variables: {stats['variables']['binary']} binary, {stats['variables']['continuous']} continuous",
                f"  Routes: parts={stats['routes']['parts']}, empties={stats['routes']['empties']}",
                f"  Fixed: parts={stats['routes']['fixed_parts']}, empties={stats['routes']['fixed_empties']}",
                f"  Pair vars: {stats['variables']['pair_vars']}",
                f"  Parts routes/shipper: avg={stats['structure']['avg_parts_routes_per_shipper']:.2f}, max={stats['structure']['max_parts_routes_per_shipper']}",
                f"  Empties routes/shipper: avg={stats['structure']['avg_empties_routes_per_shipper']:.2f}, max={stats['structure']['max_empties_routes_per_shipper']}",
                f"  Pairs per parts route: avg={stats['structure']['avg_pairs_per_parts_route']:.2f}, max={stats['structure']['max_pairs_per_parts_route']}",
                f"  Pairs per empties route: avg={stats['structure']['avg_pairs_per_empties_route']:.2f}, max={stats['structure']['max_pairs_per_empties_route']}",
                f"  Cost range: {stats['ranges']['objective_cost']}",
                f"  Pair saving range: {stats['ranges']['pair_saving']}",
                f"  Frequency range: {stats['ranges']['route_frequency']}",
            ])
        )

    def solve(self):
        self.progress_tracker("Running optimization model")
        self.solve_model()
        self.progress_tracker(f"Optimization finished with status: {self.solve_status}")

        self.progress_tracker("Run finished. Analyzing and preparing results")
        self.convert_solutions()
        self.progress_tracker(
            f"Selected {len(self.solution_parts_routes)} parts routes, "
            f"{len(self.solution_empties_routes)} empties routes, "
            f"and {len(self.solution_pair_allocations)} pair allocations"
        )

    def generate_route_patterns(self) -> None:
        carriers = {s.carrier.group for s in self.parts_shippers | self.empties_shippers}
        self.progress_tracker(f"Generating route patterns for {len(carriers)} carrier groups")

        for carrier in carriers:
            carrier_mr_parts_shippers = {
                s for s in self.mr_parts_shippers if s.carrier.group == carrier
            }
            carrier_mr_empties_shippers = {
                s for s in self.mr_empties_shippers if s.carrier.group == carrier
            }
            carrier_ftl_parts_shippers = {
                s for s in self.ftl_parts_shippers if s.carrier.group == carrier
            }
            carrier_ftl_empties_shippers = {
                s for s in self.ftl_empties_shippers if s.carrier.group == carrier
            }

            self.parts_patterns |= iterate_creation_of_route_patterns(
                shippers=carrier_mr_parts_shippers,
                existing_patterns=self.existing_parts_patterns,
                flow_direction="parts",
                plant=self.plant,
                max_stops=4,
                blocked_combinations=self.blocked_patterns,
            )
            self.empties_patterns |= iterate_creation_of_route_patterns(
                shippers=carrier_mr_empties_shippers,
                existing_patterns=self.existing_empties_patterns,
                flow_direction="empties",
                plant=self.plant,
                max_stops=4,
                blocked_combinations=self.blocked_patterns,
            )
            self.parts_patterns |= iterate_creation_of_route_patterns(
                shippers=carrier_ftl_parts_shippers,
                existing_patterns=self.existing_parts_patterns,
                flow_direction="parts",
                plant=self.plant,
                max_stops=1,
                blocked_combinations=self.blocked_patterns,
            )
            self.empties_patterns |= iterate_creation_of_route_patterns(
                shippers=carrier_ftl_empties_shippers,
                existing_patterns=self.existing_empties_patterns,
                flow_direction="empties",
                plant=self.plant,
                max_stops=1,
                blocked_combinations=self.blocked_patterns,
            )

            self.progress_tracker(
                f"Carrier {carrier}: {len(carrier_mr_parts_shippers)} MR parts, "
                f"{len(carrier_ftl_parts_shippers)} FTL parts, "
                f"{len(carrier_mr_empties_shippers)} MR empties, "
                f"{len(carrier_ftl_empties_shippers)} FTL empties processed"
            )

    def apply_ordering_to_route_patterns(self):
        distance_function = make_haversine_cache()
        for pattern in self.all_patterns:
            pattern.order_shippers(distance_function)
            pattern.calculate_deviation(distance_function)

    def remove_high_deviation_route_patterns(self):
        parts_patterns_to_remove = {p for p in self.parts_patterns if p.deviation > 150}
        for pattern in parts_patterns_to_remove:
            self.parts_patterns.remove(pattern)

        empties_patterns_to_remove = {
            p for p in self.empties_patterns if p.deviation > 150
        }
        for pattern in empties_patterns_to_remove:
            self.empties_patterns.remove(pattern)

    def build_route_caches(self):
        self.route_frequency.clear()
        self.route_total_cost.clear()
        self.route_roundtrip_total_cost.clear()
        self.route_pair_delta.clear()

        all_routes = (
            self.parts_routes
            | self.empties_routes
            | self.fixed_parts_routes
            | self.fixed_empties_routes
        )

        for route in all_routes:
            freq = int(route.frequency)
            self.route_frequency[route] = freq
            self.route_total_cost[route] = route.total_cost
            self.route_roundtrip_total_cost[route] = route.roundtrip_total_cost

            if freq == 0:
                self.route_pair_delta[route] = 0.0
            else:
                direct_unit_cost = route.total_cost / freq
                roundtrip_unit_cost = route.roundtrip_total_cost / freq
                self.route_pair_delta[route] = direct_unit_cost - roundtrip_unit_cost

    def rebuild_route_group_indexes(self):
        self.parts_routes_by_group = self._group_routes(self.parts_routes)
        self.empties_routes_by_group = self._group_routes(self.empties_routes)

    def remove_dominated_routes(self):
        self.parts_routes = self._filter_routes_by_zip_dominant_vehicle(self.parts_routes)
        self.empties_routes = self._filter_routes_by_zip_dominant_vehicle(
            self.empties_routes
        )

        self.parts_routes = self._filter_routes_by_pattern_frequency(self.parts_routes)
        self.empties_routes = self._filter_routes_by_pattern_frequency(
            self.empties_routes
        )

        filtered_cache_keys = (
            self.parts_routes
            | self.empties_routes
            | self.fixed_parts_routes
            | self.fixed_empties_routes
        )

        self.route_frequency = {
            route: value
            for route, value in self.route_frequency.items()
            if route in filtered_cache_keys
        }
        self.route_total_cost = {
            route: value
            for route, value in self.route_total_cost.items()
            if route in filtered_cache_keys
        }
        self.route_roundtrip_total_cost = {
            route: value
            for route, value in self.route_roundtrip_total_cost.items()
            if route in filtered_cache_keys
        }
        self.route_pair_delta = {
            route: value
            for route, value in self.route_pair_delta.items()
            if route in filtered_cache_keys
        }

    def _filter_routes_by_zip_dominant_vehicle(
        self, routes: set[DirectRoute]
    ) -> set[DirectRoute]:
        routes_by_zip: dict[str, list[DirectRoute]] = defaultdict(list)
        kept_routes = set()

        for route in routes:
            routes_by_zip[route.starting_point.zip_code].append(route)

        for zip_code, zip_routes in routes_by_zip.items():
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
                route for route in zip_routes if route.vehicle.id in allowed_vehicle_ids
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
        self, routes: set[DirectRoute]
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
            min_frequency = min(self.route_frequency[route] for route in same_pattern_routes)
            kept_routes.update(
                route
                for route in same_pattern_routes
                if self.route_frequency[route] == min_frequency
            )

        return kept_routes

    def _unit_cost(self, route: DirectRoute, *, is_roundtrip: bool) -> float:
        freq = self.route_frequency[route]
        if freq == 0:
            return 0.0

        total = (
            self.route_roundtrip_total_cost[route]
            if is_roundtrip
            else self.route_total_cost[route]
        )
        return total / freq

    @staticmethod
    def _group_routes(routes: set[DirectRoute]) -> dict[tuple, list[DirectRoute]]:
        grouped: dict[tuple, list[DirectRoute]] = defaultdict(list)
        for route in routes:
            grouped[_group_key(route)].append(route)
        return grouped

    def _pair_saving_per_frequency(
        self,
        parts_route: DirectRoute,
        empties_route: DirectRoute,
    ) -> float:
        return max(
            0.0,
            self.route_pair_delta[parts_route] + self.route_pair_delta[empties_route],
        )

    def build_feasible_pair_allocations(self):
        self.feasible_pair_allocations = []
        self.pair_saving_per_frequency = {}
        self.pairs_by_parts_route.clear()
        self.pairs_by_empties_route.clear()

        shared_groups = (
            set(self.parts_routes_by_group) | set(self.fixed_parts_routes_by_group)
        ) & (
            set(self.empties_routes_by_group) | set(self.fixed_empties_routes_by_group)
        )

        fixed_parts_routes = self.fixed_parts_routes
        fixed_empties_routes = self.fixed_empties_routes
        route_pair_delta = self.route_pair_delta
        max_partners = self.MAX_PARTNERS_PER_ROUTE

        for group in shared_groups:
            group_parts_routes = self.parts_routes_by_group.get(
                group, []
            ) + self.fixed_parts_routes_by_group.get(group, [])
            group_empties_routes = self.empties_routes_by_group.get(
                group, []
            ) + self.fixed_empties_routes_by_group.get(group, [])

            if not group_parts_routes or not group_empties_routes:
                continue

            sorted_empties_routes = sorted(
                group_empties_routes,
                key=lambda route: route_pair_delta[route],
                reverse=True,
            )

            for parts_route in group_parts_routes:
                parts_delta = route_pair_delta[parts_route]
                selected_count = 0

                for empties_route in sorted_empties_routes:
                    if (
                        parts_route in fixed_parts_routes
                        and empties_route in fixed_empties_routes
                    ):
                        continue

                    saving = parts_delta + route_pair_delta[empties_route]
                    if saving <= 0:
                        break

                    pair = (parts_route, empties_route)
                    self.feasible_pair_allocations.append(pair)
                    self.pair_saving_per_frequency[pair] = saving
                    self.pairs_by_parts_route[parts_route].append(pair)
                    self.pairs_by_empties_route[empties_route].append(pair)

                    selected_count += 1
                    if selected_count >= max_partners:
                        break

    def get_model_stats(self):
        parts_routes_per_shipper = [
            sum(1 for r in self.parts_routes if shipper in r.demand.pattern.shippers)
            for shipper in self.parts_shippers
        ]

        empties_routes_per_shipper = [
            sum(1 for r in self.empties_routes if shipper in r.demand.pattern.shippers)
            for shipper in self.empties_shippers
        ]

        avg_parts_routes_per_shipper = (
            sum(parts_routes_per_shipper) / len(parts_routes_per_shipper)
            if parts_routes_per_shipper else 0
        )
        max_parts_routes_per_shipper = max(parts_routes_per_shipper, default=0)

        avg_empties_routes_per_shipper = (
            sum(empties_routes_per_shipper) / len(empties_routes_per_shipper)
            if empties_routes_per_shipper else 0
        )
        max_empties_routes_per_shipper = max(empties_routes_per_shipper, default=0)

        # --- pairs per route ---
        pairs_per_parts_route = [
            len(self.pairs_by_parts_route.get(route, []))
            for route in self.parts_routes
        ]

        pairs_per_empties_route = [
            len(self.pairs_by_empties_route.get(route, []))
            for route in self.empties_routes
        ]

        avg_pairs_per_parts_route = (
            sum(pairs_per_parts_route) / len(pairs_per_parts_route)
            if pairs_per_parts_route else 0
        )
        max_pairs_per_parts_route = max(pairs_per_parts_route, default=0)

        avg_pairs_per_empties_route = (
            sum(pairs_per_empties_route) / len(pairs_per_empties_route)
            if pairs_per_empties_route else 0
        )
        max_pairs_per_empties_route = max(pairs_per_empties_route, default=0)

        # --- ranges ---
        all_costs = list(self.route_total_cost.values())
        min_cost = min(all_costs, default=0)
        max_cost = max(all_costs, default=0)

        all_savings = list(self.pair_saving_per_frequency.values())
        min_saving = min(all_savings, default=0)
        max_saving = max(all_savings, default=0)

        all_freqs = list(self.route_frequency.values())
        min_freq = min(all_freqs, default=0)
        max_freq = max(all_freqs, default=0)

        return {
            "routes": {
                "parts": len(self.parts_routes),
                "empties": len(self.empties_routes),
                "fixed_parts": len(self.fixed_parts_routes),
                "fixed_empties": len(self.fixed_empties_routes),
            },
            "variables": {
                "binary": len(self.parts_routes) + len(self.empties_routes),
                "continuous": len(self.feasible_pair_allocations),
                "pair_vars": len(self.feasible_pair_allocations),
            },
            "structure": {
                "avg_parts_routes_per_shipper": avg_parts_routes_per_shipper,
                "max_parts_routes_per_shipper": max_parts_routes_per_shipper,
                "avg_empties_routes_per_shipper": avg_empties_routes_per_shipper,
                "max_empties_routes_per_shipper": max_empties_routes_per_shipper,
                "avg_pairs_per_parts_route": avg_pairs_per_parts_route,
                "max_pairs_per_parts_route": max_pairs_per_parts_route,
                "avg_pairs_per_empties_route": avg_pairs_per_empties_route,
                "max_pairs_per_empties_route": max_pairs_per_empties_route,
            },
            "ranges": {
                "objective_cost": (min_cost, max_cost),
                "pair_saving": (min_saving, max_saving),
                "route_frequency": (min_freq, max_freq),
            },
            "constraints": len(self.model.constraints),
        }


    def build_model(self):
        self.model = pulp.LpProblem("Atomic_Route_Allocation", pulp.LpMinimize)

        self.use_parts_route_bin = pulp.LpVariable.dicts(
            name="use_parts_route",
            indices=self.parts_routes,
            cat="Binary",
        )
        self.use_empties_route_bin = pulp.LpVariable.dicts(
            name="use_empties_route",
            indices=self.empties_routes,
            cat="Binary",
        )
        self.pair_frequency = pulp.LpVariable.dicts(
            name="pair_frequency",
            indices=self.feasible_pair_allocations,
            lowBound=0,
            cat="Continuous",
        )

        self.model += (
            pulp.lpSum(
                self.route_total_cost[r] * self.use_parts_route_bin[r]
                for r in self.parts_routes
            )
            + pulp.lpSum(
                self.route_total_cost[r] * self.use_empties_route_bin[r]
                for r in self.empties_routes
            )
            - pulp.lpSum(
                self.pair_saving_per_frequency[pair] * self.pair_frequency[pair]
                for pair in self.feasible_pair_allocations
            )
        )

        for shipper in self.parts_shippers:
            self.model += (
                pulp.lpSum(
                    self.use_parts_route_bin[route]
                    for route in self.parts_routes
                    if shipper in route.demand.pattern.shippers
                )
                == 1
            )

        for shipper in self.empties_shippers:
            self.model += (
                pulp.lpSum(
                    self.use_empties_route_bin[route]
                    for route in self.empties_routes
                    if shipper in route.demand.pattern.shippers
                )
                == 1
            )

        for parts_route in self.parts_routes:
            self.model += (
                pulp.lpSum(
                    self.pair_frequency[pair]
                    for pair in self.pairs_by_parts_route.get(parts_route, [])
                )
                <= self.route_frequency[parts_route]
                * self.use_parts_route_bin[parts_route],
                f"pair_cap_parts_{hash(parts_route)}",
            )

        for empties_route in self.empties_routes:
            self.model += (
                pulp.lpSum(
                    self.pair_frequency[pair]
                    for pair in self.pairs_by_empties_route.get(empties_route, [])
                )
                <= self.route_frequency[empties_route]
                * self.use_empties_route_bin[empties_route],
                f"pair_cap_empties_{hash(empties_route)}",
            )

        for fixed_parts_route in self.fixed_parts_routes:
            self.model += (
                pulp.lpSum(
                    self.pair_frequency[pair]
                    for pair in self.pairs_by_parts_route.get(fixed_parts_route, [])
                )
                <= self.route_frequency[fixed_parts_route],
                f"pair_cap_fixed_parts_{hash(fixed_parts_route)}",
            )

        for fixed_empties_route in self.fixed_empties_routes:
            self.model += (
                pulp.lpSum(
                    self.pair_frequency[pair]
                    for pair in self.pairs_by_empties_route.get(fixed_empties_route, [])
                )
                <= self.route_frequency[fixed_empties_route],
                f"pair_cap_fixed_empties_{hash(fixed_empties_route)}",
            )

    def solve_model(self):
        solver = pulp.PULP_CBC_CMD(msg=True)
        self.model.solve(solver)
        self.solve_status = pulp.LpStatus[self.model.status]
        print("Solve status:", self.solve_status)

        if self.solve_status != "Optimal":
            raise NonOptimalSolutionError()

    def convert_solutions(self):
        self.solution_parts_routes = {
            route
            for route, var in self.use_parts_route_bin.items()
            if round(pulp.value(var)) == 1
        }
        self.solution_empties_routes = {
            route
            for route, var in self.use_empties_route_bin.items()
            if round(pulp.value(var)) == 1
        }
        self.solution_pair_allocations = {
            pair: int(round(pulp.value(var)))
            for pair, var in self.pair_frequency.items()
            if round(pulp.value(var)) > 0
        }

    @staticmethod
    def _stable_pattern_key(pattern: RoutePattern) -> str:
        return "|".join(
            sorted(getattr(shipper, "id", str(shipper)) for shipper in pattern.shippers)
        )

    @staticmethod
    def _stable_route_key(route: DirectRoute) -> tuple:
        return (
            route.demand.flow_direction,
            route.carrier.group,
            route.vehicle.id,
            route.starting_point.zip_code,
            "|".join(
                sorted(
                    getattr(shipper, "id", str(shipper))
                    for shipper in route.demand.pattern.shippers
                )
            ),
        )

    @staticmethod
    def _shipper_ids(route: DirectRoute) -> str:
        return "|".join(
            sorted(getattr(shipper, "id", str(shipper)) for shipper in route.demand.pattern.shippers)
        )

    @staticmethod
    def _shipper_names(route: DirectRoute) -> str:
        return "|".join(
            sorted(getattr(shipper, "name", str(shipper)) for shipper in route.demand.pattern.shippers)
        )

    def export_lp_relaxation_csv(
            self,
            output_dir: str | Path,
            *,
            file_prefix: str = "lp_relaxation",
            solver=None,
    ) -> None:
        """
        Exports LP-relaxation diagnostics for all route and pair variables.

        Output files:
        - {file_prefix}_routes.csv
        - {file_prefix}_pairs.csv
        """

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.progress_tracker("Building LP relaxation diagnostic model")

        lp_model = pulp.LpProblem("Atomic_Route_Allocation_LP_Relaxation", pulp.LpMinimize)

        sorted_parts_routes = sorted(self.parts_routes, key=self._stable_route_key)
        sorted_empties_routes = sorted(self.empties_routes, key=self._stable_route_key)
        sorted_pairs = sorted(
            self.feasible_pair_allocations,
            key=lambda pair: (
                self._stable_route_key(pair[0]),
                self._stable_route_key(pair[1]),
            ),
        )

        use_parts_route = pulp.LpVariable.dicts(
            name="use_parts_route_lp",
            indices=sorted_parts_routes,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        use_empties_route = pulp.LpVariable.dicts(
            name="use_empties_route_lp",
            indices=sorted_empties_routes,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        pair_frequency = pulp.LpVariable.dicts(
            name="pair_frequency_lp",
            indices=sorted_pairs,
            lowBound=0,
            cat="Continuous",
        )

        lp_model += (
                pulp.lpSum(
                    self.route_total_cost[r] * use_parts_route[r]
                    for r in sorted_parts_routes
                )
                + pulp.lpSum(
            self.route_total_cost[r] * use_empties_route[r]
            for r in sorted_empties_routes
        )
                - pulp.lpSum(
            self.pair_saving_per_frequency[pair] * pair_frequency[pair]
            for pair in sorted_pairs
        )
        )

        for shipper in sorted(
                self.parts_shippers, key=lambda s: getattr(s, "id", str(s))
        ):
            lp_model += (
                pulp.lpSum(
                    use_parts_route[route]
                    for route in sorted_parts_routes
                    if shipper in route.demand.pattern.shippers
                )
                == 1,
                f"cover_parts_{getattr(shipper, 'id', str(shipper))}",
            )

        for shipper in sorted(
                self.empties_shippers, key=lambda s: getattr(s, "id", str(s))
        ):
            lp_model += (
                pulp.lpSum(
                    use_empties_route[route]
                    for route in sorted_empties_routes
                    if shipper in route.demand.pattern.shippers
                )
                == 1,
                f"cover_empties_{getattr(shipper, 'id', str(shipper))}",
            )

        for parts_route in sorted_parts_routes:
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.pairs_by_parts_route.get(parts_route, [])
                )
                <= self.route_frequency[parts_route] * use_parts_route[parts_route],
                "pair_cap_parts_lp_" + "_".join(map(str, self._stable_route_key(parts_route))),
            )

        for empties_route in sorted_empties_routes:
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.pairs_by_empties_route.get(empties_route, [])
                )
                <= self.route_frequency[empties_route] * use_empties_route[empties_route],
                "pair_cap_empties_lp_" + "_".join(map(str, self._stable_route_key(empties_route))),
            )

        for fixed_parts_route in sorted(
                self.fixed_parts_routes, key=self._stable_route_key
        ):
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.pairs_by_parts_route.get(fixed_parts_route, [])
                )
                <= self.route_frequency[fixed_parts_route],
                "pair_cap_fixed_parts_lp_" + "_".join(map(str, self._stable_route_key(fixed_parts_route))),
            )

        for fixed_empties_route in sorted(
                self.fixed_empties_routes, key=self._stable_route_key
        ):
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.pairs_by_empties_route.get(fixed_empties_route, [])
                )
                <= self.route_frequency[fixed_empties_route],
                "pair_cap_fixed_empties_lp_" + "_".join(map(str, self._stable_route_key(fixed_empties_route))),
            )

        if solver is None:
            solver = pulp.PULP_CBC_CMD(msg=True)

        self.progress_tracker("Solving LP relaxation diagnostic model")
        lp_model.solve(solver)
        lp_status = pulp.LpStatus[lp_model.status]
        self.progress_tracker(f"LP relaxation diagnostic solve finished with status: {lp_status}")

        routes_csv_path = output_dir / f"{file_prefix}_routes.csv"
        pairs_csv_path = output_dir / f"{file_prefix}_pairs.csv"

        self._write_lp_routes_csv(
            csv_path=routes_csv_path,
            lp_model=lp_model,
            use_parts_route=use_parts_route,
            use_empties_route=use_empties_route,
            lp_status=lp_status,
        )
        self._write_lp_pairs_csv(
            csv_path=pairs_csv_path,
            lp_model=lp_model,
            pair_frequency=pair_frequency,
            lp_status=lp_status,
        )

        self.progress_tracker(
            f"LP relaxation diagnostics exported to {routes_csv_path} and {pairs_csv_path}"
        )

    def _write_lp_routes_csv(
            self,
            csv_path: Path,
            lp_model,
            use_parts_route,
            use_empties_route,
            lp_status: str,
    ) -> None:
        all_routes = sorted(
            self.parts_routes | self.empties_routes,
            key=self._stable_route_key,
        )

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "lp_status",
                    "lp_objective_value",
                    "route_kind",
                    "lp_variable_name",
                    "lp_value",
                    "lp_reduced_cost",
                    "flow_direction",
                    "carrier_group",
                    "vehicle_id",
                    "vehicle_name",
                    "starting_zip_code",
                    "group_key",
                    "pattern_key",
                    "shipper_ids",
                    "shipper_names",
                    "shipper_count",
                    "frequency",
                    "total_cost",
                    "roundtrip_total_cost",
                    "unit_cost",
                    "roundtrip_unit_cost",
                    "pair_delta_per_frequency",
                    "tariff_base_cost",
                    "tariff_roundtrip_base_cost",
                    "in_existing_network",
                    "is_fixed_route",
                    "pair_options_count",
                ],
            )
            writer.writeheader()

            lp_objective_value = pulp.value(lp_model.objective)

            for route in all_routes:
                if route in use_parts_route:
                    variable = use_parts_route[route]
                    route_kind = "parts"
                else:
                    variable = use_empties_route[route]
                    route_kind = "empties"

                frequency = self.route_frequency[route]
                total_cost = self.route_total_cost[route]
                roundtrip_total_cost = self.route_roundtrip_total_cost[route]

                writer.writerow(
                    {
                        "lp_status": lp_status,
                        "lp_objective_value": lp_objective_value,
                        "route_kind": route_kind,
                        "lp_variable_name": variable.name,
                        "lp_value": pulp.value(variable),
                        "lp_reduced_cost": getattr(variable, "dj", None),
                        "flow_direction": route.demand.flow_direction,
                        "carrier_group": route.carrier.group,
                        "vehicle_id": route.vehicle.id,
                        "vehicle_name": getattr(route.vehicle, "name", ""),
                        "starting_zip_code": route.starting_point.zip_code,
                        "group_key": str(_group_key(route)),
                        "pattern_key": self._stable_pattern_key(route.demand.pattern),
                        "shipper_ids": self._shipper_ids(route),
                        "shipper_names": self._shipper_names(route),
                        "shipper_count": len(route.demand.pattern.shippers),
                        "frequency": frequency,
                        "total_cost": total_cost,
                        "roundtrip_total_cost": roundtrip_total_cost,
                        "unit_cost": (total_cost / frequency) if frequency else 0,
                        "roundtrip_unit_cost": (
                                roundtrip_total_cost / frequency
                        ) if frequency else 0,
                        "pair_delta_per_frequency": self.route_pair_delta[route],
                        "tariff_base_cost": getattr(route.tariff, "base_cost", None),
                        "tariff_roundtrip_base_cost": getattr(
                            route.tariff, "roundtrip_base_cost", None
                        ),
                        "in_existing_network": (
                            route.demand.pattern in self.existing_parts_patterns
                            if route.demand.flow_direction == "parts"
                            else route.demand.pattern in self.existing_empties_patterns
                        ),
                        "is_fixed_route": (
                                route in self.fixed_parts_routes
                                or route in self.fixed_empties_routes
                        ),
                        "pair_options_count": len(
                            self.pairs_by_parts_route.get(route, [])
                            if route.demand.flow_direction == "parts"
                            else self.pairs_by_empties_route.get(route, [])
                        ),
                    }
                )

    def _write_lp_pairs_csv(
            self,
            csv_path: Path,
            lp_model,
            pair_frequency,
            lp_status: str,
    ) -> None:
        sorted_pairs = sorted(
            self.feasible_pair_allocations,
            key=lambda pair: (
                self._stable_route_key(pair[0]),
                self._stable_route_key(pair[1]),
            ),
        )

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "lp_status",
                    "lp_objective_value",
                    "lp_variable_name",
                    "lp_value",
                    "lp_reduced_cost",
                    "pair_saving_per_frequency",
                    "parts_route_key",
                    "empties_route_key",
                    "parts_vehicle_id",
                    "empties_vehicle_id",
                    "parts_zip_code",
                    "empties_zip_code",
                    "parts_pattern_key",
                    "empties_pattern_key",
                    "parts_frequency",
                    "empties_frequency",
                    "parts_total_cost",
                    "empties_total_cost",
                    "parts_roundtrip_total_cost",
                    "empties_roundtrip_total_cost",
                ],
            )
            writer.writeheader()

            lp_objective_value = pulp.value(lp_model.objective)

            for pair in sorted_pairs:
                parts_route, empties_route = pair
                variable = pair_frequency[pair]

                writer.writerow(
                    {
                        "lp_status": lp_status,
                        "lp_objective_value": lp_objective_value,
                        "lp_variable_name": variable.name,
                        "lp_value": pulp.value(variable),
                        "lp_reduced_cost": getattr(variable, "dj", None),
                        "pair_saving_per_frequency": self.pair_saving_per_frequency[pair],
                        "parts_route_key": str(self._stable_route_key(parts_route)),
                        "empties_route_key": str(self._stable_route_key(empties_route)),
                        "parts_vehicle_id": parts_route.vehicle.id,
                        "empties_vehicle_id": empties_route.vehicle.id,
                        "parts_zip_code": parts_route.starting_point.zip_code,
                        "empties_zip_code": empties_route.starting_point.zip_code,
                        "parts_pattern_key": self._stable_pattern_key(
                            parts_route.demand.pattern
                        ),
                        "empties_pattern_key": self._stable_pattern_key(
                            empties_route.demand.pattern
                        ),
                        "parts_frequency": self.route_frequency[parts_route],
                        "empties_frequency": self.route_frequency[empties_route],
                        "parts_total_cost": self.route_total_cost[parts_route],
                        "empties_total_cost": self.route_total_cost[empties_route],
                        "parts_roundtrip_total_cost": self.route_roundtrip_total_cost[
                            parts_route
                        ],
                        "empties_roundtrip_total_cost": self.route_roundtrip_total_cost[
                            empties_route
                        ],
                    }
                )

    def run_conservative_lp_route_pruning(
            self,
            *,
            lp_value_epsilon: float = 1e-6,
            reduced_cost_floor: float = 50.0,
            reduced_cost_ratio: float = 0.02,
            keep_top_n_per_shipper: int = 60,
            solver=None,
    ) -> None:
        """
        Conservative LP-based pruning pass.

        A route is kept if ANY of these holds:
        - LP relaxation uses it (lp_value > lp_value_epsilon)
        - its reduced cost is small enough:
            reduced_cost <= max(reduced_cost_floor, reduced_cost_ratio * total_cost)
        - it is among the top-N routes for at least one covered shipper,
          ranked by (reduced cost, -lp_value, total_cost, stable key)

        This is intentionally conservative to reduce risk of removing
        routes that may matter in the integer solve.
        """

        if not self.parts_routes and not self.empties_routes:
            return

        self.progress_tracker("Running conservative LP-based route pruning pass")

        lp_result = self._solve_lp_relaxation_for_pruning(solver=solver)
        if lp_result["status"] != "Optimal":
            self.progress_tracker(
                f"Skipping LP pruning because relaxation status is {lp_result['status']}"
            )
            return

        parts_lp_values = lp_result["parts_lp_values"]
        empties_lp_values = lp_result["empties_lp_values"]
        parts_reduced_costs = lp_result["parts_reduced_costs"]
        empties_reduced_costs = lp_result["empties_reduced_costs"]

        kept_parts_routes = self._select_routes_to_keep_from_lp(
            routes=self.parts_routes,
            shippers=self.parts_shippers,
            lp_values=parts_lp_values,
            reduced_costs=parts_reduced_costs,
            lp_value_epsilon=lp_value_epsilon,
            reduced_cost_floor=reduced_cost_floor,
            reduced_cost_ratio=reduced_cost_ratio,
            keep_top_n_per_shipper=keep_top_n_per_shipper,
        )
        kept_empties_routes = self._select_routes_to_keep_from_lp(
            routes=self.empties_routes,
            shippers=self.empties_shippers,
            lp_values=empties_lp_values,
            reduced_costs=empties_reduced_costs,
            lp_value_epsilon=lp_value_epsilon,
            reduced_cost_floor=reduced_cost_floor,
            reduced_cost_ratio=reduced_cost_ratio,
            keep_top_n_per_shipper=keep_top_n_per_shipper,
        )

        removed_parts = len(self.parts_routes) - len(kept_parts_routes)
        removed_empties = len(self.empties_routes) - len(kept_empties_routes)

        self.parts_routes = kept_parts_routes
        self.empties_routes = kept_empties_routes

        filtered_cache_keys = (
                self.parts_routes
                | self.empties_routes
                | self.fixed_parts_routes
                | self.fixed_empties_routes
        )

        self.route_frequency = {
            route: value
            for route, value in self.route_frequency.items()
            if route in filtered_cache_keys
        }
        self.route_total_cost = {
            route: value
            for route, value in self.route_total_cost.items()
            if route in filtered_cache_keys
        }
        self.route_roundtrip_total_cost = {
            route: value
            for route, value in self.route_roundtrip_total_cost.items()
            if route in filtered_cache_keys
        }
        self.route_pair_delta = {
            route: value
            for route, value in self.route_pair_delta.items()
            if route in filtered_cache_keys
        }

        self.rebuild_route_group_indexes()
        self.build_feasible_pair_allocations()

        self.progress_tracker(
            f"LP pruning removed {removed_parts} parts routes and "
            f"{removed_empties} empties routes"
        )

    def _solve_lp_relaxation_for_pruning(self, solver=None) -> dict:
        sorted_parts_routes = sorted(self.parts_routes, key=self._stable_route_key)
        sorted_empties_routes = sorted(self.empties_routes, key=self._stable_route_key)
        sorted_pairs = sorted(
            self.feasible_pair_allocations,
            key=lambda pair: (
                self._stable_route_key(pair[0]),
                self._stable_route_key(pair[1]),
            ),
        )

        lp_model = pulp.LpProblem("Atomic_Route_Allocation_LP_Prune", pulp.LpMinimize)

        use_parts_route = pulp.LpVariable.dicts(
            name="use_parts_route_lp_prune",
            indices=sorted_parts_routes,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        use_empties_route = pulp.LpVariable.dicts(
            name="use_empties_route_lp_prune",
            indices=sorted_empties_routes,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        pair_frequency = pulp.LpVariable.dicts(
            name="pair_frequency_lp_prune",
            indices=sorted_pairs,
            lowBound=0,
            cat="Continuous",
        )

        lp_model += (
                pulp.lpSum(
                    self.route_total_cost[r] * use_parts_route[r]
                    for r in sorted_parts_routes
                )
                + pulp.lpSum(
            self.route_total_cost[r] * use_empties_route[r]
            for r in sorted_empties_routes
        )
                - pulp.lpSum(
            self.pair_saving_per_frequency[pair] * pair_frequency[pair]
            for pair in sorted_pairs
        )
        )

        for shipper in sorted(
                self.parts_shippers, key=lambda s: getattr(s, "id", str(s))
        ):
            lp_model += (
                    pulp.lpSum(
                        use_parts_route[route]
                        for route in sorted_parts_routes
                        if shipper in route.demand.pattern.shippers
                    )
                    == 1
            )

        for shipper in sorted(
                self.empties_shippers, key=lambda s: getattr(s, "id", str(s))
        ):
            lp_model += (
                    pulp.lpSum(
                        use_empties_route[route]
                        for route in sorted_empties_routes
                        if shipper in route.demand.pattern.shippers
                    )
                    == 1
            )

        for parts_route in sorted_parts_routes:
            lp_model += (
                    pulp.lpSum(
                        pair_frequency[pair]
                        for pair in self.pairs_by_parts_route.get(parts_route, [])
                    )
                    <= self.route_frequency[parts_route] * use_parts_route[parts_route]
            )

        for empties_route in sorted_empties_routes:
            lp_model += (
                    pulp.lpSum(
                        pair_frequency[pair]
                        for pair in self.pairs_by_empties_route.get(empties_route, [])
                    )
                    <= self.route_frequency[empties_route] * use_empties_route[empties_route]
            )

        for fixed_parts_route in sorted(
                self.fixed_parts_routes, key=self._stable_route_key
        ):
            lp_model += (
                    pulp.lpSum(
                        pair_frequency[pair]
                        for pair in self.pairs_by_parts_route.get(fixed_parts_route, [])
                    )
                    <= self.route_frequency[fixed_parts_route]
            )

        for fixed_empties_route in sorted(
                self.fixed_empties_routes, key=self._stable_route_key
        ):
            lp_model += (
                    pulp.lpSum(
                        pair_frequency[pair]
                        for pair in self.pairs_by_empties_route.get(fixed_empties_route, [])
                    )
                    <= self.route_frequency[fixed_empties_route]
            )

        if solver is None:
            solver = pulp.PULP_CBC_CMD(msg=False)

        lp_model.solve(solver)
        status = pulp.LpStatus[lp_model.status]

        return {
            "status": status,
            "parts_lp_values": {
                route: float(pulp.value(var) or 0.0)
                for route, var in use_parts_route.items()
            },
            "empties_lp_values": {
                route: float(pulp.value(var) or 0.0)
                for route, var in use_empties_route.items()
            },
            "parts_reduced_costs": {
                route: float(var.dj or 0.0)
                for route, var in use_parts_route.items()
            },
            "empties_reduced_costs": {
                route: float(var.dj or 0.0)
                for route, var in use_empties_route.items()
            },
            "pair_lp_values": {
                pair: float(pulp.value(var) or 0.0)
                for pair, var in pair_frequency.items()
            },
            "pair_reduced_costs": {
                pair: float(var.dj or 0.0)
                for pair, var in pair_frequency.items()
            },
        }

    def _select_routes_to_keep_from_lp(
            self,
            *,
            routes: set[DirectRoute],
            shippers: set[Shipper],
            lp_values: dict[DirectRoute, float],
            reduced_costs: dict[DirectRoute, float],
            lp_value_epsilon: float,
            reduced_cost_floor: float,
            reduced_cost_ratio: float,
            keep_top_n_per_shipper: int,
    ) -> set[DirectRoute]:
        kept_routes = set()

        def reduced_cost_threshold(route: DirectRoute) -> float:
            return max(
                reduced_cost_floor,
                reduced_cost_ratio * self.route_total_cost[route],
            )

        def ranking_key(route: DirectRoute) -> tuple:
            rc = reduced_costs.get(route, 0.0)
            lp = lp_values.get(route, 0.0)
            return (
                rc,
                -lp,
                self.route_frequency[route],
                self.route_total_cost[route],
                self._stable_route_key(route),
            )

        # Global conservative keep rules
        for route in routes:
            lp_value = lp_values.get(route, 0.0)
            reduced_cost = reduced_costs.get(route, 0.0)

            if lp_value > lp_value_epsilon:
                kept_routes.add(route)
                continue

            if reduced_cost <= reduced_cost_threshold(route):
                kept_routes.add(route)

        # Per-shipper safety net: always keep top-N competitive routes
        sorted_routes = sorted(routes, key=ranking_key)

        for shipper in shippers:
            shipper_routes = [
                route
                for route in sorted_routes
                if shipper in route.demand.pattern.shippers
            ]
            kept_routes.update(shipper_routes[:keep_top_n_per_shipper])

        return kept_routes

    def run_conservative_lp_pair_pruning(
        self,
        *,
        lp_value_epsilon: float = 1e-6,
        reduced_cost_floor: float = 20.0,
        reduced_cost_ratio: float = 0.05,
        keep_top_n_per_parts_route: int = 8,
        keep_top_n_per_empties_route: int = 8,
        keep_top_n_by_saving_per_parts_route: int = 6,
        keep_top_n_by_saving_per_empties_route: int = 6,
        solver=None,
    ) -> None:
        """
        Conservative LP-based pruning pass for pair variables.

        A pair is kept if ANY of these holds:
        - LP relaxation uses it (lp_value > lp_value_epsilon)
        - its reduced cost is small enough:
            reduced_cost <= max(reduced_cost_floor, reduced_cost_ratio * pair_saving)
        - it is among the top-N pairs for either incident route by reduced-cost ranking
        - it is among the top-N pairs for either incident route by raw saving

        This is intentionally conservative to reduce risk of removing
        useful roundtrip opportunities.
        """

        if not self.feasible_pair_allocations:
            return

        self.progress_tracker("Running conservative LP-based pair pruning pass")

        lp_result = self._solve_lp_relaxation_for_pruning(solver=solver)
        if lp_result["status"] != "Optimal":
            self.progress_tracker(
                f"Skipping LP pair pruning because relaxation status is {lp_result['status']}"
            )
            return

        pair_lp_values = lp_result["pair_lp_values"]
        pair_reduced_costs = lp_result["pair_reduced_costs"]

        kept_pairs = self._select_pairs_to_keep_from_lp(
            pairs=self.feasible_pair_allocations,
            pair_lp_values=pair_lp_values,
            pair_reduced_costs=pair_reduced_costs,
            lp_value_epsilon=lp_value_epsilon,
            reduced_cost_floor=reduced_cost_floor,
            reduced_cost_ratio=reduced_cost_ratio,
            keep_top_n_per_parts_route=keep_top_n_per_parts_route,
            keep_top_n_per_empties_route=keep_top_n_per_empties_route,
            keep_top_n_by_saving_per_parts_route=keep_top_n_by_saving_per_parts_route,
            keep_top_n_by_saving_per_empties_route=keep_top_n_by_saving_per_empties_route,
        )

        removed_pairs = len(self.feasible_pair_allocations) - len(kept_pairs)

        self.feasible_pair_allocations = sorted(
            kept_pairs,
            key=lambda pair: (
                self._stable_route_key(pair[0]),
                self._stable_route_key(pair[1]),
            ),
        )

        self.pair_saving_per_frequency = {
            pair: value
            for pair, value in self.pair_saving_per_frequency.items()
            if pair in kept_pairs
        }

        self.pairs_by_parts_route.clear()
        self.pairs_by_empties_route.clear()
        for pair in self.feasible_pair_allocations:
            parts_route, empties_route = pair
            self.pairs_by_parts_route[parts_route].append(pair)
            self.pairs_by_empties_route[empties_route].append(pair)

        self.progress_tracker(f"LP pair pruning removed {removed_pairs} pair allocations")

    def _select_pairs_to_keep_from_lp(
        self,
        *,
        pairs: list[tuple[DirectRoute, DirectRoute]],
        pair_lp_values: dict[tuple[DirectRoute, DirectRoute], float],
        pair_reduced_costs: dict[tuple[DirectRoute, DirectRoute], float],
        lp_value_epsilon: float,
        reduced_cost_floor: float,
        reduced_cost_ratio: float,
        keep_top_n_per_parts_route: int,
        keep_top_n_per_empties_route: int,
        keep_top_n_by_saving_per_parts_route: int,
        keep_top_n_by_saving_per_empties_route: int,
    ) -> set[tuple[DirectRoute, DirectRoute]]:
        kept_pairs: set[tuple[DirectRoute, DirectRoute]] = set()

        def reduced_cost_threshold(pair: tuple[DirectRoute, DirectRoute]) -> float:
            saving = self.pair_saving_per_frequency[pair]
            return max(reduced_cost_floor, reduced_cost_ratio * saving)

        def pair_rank_key(pair: tuple[DirectRoute, DirectRoute]) -> tuple:
            rc = pair_reduced_costs.get(pair, 0.0)
            lp = pair_lp_values.get(pair, 0.0)
            parts_route, empties_route = pair
            return (
                rc,
                -lp,
                -self.pair_saving_per_frequency[pair],
                self.route_frequency[parts_route] + self.route_frequency[empties_route],
                self._stable_route_key(parts_route),
                self._stable_route_key(empties_route),
            )

        def saving_rank_key(pair: tuple[DirectRoute, DirectRoute]) -> tuple:
            parts_route, empties_route = pair
            return (
                -self.pair_saving_per_frequency[pair],
                pair_reduced_costs.get(pair, 0.0),
                -pair_lp_values.get(pair, 0.0),
                self.route_frequency[parts_route] + self.route_frequency[empties_route],
                self._stable_route_key(parts_route),
                self._stable_route_key(empties_route),
            )

        # Global conservative keep rules
        for pair in pairs:
            lp_value = pair_lp_values.get(pair, 0.0)
            reduced_cost = pair_reduced_costs.get(pair, 0.0)

            if lp_value > lp_value_epsilon:
                kept_pairs.add(pair)
                continue

            if reduced_cost <= reduced_cost_threshold(pair):
                kept_pairs.add(pair)

        # Per-parts-route safety net by reduced-cost competitiveness
        for parts_route, route_pairs in self.pairs_by_parts_route.items():
            ranked_pairs = sorted(route_pairs, key=pair_rank_key)
            kept_pairs.update(ranked_pairs[:keep_top_n_per_parts_route])

        # Per-empties-route safety net by reduced-cost competitiveness
        for empties_route, route_pairs in self.pairs_by_empties_route.items():
            ranked_pairs = sorted(route_pairs, key=pair_rank_key)
            kept_pairs.update(ranked_pairs[:keep_top_n_per_empties_route])

        # Per-route safety net by raw savings
        for parts_route, route_pairs in self.pairs_by_parts_route.items():
            ranked_pairs = sorted(route_pairs, key=saving_rank_key)
            kept_pairs.update(ranked_pairs[:keep_top_n_by_saving_per_parts_route])

        for empties_route, route_pairs in self.pairs_by_empties_route.items():
            ranked_pairs = sorted(route_pairs, key=saving_rank_key)
            kept_pairs.update(ranked_pairs[:keep_top_n_by_saving_per_empties_route])

        return kept_pairs