"""
Solver orchestration for route optimization.

This module contains the high-level optimization flow used to generate
and optimized operational routes for the current project scenario.

The optimization is split into two subproblems:

- Milk run shippers: solved through a mixed-integer optimization model that
  selects the cheapest combination of feasible multi-stop routes while
  covering each eligible shipper exactly once.
- FTL-exclusive shippers: solved deterministically by creating single-shipper
  patterns and selecting the cheapest vehicle/tariff option for each one.

Locked routes from the scenario are preserved as preselected direct routes and
participate in final trip assembly, including roundtrip pairing where possible.
Shippers already covered by locked routes are excluded from optimization.
User-blocked route patterns are also excluded from candidate generation.
"""
from collections import defaultdict

import pulp

from domain.domain_algorithms import make_haversine_cache, get_deviation_bin
from domain.data_structures import Plant
from domain.exceptions import NonOptimalSolutionError
from domain.project import Project
from domain.routes.direct_route import DirectRoute
from domain.shipper import Shipper
from domain.routes.route_pattern import RoutePattern
from domain.trip import Trip
from services.roundtrip_combination_algorithm import iterate_trip_combination
from services.route_pattern_creation_iterator import iterate_creation_of_route_patterns
from services.tariff_service import TariffService
from services.vehicle_permutation_service import VehiclePermutationService


def _group_key(route: DirectRoute) -> tuple:
    return route.carrier.group, route.vehicle.id, route.starting_point.zip_code

class Solver:
    def __init__(
            self,
            project: Project,
    ):
        self.project = project
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
            if shipper not in locked_parts_shippers
               and shipper.has_parts_demand
        }
        self.filtered_empties_shippers = {
            shipper
            for shipper in project.current_scenario.empties_direct_shippers.values()
            if shipper not in locked_empties_shippers
               and shipper.has_empties_demand
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
            r.demand.pattern
            for r in project.current_scenario.blocked_routes
        }

        self.vehicle_permutation_service = VehiclePermutationService(project.context.vehicles)

        self.mr_solver: MilkRunSolver = None

    def run(self):
        self.solve_milkrun_shippers()
        self.combine_solutions()
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
        )
        self.mr_solver.build()
        self.mr_solver.solve()

    def combine_solutions(self):
        selected_parts_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)
        selected_empties_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)

        mr_parts_routes = self.mr_solver.solution_parts_routes if self.mr_solver else set()
        mr_empties_routes = self.mr_solver.solution_empties_routes if self.mr_solver else set()

        all_parts_routes = self.locked_parts_routes | mr_parts_routes
        all_empties_routes = self.locked_empties_routes | mr_empties_routes

        for route in all_parts_routes:
            selected_parts_by_group[_group_key(route)].append(route)

        for route in all_empties_routes:
            selected_empties_by_group[_group_key(route)].append(route)

        self.solution_trips = iterate_trip_combination(
            selected_parts_by_group=selected_parts_by_group,
            selected_empties_by_group=selected_empties_by_group,
        )


