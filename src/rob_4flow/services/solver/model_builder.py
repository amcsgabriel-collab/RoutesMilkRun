import pulp

from .solver_input_parsing import SolverInputs
from .solver_state import MilkRunSolverState
from ...domain.exceptions import NonOptimalSolutionError


class ModelBuilder:
    def __init__(
        self,
        inputs: SolverInputs,
        state: MilkRunSolverState,
        solve_hubs:bool,
    ):
        self.inputs = inputs
        self.state = state
        self.solve_hubs = solve_hubs

    def build(self) -> None:
        self.state.model = pulp.LpProblem("Atomic_Route_Allocation", pulp.LpMinimize)

        self.state.use_parts_route_bin = pulp.LpVariable.dicts(
            name="use_parts_route",
            indices=self.state.parts_routes,
            cat="Binary",
        )
        self.state.use_empties_route_bin = pulp.LpVariable.dicts(
            name="use_empties_route",
            indices=self.state.empties_routes,
            cat="Binary",
        )
        self.state.pair_frequency = pulp.LpVariable.dicts(
            name="pair_frequency",
            indices=self.state.feasible_pair_allocations,
            lowBound=0,
            cat="Continuous",
        )

        if self.solve_hubs:
            self.state.use_hub_first_leg_bin = pulp.LpVariable.dicts(
                name="use_hub_first_leg",
                indices=self.state.hub_first_leg_options,
                cat="Binary",
            )
            self.state.use_hub_linehaul_bin = pulp.LpVariable.dicts(
                name="use_hub_linehaul",
                indices=self.state.hub_linehaul_options,
                cat="Binary",
            )

        hub_objective = 0

        if self.solve_hubs:
            hub_objective = (
                pulp.lpSum(
                    option.total_cost * self.state.use_hub_first_leg_bin[option]
                    for option in self.state.hub_first_leg_options
                )
                + pulp.lpSum(
                    option.total_cost * self.state.use_hub_linehaul_bin[option]
                    for option in self.state.hub_linehaul_options
                )
            )

        self.state.model += (
            pulp.lpSum(
                self.state.route_total_cost[route]
                * self.state.use_parts_route_bin[route]
                for route in self.state.parts_routes
            )
            + pulp.lpSum(
                self.state.route_total_cost[route]
                * self.state.use_empties_route_bin[route]
                for route in self.state.empties_routes
            )
            - pulp.lpSum(
                self.state.pair_saving_per_frequency[pair]
                * self.state.pair_frequency[pair]
                for pair in self.state.feasible_pair_allocations
            )
            + hub_objective
        )

        self._add_shipper_coverage_constraints()
        self._add_pair_capacity_constraints()

        if self.solve_hubs:
            self._add_hub_constraints()

    def solve(self) -> None:
        solver = pulp.PULP_CBC_CMD(msg=False)
        self.state.model.solve(solver)
        self.state.solve_status = pulp.LpStatus[self.state.model.status]
        print("Solve status:", self.state.solve_status)
        if self.state.solve_status != "Optimal": raise NonOptimalSolutionError()


    def _add_shipper_coverage_constraints(self) -> None:
        for shipper in self.inputs.parts_shippers:
            hub_terms = []
            if self.solve_hubs:
                hub_terms = [
                    self.state.use_hub_first_leg_bin[option]
                    for option in self.state.first_leg_options_by_shipper_flow.get(
                        (shipper, "parts"),
                        [],
                    )
                ]

            self.state.model += (
                pulp.lpSum(
                    self.state.use_parts_route_bin[route]
                    for route in self.state.parts_routes
                    if shipper in route.demand.pattern.shippers
                )
                + pulp.lpSum(hub_terms)
                == 1
            )

        for shipper in self.inputs.empties_shippers:
            hub_terms = []
            if self.solve_hubs:
                hub_terms = [
                    self.state.use_hub_first_leg_bin[option]
                    for option in self.state.first_leg_options_by_shipper_flow.get(
                        (shipper, "empties"),
                        [],
                    )
                ]

            self.state.model += (
                pulp.lpSum(
                    self.state.use_empties_route_bin[route]
                    for route in self.state.empties_routes
                    if shipper in route.demand.pattern.shippers
                )
                + pulp.lpSum(hub_terms)
                == 1
            )

    def _add_pair_capacity_constraints(self) -> None:
        for parts_route in self.state.parts_routes:
            self.state.model += (
                pulp.lpSum(
                    self.state.pair_frequency[pair]
                    for pair in self.state.pairs_by_parts_route.get(parts_route, [])
                )
                <= self.state.route_frequency[parts_route]
                * self.state.use_parts_route_bin[parts_route],
                f"pair_cap_parts_{hash(parts_route)}",
            )

        for empties_route in self.state.empties_routes:
            self.state.model += (
                pulp.lpSum(
                    self.state.pair_frequency[pair]
                    for pair in self.state.pairs_by_empties_route.get(empties_route, [])
                )
                <= self.state.route_frequency[empties_route]
                * self.state.use_empties_route_bin[empties_route],
                f"pair_cap_empties_{hash(empties_route)}",
            )

        for fixed_parts_route in self.inputs.locked_parts_routes:
            self.state.model += (
                pulp.lpSum(
                    self.state.pair_frequency[pair]
                    for pair in self.state.pairs_by_parts_route.get(
                        fixed_parts_route,
                        [],
                    )
                )
                <= self.state.route_frequency[fixed_parts_route],
                f"pair_cap_fixed_parts_{hash(fixed_parts_route)}",
            )

        for fixed_empties_route in self.inputs.locked_empties_routes:
            self.state.model += (
                pulp.lpSum(
                    self.state.pair_frequency[pair]
                    for pair in self.state.pairs_by_empties_route.get(
                        fixed_empties_route,
                        [],
                    )
                )
                <= self.state.route_frequency[fixed_empties_route],
                f"pair_cap_fixed_empties_{hash(fixed_empties_route)}",
            )

    def _add_hub_constraints(self) -> None:
        for option in self.state.hub_first_leg_options:
            if option.is_locked:
                self.state.model += (
                    self.state.use_hub_first_leg_bin[option] == 1,
                    f"locked_first_leg_{hash(option)}",
                )

        for hub_flow, first_leg_options in self.state.first_leg_options_by_hub_flow.items():
            hub, flow_direction = hub_flow
            linehaul_options = self.state.linehaul_options_by_hub_flow.get(
                hub_flow,
                [],
            )

            if not linehaul_options:
                for option in first_leg_options:
                    self.state.model += (
                        self.state.use_hub_first_leg_bin[option] == 0,
                        f"no_linehaul_for_first_leg_{hash(option)}",
                    )
                continue

            self.state.model += (
                pulp.lpSum(
                    self.state.use_hub_linehaul_bin[linehaul]
                    for linehaul in linehaul_options
                )
                <= 1,
                f"single_linehaul_choice_{hash(hub)}_{flow_direction}",
            )

            self.state.model += (
                pulp.lpSum(
                    option.chargeable_weight
                    * self.state.use_hub_first_leg_bin[option]
                    for option in first_leg_options
                )
                <= pulp.lpSum(
                    linehaul.capacity_chargeable_weight
                    * self.state.use_hub_linehaul_bin[linehaul]
                    for linehaul in linehaul_options
                ),
                f"hub_capacity_{hash(hub)}_{flow_direction}",
            )

            for option in first_leg_options:
                self.state.model += (
                    option.first_leg_frequency
                    * self.state.use_hub_first_leg_bin[option]
                    <= pulp.lpSum(
                        linehaul.frequency
                        * self.state.use_hub_linehaul_bin[linehaul]
                        for linehaul in linehaul_options
                    ),
                    f"first_leg_frequency_cap_{hash(option)}",
                )