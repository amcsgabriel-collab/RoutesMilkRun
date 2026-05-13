from collections import defaultdict

from .direct_routes.roundtrip_combination_algorithm import iterate_trip_combination
from .direct_routes.vehicle_permutation_service import VehiclePermutationService
from .solver import RouteSelectionSolver
from .solver_input_parsing import SolverInputBuilder
from .solver_services import SolverServices
from ...domain.project import Project
from ...domain.routes.direct_route import DirectRoute

def _group_key(route: DirectRoute) -> tuple:
    return route.carrier.group, route.vehicle.id, route.starting_point.zip_code

class SolverCoordinator:
    def __init__(self, project: Project, progress_tracker, solve_hubs: bool, overutilization: dict[str, float], max_stops: int):
        self.project = project
        self.solve_hubs = solve_hubs
        self.inputs = SolverInputBuilder(project, solve_hubs, overutilization, max_stops).build()

        self.vehicle_permutation_service = VehiclePermutationService(project.context.vehicles)
        self._tracker = progress_tracker
        self.tariff_service = self.project.context.tariff_service
        self.hub_assignment_service = self.project.context.hub_assignment_service

        self.services = SolverServices(
            tariff_service=self.tariff_service,
            tracker=self._tracker,
            vehicle_permutation_service=self.vehicle_permutation_service,
            hub_assignment_service=self.hub_assignment_service
        )

        self.solver: RouteSelectionSolver | None = None

        self.solution_trips = set()
        self.solution_hubs = set()

    def run(self):
        self._tracker("solver initialized. Setting up the optimization model...")
        self.run_solver()
        self.combine_solutions()
        self.solution_hubs = self.solver.solution_hubs if self.solver else None
        return self.solution_trips, self.solution_hubs

    def run_solver(self):
        self.solver = RouteSelectionSolver(
            inputs=self.inputs,
            services=self.services,
            solve_hubs=self.solve_hubs,
        )
        self.solver.build()
        self.solver.solve()

    def combine_solutions(self):
        selected_parts_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)
        selected_empties_by_group: dict[tuple, list[DirectRoute]] = defaultdict(list)

        mr_parts_routes = self.solver.solution_parts_routes if self.solver else set()
        mr_empties_routes = (
            self.solver.solution_empties_routes if self.solver else set()
        )

        all_parts_routes = self.inputs.locked_parts_routes | mr_parts_routes
        all_empties_routes = self.inputs.locked_empties_routes | mr_empties_routes

        for route in all_parts_routes:
            selected_parts_by_group[_group_key(route)].append(route)

        for route in all_empties_routes:
            selected_empties_by_group[_group_key(route)].append(route)

        self.solution_trips = iterate_trip_combination(
            selected_parts_by_group=selected_parts_by_group,
            selected_empties_by_group=selected_empties_by_group,
            pair_allocations=(
                self.solver.solution_pair_allocations if self.solver else {}
            ),
        )