from collections import defaultdict

import pulp


from .solver_state import MilkRunSolverState
from ...domain.hub import Hub
from ...domain.regional_hub_view import RegionalHubView, HubLike


class SolutionsBuilder:
    def __init__(
        self,
        state: MilkRunSolverState,
        solve_hubs,
    ):
        self.state = state
        self.solve_hubs = solve_hubs

    def convert(self) -> None:
        self.state.solution_parts_routes = {
            route
            for route, var in self.state.use_parts_route_bin.items()
            if round(pulp.value(var) or 0) == 1
        }
        self.state.solution_empties_routes = {
            route
            for route, var in self.state.use_empties_route_bin.items()
            if round(pulp.value(var) or 0) == 1
        }
        self.state.solution_pair_allocations = {
            pair: int(round(pulp.value(var) or 0))
            for pair, var in self.state.pair_frequency.items()
            if round(pulp.value(var) or 0) > 0
        }

        if (
                self.solve_hubs
                and self.state.use_hub_first_leg_bin is not None
                and self.state.use_hub_linehaul_bin is not None
        ):
            self.state.solution_first_leg_options = {
                option
                for option, var in self.state.use_hub_first_leg_bin.items()
                if round(pulp.value(var) or 0) == 1
            }

            self.state.solution_linehaul_options = {
                option
                for option, var in self.state.use_hub_linehaul_bin.items()
                if round(pulp.value(var) or 0) == 1
            }

            self.state.solution_hubs = self._build_solution_hubs()

    def _build_solution_hubs(self) -> set:
        selected_by_hub: dict[object, dict[str, list]] = defaultdict(
            lambda: defaultdict(list)
        )

        for option in self.state.solution_first_leg_options:
            selected_by_hub[option.hub_template][option.flow_direction].append(option)

        selected_linehaul_by_hub_flow = {
            (option.hub_template, option.flow_direction): option
            for option in self.state.solution_linehaul_options
        }

        solution_hubs = set()

        for hub_candidate, options_by_flow in selected_by_hub.items():
            core_hub = self._core_hub(hub_candidate)

            selected_shippers = sorted(
                {
                    option.shipper
                    for flow_options in options_by_flow.values()
                    for option in flow_options
                },
                key=lambda shipper: getattr(shipper, "id", str(shipper)),
            )

            has_empties_flow = bool(options_by_flow.get("empties"))

            parts_linehaul = selected_linehaul_by_hub_flow.get(
                (hub_candidate, "parts")
            )
            empties_linehaul = selected_linehaul_by_hub_flow.get(
                (hub_candidate, "empties")
            )

            selected_linehaul = parts_linehaul or empties_linehaul
            if selected_linehaul is None:
                continue

            hub = Hub(
                route=core_hub.route_id,
                cofor=core_hub.cofor,
                name=core_hub.name,
                country=core_hub.country,
                zip_code=core_hub.zip_code,
                plant=core_hub.plant,
                shippers=list(selected_shippers),
                first_leg_carrier=core_hub.first_leg_carrier,
                first_leg_vehicle=core_hub.first_leg_vehicle,
                linehaul_carrier=selected_linehaul.carrier,
                linehaul_vehicle=selected_linehaul.vehicle,
                linehaul_transport_concept=selected_linehaul.transport_concept,
                coordinates=core_hub.coordinates,
                has_empties_flow=has_empties_flow,
            )

            if isinstance(hub_candidate, RegionalHubView):
                hub = RegionalHubView(
                    core_hub=hub,
                    region=hub_candidate.region,
                )

            solution_hubs.add(hub)

        return solution_hubs

    @staticmethod
    def _core_hub(hub: HubLike) -> Hub:
        if isinstance(hub, RegionalHubView):
            return hub.core_hub

        return hub