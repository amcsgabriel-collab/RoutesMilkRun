from collections import defaultdict

from rob_4flow.domain.routes.direct_route import DirectRoute
from ..solver_state import MilkRunSolverState

def _group_key(route: DirectRoute) -> tuple:
    return route.carrier.group, route.vehicle.id, route.starting_point.zip_code


class RouteCacheBuilder:
    def __init__(self, state: MilkRunSolverState):
        self.state = state

    def build(self) -> None:
        self.state.route_frequency.clear()
        self.state.route_total_cost.clear()
        self.state.route_roundtrip_total_cost.clear()
        self.state.route_pair_delta.clear()

        all_routes = (
                self.state.parts_routes
                | self.state.empties_routes
                | self.state.locked_parts_routes
                | self.state.locked_empties_routes
        )

        for route in all_routes:
            self.get_route_attributes(route)

        self.rebuild_route_group_indexes()


    def get_route_attributes(self, route):
        freq = int(route.frequency)
        self.state.route_frequency[route] = freq
        self.state.route_total_cost[route] = route.total_cost
        self.state.route_roundtrip_total_cost[route] = route.roundtrip_total_cost

        if freq == 0:
            self.state.route_pair_delta[route] = 0.0
        else:
            direct_unit_cost = route.total_cost / freq
            roundtrip_unit_cost = route.roundtrip_total_cost / freq
            self.state.route_pair_delta[route] = (
                    direct_unit_cost - roundtrip_unit_cost
            )

    def rebuild_route_group_indexes(self) -> None:
        self.state.parts_routes_by_group = self._group_routes(self.state.parts_routes)
        self.state.empties_routes_by_group = self._group_routes(self.state.empties_routes)
        self.state.locked_parts_routes_by_group = self._group_routes(self.state.locked_parts_routes)
        self.state.locked_empties_routes_by_group = self._group_routes(self.state.locked_empties_routes)

    @staticmethod
    def _group_routes(routes: set[DirectRoute]) -> dict[tuple, list[DirectRoute]]:
        grouped: dict[tuple, list[DirectRoute]] = defaultdict(list)

        for route in routes:
            grouped[_group_key(route)].append(route)

        return grouped


