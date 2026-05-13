from .direct_routes.lp_pruner import LpPruner
from .direct_routes.roundtrip_pair_savings_builder import RoundtripPairSavingsBuilder
from .direct_routes.route_cache_builder import RouteCacheBuilder
from .direct_routes.route_candidate_builder import RouteCandidateBuilder
from .direct_routes.route_dominance_filter import RouteDominanceFilter
from .hubs.hub_option_builder import HubOptionBuilder
from .model_builder import ModelBuilder
from .pre_solve_validator import SolverFeasibilityValidator
from .solutions_builder import SolutionsBuilder
from .solver_input_parsing import SolverInputs
from .solver_services import SolverServices
from .solver_shipper_classifier import ShipperClassifier
from .solver_state import MilkRunSolverState
from ...domain.regional_hub_view import HubLike
from ...domain.routes.direct_route import DirectRoute



class RouteSelectionSolver:
    def __init__(
            self,
            inputs: SolverInputs,
            services: SolverServices,
            solve_hubs: bool,
    ) -> tuple[set[DirectRoute], set[HubLike]]:

        self.inputs = inputs

        self.vehicle_permutation_service = services.vehicle_permutation_service
        self.tariffs_service = services.tariff_service
        self.hub_assignment_service = services.hub_assignment_service
        self._tracker = services.tracker
        self.solve_hubs = solve_hubs

        self.state = MilkRunSolverState()

        self.shipper_classifier = ShipperClassifier(inputs=inputs, state=self.state, tracker=self._tracker)
        self.hub_option_builder = HubOptionBuilder(inputs=inputs, services=services, state=self.state)
        self.route_candidate_builder = RouteCandidateBuilder(inputs=inputs, services=services, state=self.state)
        self.route_cache_builder = RouteCacheBuilder(state=self.state)
        self.route_dominance_filter = RouteDominanceFilter(inputs=inputs, state=self.state)
        self.roundtrip_pair_builder = RoundtripPairSavingsBuilder(inputs=inputs, state=self.state)
        self.lp_pruner = LpPruner(inputs=inputs, services=services, state=self.state)
        self.model_builder = ModelBuilder(inputs=inputs, state=self.state, solve_hubs=solve_hubs)
        self.solution_builder = SolutionsBuilder(state=self.state, solve_hubs=solve_hubs)


    def build(self):
        self._tracker("Preparing shippers")
        self.shipper_classifier.prepare()

        if self.solve_hubs:
            self._tracker("Generating hub allocation candidates")
            self.hub_option_builder.build()
            self._tracker(self.state.hub_option_summary)

        self._tracker("Generating route pattern candidates")
        self.route_candidate_builder.generate_route_patterns()
        self._tracker(self.state.pattern_summary)

        self._tracker("Applying shipper ordering and deviation filter")
        self.route_candidate_builder.order_and_filter()
        self._tracker(self.state.filtered_pattern_summary)

        self._tracker("Permutating pattern candidates into vehicles")
        self.route_candidate_builder.create_and_price_routes()
        self._tracker(self.state.route_summary)

        self._tracker("Building route caches")
        self.route_cache_builder.build()

        self._tracker("Removing dominated routes")
        self.route_dominance_filter.apply()
        self._tracker(self.state.non_dominated_route_summary)

        self.route_cache_builder.rebuild_route_group_indexes()

        self._tracker("Building feasible roundtrip pair allocations")
        self.roundtrip_pair_builder.build()
        self._tracker(self.state.roundtrip_pair_summary)

        self._tracker("Validating solver feasibility")
        warnings = SolverFeasibilityValidator(self.state).validate()

        for warning in warnings:
            self._tracker(f"WARNING: {warning}")

        if warnings:
            raise ValueError(
                "Solver infeasible before model build:\n" + "\n".join(warnings)
            )

        self._tracker("Running conservative LP route pruning")
        self.lp_pruner.prune_routes()
        self._tracker(self.state.route_pruning_summary)

        self.route_cache_builder.rebuild_route_group_indexes()

        self._tracker("Rebuilding feasible roundtrip pair allocations after route pruning")
        self.roundtrip_pair_builder.build()
        self._tracker(self.state.roundtrip_pair_summary)

        self._tracker("Running conservative LP pair pruning")
        self.lp_pruner.prune_pairs()
        self._tracker(self.state.pair_pruning_summary)

        self._tracker("Building optimization model")
        self.model_builder.build()
        self._tracker(self.state.model_summary)

    def solve(self):
        self._tracker("Running optimization model")
        self.model_builder.solve()

        self._tracker("Run finished. Analyzing and preparing results")
        self.solution_builder.convert()

        self._tracker(self.state.solution_summary)


    @property
    def solution_parts_routes(self):
        return self.state.solution_parts_routes

    @property
    def solution_empties_routes(self):
        return self.state.solution_empties_routes

    @property
    def solution_pair_allocations(self):
        return self.state.solution_pair_allocations

    @property
    def solution_hubs(self):
        return self.state.solution_hubs