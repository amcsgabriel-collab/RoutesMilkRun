from dataclasses import dataclass

from .direct_routes.vehicle_permutation_service import VehiclePermutationService
from ...domain.data_structures import Plant
from ...domain.project import Project
from ...domain.regional_hub_view import HubLike
from ...domain.routes.direct_route import DirectRoute
from ...domain.routes.first_leg_route import FirstLegRoute
from ...domain.routes.route_pattern import RoutePattern
from ...domain.shipper import Shipper
from ...domain.trip import Trip


@dataclass(frozen=True)
class SolverInputs:
    existing_trips: set[Trip]
    existing_hubs: set[HubLike]

    parts_shippers: set[Shipper]
    empties_shippers: set[Shipper]

    locked_parts_routes: set[DirectRoute]
    locked_empties_routes: set[DirectRoute]

    locked_ltl_parts_shippers: set[tuple[Shipper, str]]
    locked_ltl_empties_shippers: set[tuple[Shipper, str]]

    blocked_patterns: set[RoutePattern]
    blocked_ltl_shippers: set[tuple[Shipper, str]]

    vehicle_permutation_service: VehiclePermutationService

    plant: Plant

    overutilization: dict[str, float]
    max_stops: int


class SolverInputBuilder:
    def __init__(self, project: Project, solve_hubs: bool, overutilization: dict[str, float], max_stops: int):
        self.project = project
        self.scenario = project.current_scenario
        self.solve_hubs = solve_hubs
        self.overutilization = overutilization
        self.max_stops = max_stops

    def build(self) -> SolverInputs:

        self.scenario.create_draft_hubs()
        self.scenario.create_draft_trips()
        locked_empties_routes = {r
                                 for r in self.scenario.locked_routes
                                 if r.demand.flow_direction == "empties"
                                 and isinstance(r, DirectRoute)}
        locked_parts_routes = {r
                               for r in self.scenario.locked_routes
                               if r.demand.flow_direction == "parts"
                               and isinstance(r, DirectRoute)}

        locked_ltl_parts_shippers = {r.shipper
                                     for r in self.scenario.locked_routes
                                     if isinstance(r, FirstLegRoute)}

        locked_ltl_empties_shippers = {r.shipper
                                       for r in self.scenario.locked_routes
                                       if isinstance(r, FirstLegRoute)
                                       and self.scenario.find_shipper_hub(r.shipper).has_empties_flow}

        return SolverInputs(
            existing_trips=self.scenario.get_in_use_trips(),
            existing_hubs=self.scenario.get_in_use_hubs(),
            parts_shippers=self._filtered_shippers(
                "parts",
                locked_parts_routes,
                locked_ltl_parts_shippers,
            ),
            empties_shippers=self._filtered_shippers(
                "empties",
                locked_empties_routes,
                locked_ltl_empties_shippers,
            ),
            locked_parts_routes=locked_parts_routes,
            locked_empties_routes=locked_empties_routes,
            locked_ltl_parts_shippers=locked_ltl_parts_shippers,
            locked_ltl_empties_shippers=locked_ltl_empties_shippers,
            blocked_patterns={r.demand.pattern for r in self.scenario.blocked_routes if isinstance(r, DirectRoute)},
            blocked_ltl_shippers={r.shipper for r in self.scenario.blocked_routes if isinstance(r, FirstLegRoute)},
            vehicle_permutation_service= VehiclePermutationService(self.project.context.vehicles),
            plant=self.project.plant,
            overutilization=self.overutilization,
            max_stops=self.max_stops
        )

    def _filtered_shippers(
            self,
            flow_direction: str,
            locked_direct_routes: set[DirectRoute],
            locked_ltl_shippers: set[Shipper],
    ) -> set[Shipper]:

        locked_direct_shippers = {
            shipper
            for route in locked_direct_routes
            for shipper in route.demand.pattern.shippers
        }

        locked_ltl_flow_shippers = {
            shipper
            for shipper in locked_ltl_shippers
        }

        locked_shippers = locked_direct_shippers | locked_ltl_flow_shippers

        hub_shippers_dict = getattr(self.scenario, f"{flow_direction}_hub_shippers")
        shippers_dict = getattr(self.scenario, f"{flow_direction}_direct_shippers")
        if self.solve_hubs:
            shippers_dict |= hub_shippers_dict

        return {
            shipper
            for shipper in shippers_dict.values()
            if shipper not in locked_shippers
        }