class MilkRunSolver:
    def __init__(
            self,
            parts_shippers: set[Shipper],
            empties_shippers: set[Shipper],
            existing_trips: set[Trip],
            plant: Plant,
            vehicle_permutation_service: VehiclePermutationService,
            tariffs_service: TariffService,
            blocked_patterns: set[RoutePattern] | None = None,
            fixed_parts_routes: set[DirectRoute] | None = None,
            fixed_empties_routes: set[DirectRoute] | None = None,
    ):
        self.parts_shippers = parts_shippers
        self.empties_shippers = empties_shippers
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

        self.ftl_parts_shippers = {s for s in self.parts_shippers if s.is_ftl_exclusive_parts}
        self.ftl_empties_shippers = {s for s in self.empties_shippers if s.is_ftl_exclusive_empties}
        self.mr_parts_shippers = {s for s in self.parts_shippers if not s.is_ftl_exclusive_parts}
        self.mr_empties_shippers = {s for s in self.empties_shippers if not s.is_ftl_exclusive_empties}

        self.parts_patterns: set[RoutePattern] = set()
        self.empties_patterns: set[RoutePattern] = set()
        self.parts_routes: set[DirectRoute] = set()
        self.empties_routes: set[DirectRoute] = set()

        self.roundtrip_groups: list[tuple] = []
        self.parts_routes_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)
        self.empties_routes_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)
        self.roundtrip_saving_by_group: dict[tuple, int] = defaultdict(int)

        self.model = None
        self.use_parts_route_bin = None
        self.use_empties_route_bin = None
        self.roundtrips_by_group = None
        self.fixed_parts_frequency_by_group = None
        self.fixed_empties_frequency_by_group = None

        self.solve_status = "Not Solved Yet"
        self.solution_parts_routes = set()
        self.solution_empties_routes = set()
        self.solution_trips = set()

    @property
    def all_patterns(self):
        """
        Return the union of all generated route patterns across both flows.
        """
        return self.parts_patterns.union(self.empties_patterns)

    def build(self):
        """
        Prepare the optimization model and all candidate inputs.

        This method generates route patterns, applies ordering and deviation
        filtering, expands patterns into operational routes, assigns tariffs,
        computes roundtrip savings by group, and builds the MILP model used in
        `solve()`.
        """
        self.generate_route_patterns()
        self.apply_ordering_to_route_patterns()
        self.remove_high_deviation_route_patterns()

        new_parts_routes = self.vehicle_permutation_service.permutate(self.parts_patterns)
        self.tariffs_service.assign_ftl_mr_routes(new_parts_routes)
        self.parts_routes = {r for r in new_parts_routes if r.total_cost > 0}

        new_empties_routes = self.vehicle_permutation_service.permutate(self.empties_patterns)
        self.tariffs_service.assign_ftl_mr_routes(new_empties_routes)
        self.empties_routes = {r for r in new_empties_routes if r.total_cost > 0}

        for r in self.parts_routes:
            key = (r.carrier.group, r.vehicle.id, r.starting_point.zip_code)
            self.parts_routes_by_group[key].append(r)

        for r in self.empties_routes:
            key = (r.carrier.group, r.vehicle.id, r.starting_point.zip_code)
            self.empties_routes_by_group[key].append(r)

        fixed_groups = {
            _group_key(r) for r in (self.fixed_parts_routes | self.fixed_empties_routes)
        }
        self.roundtrip_groups = (
                set(self.parts_routes_by_group.keys())
                | set(self.empties_routes_by_group.keys())
                | fixed_groups
        )

        self.get_roundtrip_savings_by_group()
        self.fixed_parts_frequency_by_group = defaultdict(int)
        for r in self.fixed_parts_routes:
            self.fixed_parts_frequency_by_group[_group_key(r)] += r.frequency

        self.fixed_empties_frequency_by_group = defaultdict(int)
        for r in self.fixed_empties_routes:
            self.fixed_empties_frequency_by_group[_group_key(r)] += r.frequency


        self.build_model()

    def solve(self):
        """
        Solve the prepared optimization model and convert the result into trips.

        The solver first selects parts and empties routes through the MILP,
        converts the active binary variables into route sets, and then combines
        those routes into operational trips with roundtrip pairing where possible.
        """
        self.solve_model()
        self.convert_solutions()

    def generate_route_patterns(self) -> None:
        carriers = {s.carrier.group for s in self.parts_shippers | self.empties_shippers}
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

    def apply_ordering_to_route_patterns(self):
        """
        Order shipper visits and compute deviation for all patterns.

        A cached haversine distance function is used so the same distance
        calculation can be reused across multiple patterns efficiently.
        """
        distance_function = make_haversine_cache()
        for pattern in self.all_patterns:
            pattern.order_shippers(distance_function)
            pattern.calculate_deviation(distance_function)

    def remove_high_deviation_route_patterns(self):
        """
        Remove patterns whose deviation exceeds the accepted threshold.

        This reduces the number of candidate routes before vehicle permutation
        and optimization, pruning patterns considered operationally undesirable.
        The current threshold is 150.
        """
        parts_patterns_to_remove = {p for p in self.parts_patterns if p.deviation > 150}
        for pattern in parts_patterns_to_remove:
            self.parts_patterns.remove(pattern)

        empties_patterns_to_remove = {p for p in self.empties_patterns if p.deviation > 150}
        for pattern in empties_patterns_to_remove:
            self.empties_patterns.remove(pattern)

    def get_roundtrip_savings_by_group(self):
        """
        Load roundtrip savings for each eligible operational group.

        Savings are looked up from FTL tariffs using a grouping key composed of
        carrier group, vehicle, deviation bin, route origin zip code, and plant.
        If no tariff is found for a group, no savings are applied for that group.
        """
        tariffs_dict = self.tariffs_service.ftl_tariffs
        for group in self.roundtrip_groups:
            tariff = tariffs_dict.get(
                (group[0], group[1], get_deviation_bin(35)[0], group[2], self.plant.cofor)
            )
            if tariff:
                self.roundtrip_saving_by_group[group] = tariff.get_roundtrip_savings()

    def build_model(self):
        """
        Build the mixed-integer optimization model.

        Decision variables:
            use_parts_route_bin[route]:
                1 if a parts route is selected, 0 otherwise.
            use_empties_route_bin[route]:
                1 if an empties route is selected, 0 otherwise.
            roundtrips_by_group[group]:
                Integer number of roundtrips allocated to an operational group.

        Objective:
            Minimize total selected route cost minus roundtrip savings.

        Constraints:
            - Every parts shipper must be covered by exactly one selected parts route.
            - Every empties shipper must be covered by exactly one selected empties route.
            - Roundtrips allocated to a group cannot exceed selected parts frequency
              for that group.
            - Roundtrips allocated to a group cannot exceed selected empties
              frequency for that group.
        """
        self.model = pulp.LpProblem("Atomic_Route_Allocation", pulp.LpMinimize)

        self.use_parts_route_bin = pulp.LpVariable.dicts(
            name="use_parts_route",
            indices=self.parts_routes,
            cat="Binary"
        )

        self.use_empties_route_bin = pulp.LpVariable.dicts(
            name="use_empties_route",
            indices=self.empties_routes,
            cat="Binary"
        )

        self.roundtrips_by_group = pulp.LpVariable.dicts(
            name="roundtrips_by_group",
            indices=list(self.roundtrip_groups),
            lowBound=0,
            cat="Integer"
        )

        max_rt_cost = max(
            [r.roundtrip_total_cost for r in self.parts_routes | self.empties_routes],
            default=0,
        )

        epsilon = 1.0 / (1000 * (1 + max_rt_cost))

        self.model += (
                pulp.lpSum(
                    (r.total_cost + epsilon * r.roundtrip_total_cost) * self.use_parts_route_bin[r]
                    for r in self.parts_routes
                )
                + pulp.lpSum(
            (r.total_cost + epsilon * r.roundtrip_total_cost) * self.use_empties_route_bin[r]
            for r in self.empties_routes
        )
                - pulp.lpSum(
            self.roundtrip_saving_by_group[g] * self.roundtrips_by_group[g]
            for g in self.roundtrip_groups
        )
        )

        for shipper in self.parts_shippers:
            self.model += (
                    pulp.lpSum(
                        self.use_parts_route_bin[route]
                        for route in self.parts_routes
                        if shipper in route.demand.pattern.shippers
                    ) == 1
            )

        for shipper in self.empties_shippers:
            self.model += (
                    pulp.lpSum(
                        self.use_empties_route_bin[route]
                        for route in self.empties_routes
                        if shipper in route.demand.pattern.shippers
                    ) == 1
            )

        for group in self.roundtrip_groups:
            self.model += (
                    self.roundtrips_by_group[group]
                    <= self.fixed_parts_frequency_by_group.get(group, 0)
                    + pulp.lpSum(
                r.frequency * self.use_parts_route_bin[r]
                for r in self.parts_routes_by_group.get(group, [])
            )
            ), f"roundtrip_parts_cap_{group[0]}_{group[1]}_{group[2]}"

            self.model += (
                    self.roundtrips_by_group[group]
                    <= self.fixed_empties_frequency_by_group.get(group, 0)
                    + pulp.lpSum(
                r.frequency * self.use_empties_route_bin[r]
                for r in self.empties_routes_by_group.get(group, [])
            )
            ), f"roundtrip_empties_cap_{group[0]}_{group[1]}_{group[2]}"

    def solve_model(self):
        """
        Solve the MILP model using CBC.

        Raises:
            NonOptimalSolutionError: If the solver does not finish with an
                optimal solution status.
        """
        solver = pulp.PULP_CBC_CMD(msg=True)
        self.model.solve(solver)
        self.solve_status = pulp.LpStatus[self.model.status]
        print("Solve status:", self.solve_status)
        if self.solve_status != "Optimal":
            raise NonOptimalSolutionError()

    def convert_solutions(self):
        """
        Convert selected binary variables into concrete route sets.

        After the MILP is solved, all active parts and empties route decisions
        are collected into `solution_parts_routes` and `solution_empties_routes`.
        """
        self.solution_parts_routes = {
            route for route, var in self.use_parts_route_bin.items()
            if round(pulp.value(var)) == 1
        }
        self.solution_empties_routes = {
            route for route, var in self.use_empties_route_bin.items()
            if round(pulp.value(var)) == 1
        }