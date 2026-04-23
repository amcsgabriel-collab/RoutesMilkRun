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

from collections import defaultdict

import pulp

from domain.data_structures import Plant
from domain.domain_algorithms import make_haversine_cache
from domain.exceptions import NonOptimalSolutionError
from domain.project import Project
from domain.routes.direct_route import DirectRoute
from domain.routes.route_pattern import RoutePattern
from domain.shipper import Shipper
from domain.trip import Trip
from services.roundtrip_combination_algorithm import iterate_trip_combination
from services.route_pattern_creation_iterator import iterate_creation_of_route_patterns
from services.tariff_service import TariffService
from services.vehicle_permutation_service import VehiclePermutationService


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

        self.progress_tracker("Building optimization Model")
        self.build_model()
        self.progress_tracker(
            f"Optimization model ready with {len(self.model.constraints)} constraints"
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
        self.parts_routes = self._remove_dominated_route_set(self.parts_routes)
        self.empties_routes = self._remove_dominated_route_set(self.empties_routes)

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

    def _remove_dominated_route_set(
        self, routes: set[DirectRoute]
    ) -> set[DirectRoute]:
        routes_by_signature: dict[tuple, list[DirectRoute]] = defaultdict(list)
        kept_routes = set()

        for route in routes:
            signature = (
                frozenset(route.demand.pattern.shippers),
                route.vehicle.id,
                route.starting_point.zip_code,
                route.demand.flow_direction,
            )
            routes_by_signature[signature].append(route)

        for same_signature_routes in routes_by_signature.values():
            best_route = min(
                same_signature_routes,
                key=lambda r: (
                    self.route_total_cost[r],
                    self.route_roundtrip_total_cost[r],
                    self.route_frequency[r],
                    hash(r),
                ),
            )
            kept_routes.add(best_route)

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