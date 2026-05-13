from itertools import combinations

from ....domain.domain_algorithms import make_haversine_cache
from ....domain.routes.route_pattern import RoutePattern
from ....domain.shipper import Shipper
from ..solver_input_parsing import SolverInputs
from ..solver_services import SolverServices
from ..solver_state import MilkRunSolverState


class RouteCandidateBuilder:
    def __init__(
        self,
        inputs: SolverInputs,
        services: SolverServices,
        state: MilkRunSolverState,
    ):
        self.inputs = inputs
        self.services = services
        self.state = state
        self.tracker = services.tracker

    @property
    def all_patterns(self):
        return self.state.parts_patterns | self.state.empties_patterns

    def generate_route_patterns(self) -> None:
        carriers = {
            s.carrier.group
            for s in self.inputs.parts_shippers | self.inputs.empties_shippers
        }

        self.tracker(f"Generating route patterns for {len(carriers)} carrier groups")

        for carrier in carriers:
            non_ftl_parts = {
                s for s in self.state.non_exclusive_parts_shippers
                if s.carrier.group == carrier
            }
            non_ftl_empties = {
                s for s in self.state.non_exclusive_empties_shippers
                if s.carrier.group == carrier
            }
            ftl_parts = {
                s for s in self.state.ftl_exclusive_parts_shippers
                if s.carrier.group == carrier
            }
            ftl_empties = {
                s for s in self.state.ftl_exclusive_empties_shippers
                if s.carrier.group == carrier
            }

            self.state.parts_patterns |= self.iterate_creation_of_route_patterns(
                shippers=non_ftl_parts,
                existing_patterns=self.state.existing_parts_patterns,
                flow_direction="parts",
                max_stops=self.inputs.max_stops,
            )
            self.state.empties_patterns |= self.iterate_creation_of_route_patterns(
                shippers=non_ftl_empties,
                existing_patterns=self.state.existing_empties_patterns,
                flow_direction="empties",
                max_stops=self.inputs.max_stops,
            )
            self.state.parts_patterns |= self.iterate_creation_of_route_patterns(
                shippers=ftl_parts,
                existing_patterns=self.state.existing_parts_patterns,
                flow_direction="parts",
                max_stops=1,
            )
            self.state.empties_patterns |= self.iterate_creation_of_route_patterns(
                shippers=ftl_empties,
                existing_patterns=self.state.existing_empties_patterns,
                flow_direction="empties",
                max_stops=1,
            )

            self.tracker(
                f"Carrier {carrier}: {len(non_ftl_parts)} Non-FTL Exclusive Parts, "
                f"{len(ftl_parts)} FTL Exclusive Parts, "
                f"{len(non_ftl_empties)} Non-FTL Exclusive Empties, "
                f"{len(ftl_empties)} FTL Exclusive Empties processed"
            )

    def iterate_creation_of_route_patterns(
        self,
        *,
        shippers: set[Shipper],
        existing_patterns: set[RoutePattern],
        flow_direction: str,
        max_stops: int = 4,
    ) -> set[RoutePattern]:
        route_id = 0
        routes = set()

        blocked_by_shippers = {
            pattern.shippers
            for pattern in self.inputs.blocked_patterns
        }
        existing_by_shippers = {
            pattern.shippers: pattern
            for pattern in existing_patterns
        }

        for num_points in range(1, max_stops + 1):
            for combination in combinations(shippers, num_points):
                route_key = frozenset(combination)

                if route_key in blocked_by_shippers:
                    continue

                existing = existing_by_shippers.get(route_key)

                if existing:
                    candidate = existing.copy()
                    candidate.reset_allocation()
                else:
                    candidate = RoutePattern(
                        shippers=combination,
                        plant=self.inputs.plant,
                        flow_direction=flow_direction,
                        overutilization=self.inputs.overutilization
                    )
                    route_id += 1
                    candidate.route_name = route_id
                    candidate.is_new_pattern = True

                routes.add(candidate)

        return routes

    def order_and_filter(self):
        self.apply_ordering_to_route_patterns()
        self.remove_high_deviation_route_patterns()

    def apply_ordering_to_route_patterns(self):
        distance_function = make_haversine_cache()
        for pattern in self.all_patterns:
            pattern.order_shippers(distance_function)
            pattern.calculate_deviation(distance_function)

    def remove_high_deviation_route_patterns(self):
        parts_patterns_to_remove = {p for p in self.state.parts_patterns if p.deviation > 150}
        for pattern in parts_patterns_to_remove:
            self.state.parts_patterns.remove(pattern)

        empties_patterns_to_remove = {
            p for p in self.state.empties_patterns if p.deviation > 150
        }
        for pattern in empties_patterns_to_remove:
            self.state.empties_patterns.remove(pattern)

    def create_and_price_routes(self):
        new_parts_routes = self.services.vehicle_permutation_service.permutate(self.state.parts_patterns)
        self.services.tariff_service.assign_ftl_mr_routes(new_parts_routes)
        self.state.parts_routes = {r for r in new_parts_routes if r.total_cost > 0}

        new_empties_routes = self.services.vehicle_permutation_service.permutate(
            self.state.empties_patterns
        )
        self.services.tariff_service.assign_ftl_mr_routes(new_empties_routes)
        self.state.empties_routes = {r for r in new_empties_routes if r.total_cost > 0}
