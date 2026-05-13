import copy
from dataclasses import dataclass

from ....domain.hub import Hub
from ....domain.regional_hub_view import HubLike, RegionalHubView
from ....domain.routes.first_leg_route import FirstLegRoute, get_frequency_bracket
from ....domain.routes.linehaul_route import LinehaulRoute, get_linehaul_frequency_capacity
from ....domain.shipper import Shipper
from ..solver_input_parsing import SolverInputs
from ..solver_services import SolverServices
from ..solver_state import MilkRunSolverState


def _core_hub(hub: HubLike) -> Hub:
    return hub.core_hub if isinstance(hub, RegionalHubView) else hub


def _chargeable_weight_for_shipper(shipper: Shipper, flow_direction: str) -> float:
    demand = shipper.parts_demand if flow_direction == "parts" else shipper.empties_demand
    return max(demand.weight, demand.volume * 250)


@dataclass(frozen=True)
class HubFirstLegOption:
    shipper: Shipper
    hub_template: object
    flow_direction: str
    carrier: object
    vehicle: object
    chargeable_weight: float
    first_leg_frequency: int
    total_cost: float
    route: object
    is_locked: bool = False


@dataclass(frozen=True)
class HubLinehaulOption:
    hub_template: object
    flow_direction: str
    transport_concept: str
    carrier: object
    vehicle: object
    frequency: int
    capacity_chargeable_weight: float
    total_cost: float
    route: object


class HubOptionBuilder:
    def __init__(
        self,
        inputs: SolverInputs,
        services: SolverServices,
        state: MilkRunSolverState,
    ):
        self.inputs = inputs
        self.services = services
        self.state = state

    def build(self) -> None:
        self.state.hub_first_leg_options.clear()
        self.state.hub_linehaul_options.clear()
        self.state.first_leg_options_by_shipper_flow.clear()
        self.state.first_leg_options_by_hub_flow.clear()
        self.state.linehaul_options_by_hub_flow.clear()

        generated_hub_flows: set[tuple[HubLike, str]] = set()

        for shipper in self.inputs.parts_shippers | self.inputs.empties_shippers:

            hub_candidate = self.services.hub_assignment_service.assign_hub_to_shipper(
                shipper=shipper,
                hubs=self.inputs.existing_hubs,
            )
            if hub_candidate is None:
                continue

            core_hub = _core_hub(hub_candidate)
            flows_to_generate = []

            if shipper in self.inputs.parts_shippers:
                flows_to_generate.append("parts")

            if shipper in self.inputs.empties_shippers and core_hub.has_empties_flow:
                flows_to_generate.append("empties")

            for flow_direction in flows_to_generate:
                if self._is_shipper_flow_ltl_blocked(shipper, flow_direction):
                    continue

                option = self._build_first_leg_option(
                    shipper=shipper,
                    hub_candidate=hub_candidate,
                    flow_direction=flow_direction,
                )

                if option is None:
                    continue

                self.state.hub_first_leg_options.add(option)
                self.state.first_leg_options_by_shipper_flow[
                    (shipper, flow_direction)
                ].append(option)
                self.state.first_leg_options_by_hub_flow[
                    (hub_candidate, flow_direction)
                ].append(option)

                generated_hub_flows.add((hub_candidate, flow_direction))

        for hub_candidate, flow_direction in generated_hub_flows:
            self._generate_linehaul_options_for_hub_flow(
                hub_candidate=hub_candidate,
                flow_direction=flow_direction,
            )

    def _build_first_leg_option(
        self,
        *,
        shipper: Shipper,
        hub_candidate: HubLike,
        flow_direction: str,
    ) -> HubFirstLegOption | None:
        core_hub = _core_hub(hub_candidate)

        route = FirstLegRoute(
            hub=core_hub,
            shipper=shipper,
            vehicle=core_hub.first_leg_vehicle,
            carrier=core_hub.first_leg_carrier,
            flow_direction=flow_direction,
        )

        self.services.tariff_service.assign_ltl_route(route)

        if getattr(route, "tariff_source", None) == "Missing":
            return None

        chargeable_weight = _chargeable_weight_for_shipper(shipper, flow_direction)
        first_leg_frequency = get_frequency_bracket(chargeable_weight)
        total_cost = route.route_cost * first_leg_frequency

        if total_cost <= 0:
            return None

        return HubFirstLegOption(
            shipper=shipper,
            hub_template=hub_candidate,
            flow_direction=flow_direction,
            carrier=core_hub.first_leg_carrier,
            vehicle=core_hub.first_leg_vehicle,
            chargeable_weight=chargeable_weight,
            first_leg_frequency=first_leg_frequency,
            total_cost=total_cost,
            route=route,
            is_locked=self._is_shipper_flow_ltl_locked(shipper, flow_direction),
        )

    def _find_hub_by_cofor(self, hub_cofor: str) -> HubLike | None:
        for hub in self.inputs.existing_hubs:
            if _core_hub(hub).cofor == hub_cofor:
                return hub

        return None

    def _find_current_shipper_hub(self, shipper: Shipper) -> HubLike | None:
        for hub in self.inputs.existing_hubs:
            core_hub = _core_hub(hub)

            if shipper in getattr(core_hub, "shippers", []):
                return hub

            if shipper in getattr(hub, "shippers", []):
                return hub

            if shipper in getattr(hub, "parts_shippers", []):
                return hub

            if shipper in getattr(hub, "empties_shippers", []):
                return hub

        return None

    def _is_shipper_flow_ltl_locked(
        self,
        shipper: Shipper,
        flow_direction: str,
    ) -> bool:
        return shipper in getattr(
            self.inputs,
            f"locked_ltl_{flow_direction}_shippers",
            set(),
        )

    def _is_shipper_flow_ltl_blocked(
        self,
        shipper: Shipper,
        flow_direction: str,
    ) -> bool:
        blocked = self.inputs.blocked_ltl_shippers
        return shipper in blocked or (shipper, flow_direction) in blocked

    def _generate_linehaul_options_for_hub_flow(
        self,
        *,
        hub_candidate: HubLike,
        flow_direction: str,
    ) -> None:
        core_hub = _core_hub(hub_candidate)

        base_linehaul_route = (
            core_hub.parts_linehaul_route
            if flow_direction == "parts"
            else getattr(core_hub, "empties_linehaul_route", None)
        )

        if base_linehaul_route is None:
            return

        for transport_concept in ("LTL", "FTL"):
            for frequency in (1, 2, 3):
                hub_copy = copy.deepcopy(core_hub)
                hub_copy.linehaul_transport_concept = transport_concept
                hub_copy.shippers = []

                route = LinehaulRoute(
                    hub=hub_copy,
                    vehicle=base_linehaul_route.vehicle,
                    carrier=base_linehaul_route.carrier,
                    flow_direction=flow_direction,
                )

                if transport_concept == "FTL":
                    self.services.tariff_service.assign_linehaul(route)
                else:
                    self.services.tariff_service.assign_ltl_linehaul(route)

                route_cost = route.route_cost
                if route_cost <= 0:
                    continue

                option = HubLinehaulOption(
                    hub_template=hub_candidate,
                    flow_direction=flow_direction,
                    transport_concept=transport_concept,
                    carrier=base_linehaul_route.carrier,
                    vehicle=base_linehaul_route.vehicle,
                    frequency=frequency,
                    capacity_chargeable_weight=get_linehaul_frequency_capacity(frequency),
                    total_cost=route_cost * frequency,
                    route=route,
                )

                self.state.hub_linehaul_options.add(option)
                self.state.linehaul_options_by_hub_flow[
                    (hub_candidate, flow_direction)
                ].append(option)