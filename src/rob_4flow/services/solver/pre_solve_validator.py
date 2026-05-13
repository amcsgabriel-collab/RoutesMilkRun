from .solver_state import MilkRunSolverState


class SolverFeasibilityValidator:
    def __init__(self, state: MilkRunSolverState):
        self.state = state

    def validate(self) -> list[str]:
        warnings = []
        warnings.extend(self._validate_shipper_flow_coverage())
        warnings.extend(self._validate_hub_linehauls())
        return warnings

    def raise_warnings(self) -> None:
        warnings = self.validate()

        if warnings:
            raise Warning("\n".join(warnings))

    def _validate_shipper_flow_coverage(self) -> list[str]:
        warnings = []

        for shipper in self.state.parts_shippers:
            direct_routes = [
                route
                for route in self.state.parts_routes
                if shipper in route.demand.pattern.shippers
            ]
            ltl_options = self.state.first_leg_options_by_shipper_flow.get(
                (shipper, "parts"),
                [],
            )

            if not direct_routes and not ltl_options:
                warnings.append(
                    f"No feasible parts coverage for shipper {self._shipper_label(shipper)}"
                )

        for shipper in self.state.empties_shippers:
            direct_routes = [
                route
                for route in self.state.empties_routes
                if shipper in route.demand.pattern.shippers
            ]
            ltl_options = self.state.first_leg_options_by_shipper_flow.get(
                (shipper, "empties"),
                [],
            )

            if not direct_routes and not ltl_options:
                warnings.append(
                    f"No feasible empties coverage for shipper {self._shipper_label(shipper)}"
                )

        return warnings

    def _validate_hub_linehauls(self) -> list[str]:
        warnings = []

        for hub_flow, first_leg_options in self.state.first_leg_options_by_hub_flow.items():
            if not first_leg_options:
                continue

            linehaul_options = self.state.linehaul_options_by_hub_flow.get(
                hub_flow,
                [],
            )

            if not linehaul_options:
                hub, flow_direction = hub_flow
                warnings.append(
                    f"No feasible {flow_direction} linehaul for hub {self._hub_label(hub)} "
                    f"with {len(first_leg_options)} first-leg options"
                )

        return warnings

    @staticmethod
    def _shipper_label(shipper) -> str:
        return getattr(shipper, "cofor", None) or getattr(shipper, "id", None) or str(shipper)

    @staticmethod
    def _hub_label(hub) -> str:
        core_hub = getattr(hub, "core_hub", hub)
        return getattr(core_hub, "cofor", None) or getattr(core_hub, "id", None) or str(core_hub)