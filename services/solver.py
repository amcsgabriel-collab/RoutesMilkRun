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

Locked routes from the scenario are preserved and included directly in the
final solution. Shippers already covered by locked routes are excluded from
optimization. User-blocked route patterns are also excluded from candidate
generation.
"""

import pulp

from domain.domain_algorithms import make_haversine_cache
from domain.data_structures import Plant
from domain.exceptions import NonOptimalSolutionError
from domain.project import Project
from domain.routes.direct_route import DirectRoute
from domain.shipper import Shipper
from domain.routes.route_pattern import RoutePattern
from services.route_pattern_creation_iterator import iterate_creation_of_route_patterns
from services.tariff_service import TariffService
from services.vehicle_permutation_service import VehiclePermutationService


class Solver:
    """
    Coordinate route solving for the currently selected project scenario.

    This class is the main entry point for optimization. It prepares the
    scenario-specific inputs, separates shippers by solving strategy, runs the
    dedicated solvers, and merges their results with already locked routes.

    Responsibilities:
    - Read the active region and scenario from the project metadata
    - Exclude shippers already covered by locked routes
    - Split remaining shippers into milk run and FTL-exclusive groups
    - Run the corresponding specialized solvers
    - Merge optimized routes with locked routes into the final solution

    Attributes:
        project: Project object that contains all project context data.
        filtered_shippers: Direct shippers not already covered by locked routes.
        ftl_shippers: Subset of filtered shippers that must be served by FTL.
        mr_shippers: Subset of filtered shippers eligible for milk run solving.
        solution_routes: Final set of routes, initialized with locked routes.
        blocked_patterns: Route patterns explicitly forbidden by the user.
    """

    def __init__(
            self,
            project: Project,
    ):
        self.project = project
        locked_shippers = {
            shipper
            for route in project.current_scenario.locked_routes
            for shipper in route.pattern.shippers
        }
        self.filtered_shippers = {
            shipper
            for shipper in project.current_scenario.direct_shippers.values()
            if shipper not in locked_shippers
               and shipper.has_demand
        }
        self.ftl_shippers = {s for s in self.filtered_shippers if s.is_ftl_exclusive_shipper}
        self.mr_shippers = {s for s in self.filtered_shippers if not s.is_ftl_exclusive_shipper}
        self.solution_routes = set(project.current_scenario.locked_routes.copy())
        self.blocked_patterns = {r.pattern for r in project.current_scenario.blocked_routes}
        self.vehicle_permutation_service = VehiclePermutationService(project.context.vehicles)

        self.mr_solver: MilkRunSolver = None
        self.ftl_solver: FtlSolver = None

    @property
    def tariffs_service(self):
        return self.project.context.tariffs_service

    @property
    def plant(self):
        return self.project.context.plant

    def run(self):
        """
        Execute the full optimization flow for the current scenario.

        Returns:
            Set of operational routes including locked routes, optimized milk run
            routes, and optimized FTL routes.
        """
        self.solve_milkrun_shippers()
        self.solve_ftl_shippers()
        self.combine_solutions()
        return self.solution_routes

    def solve_milkrun_shippers(self):
        """
        Solve all non-FTL-exclusive shippers using the milk run optimization model.

        Existing routes from the AS-IS scenario are passed in so their route
        patterns can be reused when the same shipper combination already exists.
        This preserves route metadata such as route names where applicable.
        """
        self.mr_solver = MilkRunSolver(
            shippers=self.mr_shippers,
            existing_routes=self.project.current_region.scenarios["AS-IS"].routes,
            plant=self.plant,
            vehicle_permutation_service=self.vehicle_permutation_service,
            tariffs_service=self.tariffs_service,
            blocked_patterns=self.blocked_patterns
        )
        self.mr_solver.build()
        self.mr_solver.solve()

    def solve_ftl_shippers(self):
        """
        Solve FTL-exclusive shippers using single-shipper route patterns.

        Each shipper is modeled as its own route pattern and later assigned the
        cheapest feasible operational route after vehicle permutation and tariff
        assignment.
        """
        self.ftl_solver = FtlSolver(
            shippers=self.ftl_shippers,
            plant=self.plant,
            vehicle_permutation_service=self.vehicle_permutation_service,
            tariffs_service=self.tariffs_service,
            existing_routes=self.project.current_region.scenarios["AS-IS"].routes
        )
        self.ftl_solver.build()
        self.ftl_solver.solve()

    def combine_solutions(self):
        """
        Merge locked, milk run, and FTL route solutions into one final route set.
        """
        self.solution_routes = self.solution_routes.union(
            self.mr_solver.solution_routes.union(
                self.ftl_solver.solution_routes))


class MilkRunSolver:
    """
    Solve a milk run routing problem for a set of eligible shippers.

    This solver generates feasible multi-stop route patterns, expands them into
    operational routes through vehicle permutations and tariff assignment, and
    then solves a binary optimization model to select the minimum-cost set of
    routes.

    The model enforces exact shipper coverage: every shipper in the input set
    must be covered by exactly one selected route.

    Solver lifecycle:
    1. Generate route patterns grouped by carrier
    2. Order shipper visits and compute route deviation
    3. Remove patterns with excessive deviation
    4. Generate operational routes via vehicle permutations
    5. Assign tariffs and calculate total route cost
    6. Build and solve the MILP model minimizing costs
    7. Convert selected decision variables into solution routes

    Notes:
        - Existing route patterns may be reused to preserve stable metadata
          such as route names.
        - Blocked patterns are excluded before route generation continues.
        - Only shippers within the same carrier group may be grouped together.
    """
    patterns: set[RoutePattern]
    routes: set[DirectRoute]

    def __init__(
            self,
            shippers: set[Shipper],
            existing_routes: set[DirectRoute],
            plant: Plant,
            vehicle_permutation_service: VehiclePermutationService,
            tariffs_service: TariffService,
            blocked_patterns: set[RoutePattern] | None = None,
    ):
        """
        Initialize a milk run solver for a shipper subset.

        Args:
            shippers: Shippers to be covered by the solver.
            existing_routes: Previously known routes whose patterns may be reused.
            plant: Plant serving as the route origin/end point.
            vehicle_permutation_service: Service used to expand route patterns into
                feasible vehicle-specific operational routes.
            tariffs_service: Service used to assign tariffs and cost to routes.
            blocked_patterns: Route patterns that must not be generated or reused.
        """
        self.shippers = shippers
        self.existing_routes = existing_routes
        self.existing_patterns = {r.pattern for r in self.existing_routes}
        self.plant = plant
        self.vehicle_permutation_service = vehicle_permutation_service
        self.tariffs_service = tariffs_service
        self.blocked_patterns = blocked_patterns
        self.patterns = set()
        self.routes = set()

        self.model = None
        self.use_route_bin = None
        self.solve_status = "Not Solved Yet"
        self.solution_routes = set()

    def build(self):
        """
        Prepare the optimization problem.

        This method generates candidate route patterns, filters infeasible or
        undesirable ones, converts them into priced operational routes, and builds
        the MILP model used in `solve()`.
        """
        self.generate_route_patterns()
        self.apply_ordering_to_route_patterns()
        self.remove_high_deviation_route_patterns()
        new_routes = self.vehicle_permutation_service.permutate(self.patterns)
        self.tariffs_service.assign_ftl_mr_routes(new_routes)
        self.routes = {r for r in new_routes if r.total_cost > 0}
        self.build_model()

    def solve(self):
        """
        Solve the prepared MILP model and convert the selected variables into
        operational routes.
        """
        self.solve_model()
        self.convert_solutions()

    def generate_route_patterns(self):
        """
        Generate candidate route patterns for milk run optimization.

        Route patterns are created separately per carrier group, since shippers
        from different carrier groups cannot be combined into the same pattern.

        Existing patterns are reused when a generated shipper combination already
        exists in `existing_routes`, preserving stable route metadata such as
        route names.
        """
        carriers = {s.carrier.group for s in self.shippers}
        for carrier in carriers:
            carrier_shippers = {s for s in self.shippers if s.carrier.group == carrier}
            self.patterns |= iterate_creation_of_route_patterns(
                shippers=carrier_shippers,
                existing_patterns=self.existing_patterns,
                plant=self.plant,
                blocked_combinations=self.blocked_patterns
            )

    def apply_ordering_to_route_patterns(self):
        """
        Order shipper visits within each pattern and compute route deviation.

        Ordering and deviation are computed using a cached haversine distance
        function to avoid repeated distance calculations across patterns.
        """
        distance_function = make_haversine_cache()
        for pattern in self.patterns:
            pattern.order_shippers(distance_function)
            pattern.calculate_deviation(distance_function)

    def remove_high_deviation_route_patterns(self):
        """
        Remove route patterns whose deviation exceeds the accepted threshold.

        This acts as a pruning step before vehicle permutation and optimization,
        reducing model size and excluding operationally undesirable patterns.
        """
        patterns_to_remove = {p for p in self.patterns if p.deviation > 150}
        for pattern in patterns_to_remove:
            self.patterns.remove(pattern)

    def build_model(self):
        """
        Build the binary linear optimization model for route selection.

        Decision variables:
            use_route_bin[route] = 1 if the route is selected, else 0.

        Objective:
            Minimize total route cost across all selected routes.

        Constraints:
            Each input shipper must be covered by exactly one selected route.
        """
        self.model = pulp.LpProblem("Atomic_Route_Allocation", pulp.LpMinimize)
        self.use_route_bin = pulp.LpVariable.dicts(
            name="use_route",
            indices=self.routes,
            cat="Binary"
        )

        # Model Objective: Minimize following function
        # The first non-constraining expression is the objective.
        self.model += pulp.lpSum(r.total_cost * self.use_route_bin[r] for r in self.routes)

        # Coverage constraint
        for shipper in self.shippers:
            self.model += pulp.lpSum(
                self.use_route_bin[route] for route in self.routes if shipper in route.pattern.shippers
            ) == 1

    def solve_model(self):
        """
        Solve the MILP model using CBC.

        Raises:
            NonOptimalSolutionError: If the solver does not return an optimal
                solution status.
        """
        solver = pulp.PULP_CBC_CMD(msg=True)
        self.model.solve(solver)
        self.solve_status = pulp.LpStatus[self.model.status]
        print("Solve status:", self.solve_status)
        if self.solve_status != "Optimal":
            raise NonOptimalSolutionError()

    def convert_solutions(self):
        """
        Convert binary decision variable values into the final selected route set.
        """
        self.solution_routes = {
            route for route, var in self.use_route_bin.items()
            if round(pulp.value(var)) == 1
        }


class FtlSolver:
    """
    Solve routing for FTL-exclusive shippers.

    Unlike the milk run solver, this solver does not build an optimization
    model. Each shipper is assigned to a single-stop route pattern, expanded
    into candidate operational routes, priced, and then reduced to the
    cheapest route per pattern.

    This solver is intended for shippers that must not be grouped into a
    multi-stop milk run.
    """
    def __init__(
            self,
            shippers: set[Shipper],
            plant: Plant,
            vehicle_permutation_service: VehiclePermutationService,
            tariffs_service: TariffService,
            existing_routes: set[DirectRoute]
    ):
        self.shippers = shippers
        self.plant = plant
        self.vehicle_permutation_service = vehicle_permutation_service
        self.tariffs_service = tariffs_service
        self.distance_function = make_haversine_cache()
        self.existing_ftl_routes = {r for r in existing_routes if r.pattern.transport_concept == "FTL"}

        self.patterns = set()
        self.routes = set()
        self.solution_routes = set()

    def build(self):
        """
        Generate and price candidate FTL routes for the input shippers.
        """
        self.build_patterns()
        new_routes = self.vehicle_permutation_service.permutate(self.patterns)
        self.tariffs_service.assign_ftl_mr_routes(new_routes)
        self.routes = {r for r in new_routes if r.total_cost > 0}

    def solve(self):
        """
        Select the cheapest priced route for each single-shipper pattern.
        """
        best_routes = {}
        for route in self.routes:
            pattern = route.pattern
            if pattern not in best_routes or route.total_cost < best_routes[pattern].total_cost:
                best_routes[pattern] = route
        self.solution_routes = set(best_routes.values())

    def build_patterns(self):
        """
        Create one single-shipper route pattern per shipper and compute its order
        and deviation metadata.
        """

        existing_patterns_by_shipper = {next(iter(r.pattern.shippers)): r.pattern.copy() for r in self.existing_ftl_routes}
        for shipper in self.shippers:
            if shipper in existing_patterns_by_shipper:
                pattern = existing_patterns_by_shipper[shipper]
                pattern.reset_allocation()
            else:
                pattern = RoutePattern({shipper}, self.plant)
                pattern.is_new_pattern = True
                pattern.order_shippers(self.distance_function)
                pattern.calculate_deviation(self.distance_function)

            self.patterns.add(pattern)
