import pulp

from ....domain.routes.direct_route import DirectRoute
from ....domain.routes.route_pattern import RoutePattern
from ....domain.shipper import Shipper
from ..solver_input_parsing import SolverInputs
from ..solver_services import SolverServices
from ..solver_state import MilkRunSolverState


class LpPruner:
    def __init__(
        self,
        inputs: SolverInputs,
        services: SolverServices,
        state: MilkRunSolverState,
    ):
        self.inputs = inputs
        self.services = services
        self.state = state

    @staticmethod
    def _stable_pattern_key(pattern: RoutePattern) -> str:
        return "|".join(
            sorted(getattr(shipper, "id", str(shipper)) for shipper in pattern.shippers)
        )

    @staticmethod
    def _stable_route_key(route: DirectRoute) -> tuple:
        return (
            route.demand.flow_direction,
            route.carrier.group,
            route.vehicle.id,
            route.starting_point.zip_code,
            "|".join(
                sorted(
                    getattr(shipper, "id", str(shipper))
                    for shipper in route.demand.pattern.shippers
                )
            ),
        )

    def prune_routes(
        self,
        *,
        lp_value_epsilon: float = 1e-6,
        reduced_cost_floor: float = 50.0,
        reduced_cost_ratio: float = 0.02,
        keep_top_n_per_shipper: int = 60,
        solver=None,
    ) -> None:
        if not self.state.parts_routes and not self.state.empties_routes:
            return

        self.services.tracker("Running conservative LP-based route pruning pass")

        lp_result = self._solve_lp_relaxation_for_pruning(solver=solver)
        if lp_result["status"] != "Optimal":
            self.services.tracker(
                f"Skipping LP pruning because relaxation status is {lp_result['status']}"
            )
            return

        kept_parts_routes = self._select_routes_to_keep_from_lp(
            routes=self.state.parts_routes,
            shippers=self.inputs.parts_shippers,
            lp_values=lp_result["parts_lp_values"],
            reduced_costs=lp_result["parts_reduced_costs"],
            lp_value_epsilon=lp_value_epsilon,
            reduced_cost_floor=reduced_cost_floor,
            reduced_cost_ratio=reduced_cost_ratio,
            keep_top_n_per_shipper=keep_top_n_per_shipper,
        )
        kept_empties_routes = self._select_routes_to_keep_from_lp(
            routes=self.state.empties_routes,
            shippers=self.inputs.empties_shippers,
            lp_values=lp_result["empties_lp_values"],
            reduced_costs=lp_result["empties_reduced_costs"],
            lp_value_epsilon=lp_value_epsilon,
            reduced_cost_floor=reduced_cost_floor,
            reduced_cost_ratio=reduced_cost_ratio,
            keep_top_n_per_shipper=keep_top_n_per_shipper,
        )

        removed_parts = len(self.state.parts_routes) - len(kept_parts_routes)
        removed_empties = len(self.state.empties_routes) - len(kept_empties_routes)

        self.state.parts_routes = kept_parts_routes
        self.state.empties_routes = kept_empties_routes

        self._filter_route_caches()

        self.services.tracker(
            f"LP pruning removed {removed_parts} parts routes and "
            f"{removed_empties} empties routes"
        )

    def prune_pairs(
        self,
        *,
        lp_value_epsilon: float = 1e-4,
        reduced_cost_floor: float = 40.0,
        reduced_cost_ratio: float = 0.05,
        keep_top_n_per_parts_route: int = 6,
        keep_top_n_per_empties_route: int = 6,
        keep_top_n_by_saving_per_parts_route: int = 5,
        keep_top_n_by_saving_per_empties_route: int = 5,
        solver=None,
    ) -> None:
        if not self.state.feasible_pair_allocations:
            return

        self.services.tracker("Running conservative LP-based pair pruning pass")

        lp_result = self._solve_lp_relaxation_for_pruning(solver=solver)
        if lp_result["status"] != "Optimal":
            self.services.tracker(
                f"Skipping LP pair pruning because relaxation status is {lp_result['status']}"
            )
            return

        kept_pairs = self._select_pairs_to_keep_from_lp(
            pairs=self.state.feasible_pair_allocations,
            pair_lp_values=lp_result["pair_lp_values"],
            pair_reduced_costs=lp_result["pair_reduced_costs"],
            lp_value_epsilon=lp_value_epsilon,
            reduced_cost_floor=reduced_cost_floor,
            reduced_cost_ratio=reduced_cost_ratio,
            keep_top_n_per_parts_route=keep_top_n_per_parts_route,
            keep_top_n_per_empties_route=keep_top_n_per_empties_route,
            keep_top_n_by_saving_per_parts_route=keep_top_n_by_saving_per_parts_route,
            keep_top_n_by_saving_per_empties_route=keep_top_n_by_saving_per_empties_route,
        )

        removed_pairs = len(self.state.feasible_pair_allocations) - len(kept_pairs)

        self.state.feasible_pair_allocations = sorted(
            kept_pairs,
            key=lambda pair: (
                self._stable_route_key(pair[0]),
                self._stable_route_key(pair[1]),
            ),
        )

        self.state.pair_saving_per_frequency = {
            pair: value
            for pair, value in self.state.pair_saving_per_frequency.items()
            if pair in kept_pairs
        }

        self.state.pairs_by_parts_route.clear()
        self.state.pairs_by_empties_route.clear()

        for pair in self.state.feasible_pair_allocations:
            parts_route, empties_route = pair
            self.state.pairs_by_parts_route[parts_route].append(pair)
            self.state.pairs_by_empties_route[empties_route].append(pair)

        self.services.tracker(f"LP pair pruning removed {removed_pairs} pair allocations")

    def _filter_route_caches(self) -> None:
        filtered_cache_keys = (
            self.state.parts_routes
            | self.state.empties_routes
            | self.inputs.locked_parts_routes
            | self.inputs.locked_empties_routes
        )

        self.state.route_frequency = {
            route: value
            for route, value in self.state.route_frequency.items()
            if route in filtered_cache_keys
        }
        self.state.route_total_cost = {
            route: value
            for route, value in self.state.route_total_cost.items()
            if route in filtered_cache_keys
        }
        self.state.route_roundtrip_total_cost = {
            route: value
            for route, value in self.state.route_roundtrip_total_cost.items()
            if route in filtered_cache_keys
        }
        self.state.route_pair_delta = {
            route: value
            for route, value in self.state.route_pair_delta.items()
            if route in filtered_cache_keys
        }

    def _solve_lp_relaxation_for_pruning(self, solver=None) -> dict:
        sorted_parts_routes = sorted(
            self.state.parts_routes,
            key=self._stable_route_key,
        )
        sorted_empties_routes = sorted(
            self.state.empties_routes,
            key=self._stable_route_key,
        )
        sorted_hub_first_leg_options = sorted(
            self.state.hub_first_leg_options,
            key=self._stable_hub_first_leg_key,
        )
        sorted_hub_linehaul_options = sorted(
            self.state.hub_linehaul_options,
            key=self._stable_hub_linehaul_key,
        )
        sorted_pairs = sorted(
            self.state.feasible_pair_allocations,
            key=lambda pair: (
                self._stable_route_key(pair[0]),
                self._stable_route_key(pair[1]),
            ),
        )

        lp_model = pulp.LpProblem("Atomic_Route_Allocation_LP_Prune", pulp.LpMinimize)

        use_parts_route = pulp.LpVariable.dicts(
            name="use_parts_route_lp_prune",
            indices=sorted_parts_routes,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        use_empties_route = pulp.LpVariable.dicts(
            name="use_empties_route_lp_prune",
            indices=sorted_empties_routes,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        pair_frequency = pulp.LpVariable.dicts(
            name="pair_frequency_lp_prune",
            indices=sorted_pairs,
            lowBound=0,
            cat="Continuous",
        )
        use_hub_first_leg = pulp.LpVariable.dicts(
            name="use_hub_first_leg_lp_prune",
            indices=sorted_hub_first_leg_options,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )
        use_hub_linehaul = pulp.LpVariable.dicts(
            name="use_hub_linehaul_lp_prune",
            indices=sorted_hub_linehaul_options,
            lowBound=0,
            upBound=1,
            cat="Continuous",
        )

        lp_model += (
            pulp.lpSum(
                self.state.route_total_cost[route] * use_parts_route[route]
                for route in sorted_parts_routes
            )
            + pulp.lpSum(
                self.state.route_total_cost[route] * use_empties_route[route]
                for route in sorted_empties_routes
            )
            - pulp.lpSum(
                self.state.pair_saving_per_frequency[pair] * pair_frequency[pair]
                for pair in sorted_pairs
            )
            + pulp.lpSum(
                option.total_cost * use_hub_first_leg[option]
                for option in sorted_hub_first_leg_options
            )
            + pulp.lpSum(
                option.total_cost * use_hub_linehaul[option]
                for option in sorted_hub_linehaul_options
            )
        )

        for shipper in sorted(
            self.inputs.parts_shippers,
            key=lambda s: getattr(s, "id", str(s)),
        ):
            lp_model += (
                pulp.lpSum(
                    use_parts_route[route]
                    for route in sorted_parts_routes
                    if shipper in route.demand.pattern.shippers
                )
                + pulp.lpSum(
                    use_hub_first_leg[option]
                    for option in self.state.first_leg_options_by_shipper_flow.get(
                        (shipper, "parts"),
                        [],
                    )
                )
                == 1
            )

        for shipper in sorted(
            self.inputs.empties_shippers,
            key=lambda s: getattr(s, "id", str(s)),
        ):
            lp_model += (
                pulp.lpSum(
                    use_empties_route[route]
                    for route in sorted_empties_routes
                    if shipper in route.demand.pattern.shippers
                )
                + pulp.lpSum(
                    use_hub_first_leg[option]
                    for option in self.state.first_leg_options_by_shipper_flow.get(
                        (shipper, "empties"),
                        [],
                    )
                )
                == 1
            )

        self._add_lp_pair_capacity_constraints(
            lp_model=lp_model,
            use_parts_route=use_parts_route,
            use_empties_route=use_empties_route,
            pair_frequency=pair_frequency,
            sorted_parts_routes=sorted_parts_routes,
            sorted_empties_routes=sorted_empties_routes,
        )

        self._add_lp_hub_constraints(
            lp_model=lp_model,
            use_hub_first_leg=use_hub_first_leg,
            use_hub_linehaul=use_hub_linehaul,
        )

        if solver is None:
            solver = pulp.PULP_CBC_CMD(msg=False)

        lp_model.solve(solver)
        status = pulp.LpStatus[lp_model.status]

        return {
            "status": status,
            "parts_lp_values": {
                route: float(pulp.value(var) or 0.0)
                for route, var in use_parts_route.items()
            },
            "empties_lp_values": {
                route: float(pulp.value(var) or 0.0)
                for route, var in use_empties_route.items()
            },
            "parts_reduced_costs": {
                route: float(var.dj or 0.0)
                for route, var in use_parts_route.items()
            },
            "empties_reduced_costs": {
                route: float(var.dj or 0.0)
                for route, var in use_empties_route.items()
            },
            "pair_lp_values": {
                pair: float(pulp.value(var) or 0.0)
                for pair, var in pair_frequency.items()
            },
            "pair_reduced_costs": {
                pair: float(var.dj or 0.0)
                for pair, var in pair_frequency.items()
            },
        }

    def _add_lp_pair_capacity_constraints(
        self,
        *,
        lp_model,
        use_parts_route,
        use_empties_route,
        pair_frequency,
        sorted_parts_routes,
        sorted_empties_routes,
    ) -> None:
        for parts_route in sorted_parts_routes:
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.state.pairs_by_parts_route.get(parts_route, [])
                )
                <= self.state.route_frequency[parts_route] * use_parts_route[parts_route]
            )

        for empties_route in sorted_empties_routes:
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.state.pairs_by_empties_route.get(empties_route, [])
                )
                <= self.state.route_frequency[empties_route] * use_empties_route[empties_route]
            )

        for fixed_parts_route in sorted(
            self.inputs.locked_parts_routes,
            key=self._stable_route_key,
        ):
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.state.pairs_by_parts_route.get(
                        fixed_parts_route,
                        [],
                    )
                )
                <= self.state.route_frequency[fixed_parts_route]
            )

        for fixed_empties_route in sorted(
            self.inputs.locked_empties_routes,
            key=self._stable_route_key,
        ):
            lp_model += (
                pulp.lpSum(
                    pair_frequency[pair]
                    for pair in self.state.pairs_by_empties_route.get(
                        fixed_empties_route,
                        [],
                    )
                )
                <= self.state.route_frequency[fixed_empties_route]
            )

    def _add_lp_hub_constraints(
        self,
        *,
        lp_model,
        use_hub_first_leg,
        use_hub_linehaul,
    ) -> None:
        for option in self.state.hub_first_leg_options:
            if option.is_locked:
                lp_model += use_hub_first_leg[option] == 1

        for hub_flow, first_leg_options in self.state.first_leg_options_by_hub_flow.items():
            linehaul_options = self.state.linehaul_options_by_hub_flow.get(
                hub_flow,
                [],
            )

            if not linehaul_options:
                for option in first_leg_options:
                    lp_model += use_hub_first_leg[option] == 0
                continue

            lp_model += (
                pulp.lpSum(
                    use_hub_linehaul[linehaul]
                    for linehaul in linehaul_options
                )
                <= 1
            )

            lp_model += (
                pulp.lpSum(
                    option.chargeable_weight * use_hub_first_leg[option]
                    for option in first_leg_options
                )
                <= pulp.lpSum(
                    linehaul.capacity_chargeable_weight * use_hub_linehaul[linehaul]
                    for linehaul in linehaul_options
                )
            )

            for option in first_leg_options:
                lp_model += (
                    option.first_leg_frequency * use_hub_first_leg[option]
                    <= pulp.lpSum(
                        linehaul.frequency * use_hub_linehaul[linehaul]
                        for linehaul in linehaul_options
                    )
                )

    @staticmethod
    def _stable_hub_first_leg_key(option) -> tuple:
        hub = getattr(option.hub_template, "core_hub", option.hub_template)
        return (
            getattr(option.shipper, "id", str(option.shipper)),
            option.flow_direction,
            getattr(hub, "cofor", str(hub)),
            getattr(option.carrier, "group", str(option.carrier)),
            getattr(option.vehicle, "id", str(option.vehicle)),
        )

    @staticmethod
    def _stable_hub_linehaul_key(option) -> tuple:
        hub = getattr(option.hub_template, "core_hub", option.hub_template)
        return (
            getattr(hub, "cofor", str(hub)),
            option.flow_direction,
            option.transport_concept,
            option.frequency,
            getattr(option.carrier, "group", str(option.carrier)),
            getattr(option.vehicle, "id", str(option.vehicle)),
        )

    def _select_routes_to_keep_from_lp(
        self,
        *,
        routes: set[DirectRoute],
        shippers: set[Shipper],
        lp_values: dict[DirectRoute, float],
        reduced_costs: dict[DirectRoute, float],
        lp_value_epsilon: float,
        reduced_cost_floor: float,
        reduced_cost_ratio: float,
        keep_top_n_per_shipper: int,
    ) -> set[DirectRoute]:
        kept_routes = set()

        def reduced_cost_threshold(route: DirectRoute) -> float:
            return max(
                reduced_cost_floor,
                reduced_cost_ratio * self.state.route_total_cost[route],
            )

        def ranking_key(route: DirectRoute) -> tuple:
            rc = reduced_costs.get(route, 0.0)
            lp = lp_values.get(route, 0.0)

            return (
                rc,
                -lp,
                self.state.route_frequency[route],
                self.state.route_total_cost[route],
                self._stable_route_key(route),
            )

        for route in routes:
            lp_value = lp_values.get(route, 0.0)
            reduced_cost = reduced_costs.get(route, 0.0)

            if lp_value > lp_value_epsilon:
                kept_routes.add(route)
                continue

            if reduced_cost <= reduced_cost_threshold(route):
                kept_routes.add(route)

        sorted_routes = sorted(routes, key=ranking_key)

        for shipper in shippers:
            shipper_routes = [
                route
                for route in sorted_routes
                if shipper in route.demand.pattern.shippers
            ]
            kept_routes.update(shipper_routes[:keep_top_n_per_shipper])

        return kept_routes

    def _select_pairs_to_keep_from_lp(
        self,
        *,
        pairs: list[tuple[DirectRoute, DirectRoute]],
        pair_lp_values: dict[tuple[DirectRoute, DirectRoute], float],
        pair_reduced_costs: dict[tuple[DirectRoute, DirectRoute], float],
        lp_value_epsilon: float,
        reduced_cost_floor: float,
        reduced_cost_ratio: float,
        keep_top_n_per_parts_route: int,
        keep_top_n_per_empties_route: int,
        keep_top_n_by_saving_per_parts_route: int,
        keep_top_n_by_saving_per_empties_route: int,
    ) -> set[tuple[DirectRoute, DirectRoute]]:
        kept_pairs: set[tuple[DirectRoute, DirectRoute]] = set()

        def reduced_cost_threshold(pair: tuple[DirectRoute, DirectRoute]) -> float:
            saving = self.state.pair_saving_per_frequency[pair]
            return max(reduced_cost_floor, reduced_cost_ratio * saving)

        def pair_rank_key(pair: tuple[DirectRoute, DirectRoute]) -> tuple:
            rc = pair_reduced_costs.get(pair, 0.0)
            lp = pair_lp_values.get(pair, 0.0)
            parts_route, empties_route = pair

            return (
                rc,
                -lp,
                -self.state.pair_saving_per_frequency[pair],
                self.state.route_frequency[parts_route]
                + self.state.route_frequency[empties_route],
                self._stable_route_key(parts_route),
                self._stable_route_key(empties_route),
            )

        def saving_rank_key(pair: tuple[DirectRoute, DirectRoute]) -> tuple:
            parts_route, empties_route = pair

            return (
                -self.state.pair_saving_per_frequency[pair],
                pair_reduced_costs.get(pair, 0.0),
                -pair_lp_values.get(pair, 0.0),
                self.state.route_frequency[parts_route]
                + self.state.route_frequency[empties_route],
                self._stable_route_key(parts_route),
                self._stable_route_key(empties_route),
            )

        for pair in pairs:
            lp_value = pair_lp_values.get(pair, 0.0)
            reduced_cost = pair_reduced_costs.get(pair, 0.0)

            if lp_value > lp_value_epsilon:
                kept_pairs.add(pair)
                continue

            if reduced_cost <= reduced_cost_threshold(pair):
                kept_pairs.add(pair)

        for route_pairs in self.state.pairs_by_parts_route.values():
            kept_pairs.update(
                sorted(route_pairs, key=pair_rank_key)[:keep_top_n_per_parts_route]
            )

        for route_pairs in self.state.pairs_by_empties_route.values():
            kept_pairs.update(
                sorted(route_pairs, key=pair_rank_key)[:keep_top_n_per_empties_route]
            )

        for route_pairs in self.state.pairs_by_parts_route.values():
            kept_pairs.update(
                sorted(route_pairs, key=saving_rank_key)[
                    :keep_top_n_by_saving_per_parts_route
                ]
            )

        for route_pairs in self.state.pairs_by_empties_route.values():
            kept_pairs.update(
                sorted(route_pairs, key=saving_rank_key)[
                    :keep_top_n_by_saving_per_empties_route
                ]
            )

        return kept_pairs