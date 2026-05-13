from collections import defaultdict
from dataclasses import field, dataclass

from rob_4flow.domain.routes.direct_route import DirectRoute
from rob_4flow.domain.routes.route_pattern import RoutePattern
from rob_4flow.domain.shipper import Shipper


def _route_counts_by_shipper(routes, shippers):
    counts = [
        sum(1 for r in routes if shipper in r.demand.pattern.shippers)
        for shipper in shippers
    ]
    return {
        "avg": sum(counts) / len(counts) if counts else 0,
        "max": max(counts, default=0),
    }


def _pair_counts_by_route(routes, pairs_by_route):
    counts = [len(pairs_by_route.get(route, [])) for route in routes]
    return {
        "avg": sum(counts) / len(counts) if counts else 0,
        "max": max(counts, default=0),
    }


def _range(values):
    values = list(values)
    return min(values, default=0), max(values, default=0)


@dataclass
class MilkRunSolverState:
    non_exclusive_parts_shippers: set[Shipper] = field(default_factory=set)
    non_exclusive_empties_shippers: set[Shipper] = field(default_factory=set)
    ftl_exclusive_parts_shippers: set[Shipper] = field(default_factory=set)
    ftl_exclusive_empties_shippers: set[Shipper] = field(default_factory=set)

    existing_parts_patterns: set[RoutePattern] = field(default_factory=set)
    existing_empties_patterns: set[RoutePattern] = field(default_factory=set)

    parts_patterns: set[RoutePattern] = field(default_factory=set)
    empties_patterns: set[RoutePattern] = field(default_factory=set)

    parts_routes: set[DirectRoute] = field(default_factory=set)
    empties_routes: set[DirectRoute] = field(default_factory=set)

    locked_parts_routes: set[DirectRoute] = field(default_factory=set)
    locked_empties_routes: set[DirectRoute] = field(default_factory=set)

    route_frequency: dict = field(default_factory=dict)
    route_total_cost: dict = field(default_factory=dict)
    route_roundtrip_total_cost: dict = field(default_factory=dict)
    route_pair_delta: dict = field(default_factory=dict)

    parts_routes_by_group: dict = field(default_factory=lambda: defaultdict(list))
    empties_routes_by_group: dict = field(default_factory=lambda: defaultdict(list))
    locked_parts_routes_by_group: dict = field(default_factory=lambda: defaultdict(list))
    locked_empties_routes_by_group: dict = field(default_factory=lambda: defaultdict(list))

    feasible_pair_allocations: list = field(default_factory=list)
    pair_saving_per_frequency: dict = field(default_factory=dict)
    pairs_by_parts_route: dict = field(default_factory=lambda: defaultdict(list))
    pairs_by_empties_route: dict = field(default_factory=lambda: defaultdict(list))

    hub_first_leg_options: set = field(default_factory=set)
    hub_linehaul_options: set = field(default_factory=set)
    first_leg_options_by_shipper_flow: dict = field(default_factory=lambda: defaultdict(list))
    first_leg_options_by_hub_flow: dict = field(default_factory=lambda: defaultdict(list))
    linehaul_options_by_hub_flow: dict = field(default_factory=lambda: defaultdict(list))

    model: object | None = None
    use_parts_route_bin: object | None = None
    use_empties_route_bin: object | None = None
    pair_frequency: object | None = None
    use_hub_first_leg_bin: object | None = None
    use_hub_linehaul_bin: object | None = None

    solve_status: str = "Not Solved Yet"

    solution_parts_routes: set = field(default_factory=set)
    solution_empties_routes: set = field(default_factory=set)
    solution_pair_allocations: dict = field(default_factory=dict)
    solution_first_leg_options: set = field(default_factory=set)
    solution_linehaul_options: set = field(default_factory=set)
    solution_hubs: set = field(default_factory=set)

    @property
    def parts_shippers(self):
        return self.non_exclusive_parts_shippers | self.ftl_exclusive_parts_shippers

    @property
    def empties_shippers(self):
        return self.non_exclusive_empties_shippers | self.ftl_exclusive_empties_shippers

    @property
    def hub_option_summary(self):
        return (
            f"Generated {len(self.hub_first_leg_options)} first-leg hub options and "
            f"{len(self.hub_linehaul_options)} linehaul options"
        )

    @property
    def pattern_summary(self):
        return (
            f"Generated {len(self.parts_patterns)} parts patterns and "
            f"{len(self.empties_patterns)} empties patterns"
        )

    @property
    def filtered_pattern_summary(self):
        return (
            f"Retained {len(self.parts_patterns)} parts patterns and "
            f"{len(self.empties_patterns)} empties patterns after deviation filter"
        )

    @property
    def route_summary(self):
        return (
            f"Created {len(self.parts_routes)} feasible parts routes and "
            f"{len(self.empties_routes)} feasible empties routes"
        )

    @property
    def non_dominated_route_summary(self):
        return (
            f"Retained {len(self.parts_routes)} non-dominated parts routes and "
            f"{len(self.empties_routes)} non-dominated empties routes"
        )

    @property
    def roundtrip_pair_summary(self):
        return (
            f"Built {len(self.feasible_pair_allocations)} feasible roundtrip pair allocations"
        )

    @property
    def route_pruning_summary(self):
        return (
            f"Retained {len(self.parts_routes)} parts routes and "
            f"{len(self.empties_routes)} empties routes after conservative LP pruning"
        )

    @property
    def pair_pruning_summary(self):
        return (
            f"Retained {len(self.feasible_pair_allocations)} feasible roundtrip pair allocations "
            f"after conservative LP pair pruning"
        )

    @property
    def model_summary(self):
        parts_routes_per_shipper = _route_counts_by_shipper(
            self.parts_routes,
            getattr(self, "parts_shippers", set()),
        )
        empties_routes_per_shipper = _route_counts_by_shipper(
            self.empties_routes,
            getattr(self, "empties_shippers", set()),
        )

        pairs_per_parts_route = _pair_counts_by_route(
            self.parts_routes,
            self.pairs_by_parts_route,
        )
        pairs_per_empties_route = _pair_counts_by_route(
            self.empties_routes,
            self.pairs_by_empties_route,
        )

        fixed_parts_routes = getattr(self, "locked_parts_routes", set())
        fixed_empties_routes = getattr(self, "locked_empties_routes", set())

        constraints = (
            len(self.model.constraints)
            if self.model is not None and hasattr(self.model, "constraints")
            else 0
        )

        binary_vars = (
                len(self.parts_routes)
                + len(self.empties_routes)
                + len(self.hub_first_leg_options)
                + len(self.hub_linehaul_options)
        )
        continuous_vars = len(self.feasible_pair_allocations)

        return "\n".join([
            "Optimization model ready:",
            f"  Constraints: {constraints}",
            f"  Variables: {binary_vars} binary, {continuous_vars} continuous",
            f"  Routes: parts={len(self.parts_routes)}, empties={len(self.empties_routes)}",
            f"  Fixed: parts={len(fixed_parts_routes)}, empties={len(fixed_empties_routes)}",
            f"  Pair vars: {len(self.feasible_pair_allocations)}",
            f"  Parts routes/shipper: avg={parts_routes_per_shipper['avg']:.2f}, max={parts_routes_per_shipper['max']}",
            f"  Empties routes/shipper: avg={empties_routes_per_shipper['avg']:.2f}, max={empties_routes_per_shipper['max']}",
            f"  Pairs per parts route: avg={pairs_per_parts_route['avg']:.2f}, max={pairs_per_parts_route['max']}",
            f"  Pairs per empties route: avg={pairs_per_empties_route['avg']:.2f}, max={pairs_per_empties_route['max']}",
            f"  Cost range: {_range(self.route_total_cost.values())}",
            f"  Pair saving range: {_range(self.pair_saving_per_frequency.values())}",
            f"  Frequency range: {_range(self.route_frequency.values())}",
        ])

    @property
    def solution_summary(self):
        return "\n".join([
            "Solution ready:",
            f"  Status: {self.solve_status}",
            f"  Parts routes: {len(self.solution_parts_routes)}",
            f"  Empties routes: {len(self.solution_empties_routes)}",
            f"  Roundtrip pair allocations: {len(self.solution_pair_allocations)}",
            f"  First-leg hub options: {len(self.solution_first_leg_options)}",
            f"  Linehaul hub options: {len(self.solution_linehaul_options)}",
            f"  Hubs: {len(self.solution_hubs)}",
        ])