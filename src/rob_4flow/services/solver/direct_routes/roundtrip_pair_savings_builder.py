from ..solver_input_parsing import SolverInputs
from ..solver_state import MilkRunSolverState
from ....domain.routes.direct_route import DirectRoute


class RoundtripPairSavingsBuilder:
    MAX_PARTNERS_PER_ROUTE = 5

    def __init__(
        self,
        inputs: SolverInputs,
        state: MilkRunSolverState,
    ):
        self.inputs = inputs
        self.state = state

    def build(self) -> None:
        self.state.feasible_pair_allocations = []
        self.state.pair_saving_per_frequency = {}
        self.state.pairs_by_parts_route.clear()
        self.state.pairs_by_empties_route.clear()

        shared_groups = (
            set(self.state.parts_routes_by_group)
            | set(self.state.locked_parts_routes_by_group)
        ) & (
            set(self.state.empties_routes_by_group)
            | set(self.state.locked_empties_routes_by_group)
        )

        max_partners = self.MAX_PARTNERS_PER_ROUTE

        for group in shared_groups:
            group_parts_routes = (
                self.state.parts_routes_by_group.get(group, [])
                + self.state.locked_parts_routes_by_group.get(group, [])
            )
            group_empties_routes = (
                self.state.empties_routes_by_group.get(group, [])
                + self.state.locked_empties_routes_by_group.get(group, [])
            )

            if not group_parts_routes or not group_empties_routes:
                continue

            sorted_empties_routes = sorted(
                group_empties_routes,
                key=lambda route: self.state.route_pair_delta[route],
                reverse=True,
            )

            for parts_route in group_parts_routes:
                parts_delta = self.state.route_pair_delta[parts_route]
                selected_count = 0

                for empties_route in sorted_empties_routes:
                    if (
                        parts_route in self.inputs.locked_parts_routes
                        and empties_route in self.inputs.locked_empties_routes
                    ):
                        continue

                    saving = self._pair_saving_per_frequency(
                        parts_route,
                        empties_route,
                    )
                    if saving <= 0:
                        break

                    pair = (parts_route, empties_route)
                    self.state.feasible_pair_allocations.append(pair)
                    self.state.pair_saving_per_frequency[pair] = saving
                    self.state.pairs_by_parts_route[parts_route].append(pair)
                    self.state.pairs_by_empties_route[empties_route].append(pair)

                    selected_count += 1
                    if selected_count >= max_partners:
                        break

        print("parts groups", len(self.state.parts_routes_by_group))
        print("empties groups", len(self.state.empties_routes_by_group))
        print("shared groups", len(shared_groups))
        print("route pair deltas", len(self.state.route_pair_delta))

    def _pair_saving_per_frequency(
        self,
        parts_route: DirectRoute,
        empties_route: DirectRoute,
    ) -> float:
        return max(
            0.0,
            self.state.route_pair_delta[parts_route]
            + self.state.route_pair_delta[empties_route],
        )