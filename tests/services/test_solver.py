# tests/test_milk_run_solver.py

from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

import pulp
import pytest

from services.solver import MilkRunSolver


# Adjust this import to your real module path
# from your_package.milk_run_solver import MilkRunSolver



# ----------------------------
# Test doubles / helper models
# ----------------------------

@dataclass(frozen=True)
class Carrier:
    group: str


@dataclass(frozen=True)
class Vehicle:
    id: str


@dataclass(frozen=True)
class Point:
    zip_code: str


@dataclass(frozen=True)
class Pattern:
    shippers: frozenset
    frequency: int
    deviation: int = 0

    def order_shippers(self, distance_function):
        return None

    def calculate_deviation(self, distance_function):
        return None


@dataclass(frozen=True)
class Demand:
    pattern: Pattern


@dataclass(frozen=True)
class Shipper:
    name: str
    carrier: Carrier
    has_parts_demand: bool = False
    has_empties_demand: bool = False


@dataclass(frozen=True)
class Route:
    name: str
    carrier: Carrier
    vehicle: Vehicle
    starting_point: Point
    demand: Demand
    total_cost: int


@dataclass(frozen=True)
class Trip:
    parts_route: object
    empties_route: object


@dataclass(frozen=True)
class Plant:
    cofor: str


class DummyVehiclePermutationService:
    def __init__(self, parts_result=None, empties_result=None):
        self.parts_result = parts_result or set()
        self.empties_result = empties_result or set()
        self.calls = []

    def permutate(self, patterns):
        self.calls.append(patterns)
        # first call => parts, second call => empties
        if len(self.calls) == 1:
            return self.parts_result
        return self.empties_result


class DummyTariff:
    def __init__(self, savings):
        self._savings = savings

    def get_roundtrip_savings(self):
        return self._savings


class DummyTariffService:
    def __init__(self):
        self.ftl_tariffs = {}
        self.assigned = []

    def assign_ftl_mr_routes(self, routes):
        self.assigned.append(routes)


# ----------------------------
# Fixtures
# ----------------------------

@pytest.fixture
def base_objects():
    carrier = Carrier(group="C1")
    vehicle = Vehicle(id="V1")
    point = Point(zip_code="12345")
    plant = Plant(cofor="PLANT")

    shipper_a = Shipper("A", carrier, has_parts_demand=True, has_empties_demand=True)
    shipper_b = Shipper("B", carrier, has_parts_demand=True, has_empties_demand=False)

    parts_pattern_a = Pattern(shippers=frozenset({shipper_a}), frequency=3)
    parts_pattern_b = Pattern(shippers=frozenset({shipper_b}), frequency=2)
    empties_pattern_a = Pattern(shippers=frozenset({shipper_a}), frequency=4)

    parts_route_a = Route(
        name="parts_a",
        carrier=carrier,
        vehicle=vehicle,
        starting_point=point,
        demand=Demand(parts_pattern_a),
        total_cost=100,
    )
    parts_route_b = Route(
        name="parts_b",
        carrier=carrier,
        vehicle=vehicle,
        starting_point=point,
        demand=Demand(parts_pattern_b),
        total_cost=80,
    )
    empties_route_a = Route(
        name="empties_a",
        carrier=carrier,
        vehicle=vehicle,
        starting_point=point,
        demand=Demand(empties_pattern_a),
        total_cost=60,
    )

    return SimpleNamespace(
        carrier=carrier,
        vehicle=vehicle,
        point=point,
        plant=plant,
        shipper_a=shipper_a,
        shipper_b=shipper_b,
        parts_pattern_a=parts_pattern_a,
        parts_pattern_b=parts_pattern_b,
        empties_pattern_a=empties_pattern_a,
        parts_route_a=parts_route_a,
        parts_route_b=parts_route_b,
        empties_route_a=empties_route_a,
    )


@pytest.fixture
def solver(base_objects, monkeypatch):
    obj = base_objects

    vehicle_service = DummyVehiclePermutationService()
    tariff_service = DummyTariffService()

    s = MilkRunSolver(
        shippers={obj.shipper_a, obj.shipper_b},
        existing_trips=set(),
        plant=obj.plant,
        vehicle_permutation_service=vehicle_service,
        tariffs_service=tariff_service,
        blocked_patterns=None,
    )

    # avoid depending on external route-pattern generation funcs
    monkeypatch.setattr(
        s,
        "generate_route_patterns",
        lambda: None,
    )
    monkeypatch.setattr(
        s,
        "apply_ordering_to_route_patterns",
        lambda: None,
    )
    monkeypatch.setattr(
        s,
        "remove_high_deviation_route_patterns",
        lambda: None,
    )

    return s


# ----------------------------
# Tests
# ----------------------------

def test_all_patterns_returns_union(solver):
    carrier = Carrier("C1")
    shipper = Shipper("A", carrier, True, True)
    p1 = Pattern(frozenset({shipper}), 1)
    p2 = Pattern(frozenset({shipper}), 2)

    solver.parts_patterns = {p1}
    solver.empties_patterns = {p2}

    assert solver.all_patterns == {p1, p2}


def test_build_groups_routes_by_carrier_vehicle_zip(solver, base_objects):
    obj = base_objects

    solver.vehicle_permutation_service.parts_result = {
        obj.parts_route_a,
        obj.parts_route_b,
    }
    solver.vehicle_permutation_service.empties_result = {
        obj.empties_route_a,
    }

    build_model_mock = Mock()
    solver.build_model = build_model_mock

    solver.build()

    key = (obj.carrier.group, obj.vehicle.id, obj.point.zip_code)

    assert solver.parts_routes == {obj.parts_route_a, obj.parts_route_b}
    assert solver.empties_routes == {obj.empties_route_a}
    assert set(solver.parts_routes_by_group[key]) == {obj.parts_route_a, obj.parts_route_b}
    assert set(solver.empties_routes_by_group[key]) == {obj.empties_route_a}
    assert solver.roundtrip_groups == {key}
    build_model_mock.assert_called_once()


def test_build_filters_out_zero_cost_routes(solver, base_objects):
    obj = base_objects
    zero_cost_route = Route(
        name="zero",
        carrier=obj.carrier,
        vehicle=obj.vehicle,
        starting_point=obj.point,
        demand=Demand(Pattern(frozenset({obj.shipper_a}), 1)),
        total_cost=0,
    )

    solver.vehicle_permutation_service.parts_result = {obj.parts_route_a, zero_cost_route}
    solver.vehicle_permutation_service.empties_result = set()
    solver.build_model = Mock()

    solver.build()

    assert solver.parts_routes == {obj.parts_route_a}
    assert zero_cost_route not in solver.parts_routes


def test_get_roundtrip_savings_by_group_populates_dict(solver, base_objects, monkeypatch):
    obj = base_objects
    group = (obj.carrier.group, obj.vehicle.id, obj.point.zip_code)
    solver.roundtrip_groups = {group}

    monkeypatch.setitem(
        solver.tariffs_service.ftl_tariffs,
        (group[0], group[1], 35, group[2], obj.plant.cofor),
        DummyTariff(42),
    )

    import services.solver
    monkeypatch.setattr(services.solver, "get_deviation_bin", lambda x: (35, 50))

    solver.get_roundtrip_savings_by_group()

    assert solver.roundtrip_saving_by_group[group] == 42


def test_build_model_creates_decision_variables_and_constraints(solver, base_objects):
    obj = base_objects
    group = (obj.carrier.group, obj.vehicle.id, obj.point.zip_code)

    solver.parts_routes = {obj.parts_route_a, obj.parts_route_b}
    solver.empties_routes = {obj.empties_route_a}
    solver.parts_routes_by_group = defaultdict(list, {
        group: [obj.parts_route_a, obj.parts_route_b]
    })
    solver.empties_routes_by_group = defaultdict(list, {
        group: [obj.empties_route_a]
    })
    solver.roundtrip_groups = {group}
    solver.roundtrip_saving_by_group[group] = 10

    solver.build_model()

    assert solver.model is not None
    assert set(solver.use_parts_route_bin.keys()) == {obj.parts_route_a, obj.parts_route_b}
    assert set(solver.use_empties_route_bin.keys()) == {obj.empties_route_a}
    assert set(solver.roundtrips_by_group.keys()) == {group}

    constraint_names = set(solver.model.constraints.keys())

    assert f"roundtrip_parts_cap_{group[0]}_{group[1]}_{group[2]}" in constraint_names
    assert f"roundtrip_empties_cap_{group[0]}_{group[1]}_{group[2]}" in constraint_names

    # shipper_a has parts + empties; shipper_b has parts only
    assert len(solver.model.constraints) == 5


def test_convert_solutions_extracts_selected_routes(solver, base_objects):
    obj = base_objects

    solver.use_parts_route_bin = {
        obj.parts_route_a: pulp.LpVariable("parts_a", cat="Binary"),
        obj.parts_route_b: pulp.LpVariable("parts_b", cat="Binary"),
    }
    solver.use_empties_route_bin = {
        obj.empties_route_a: pulp.LpVariable("empties_a", cat="Binary"),
    }

    solver.use_parts_route_bin[obj.parts_route_a].varValue = 1
    solver.use_parts_route_bin[obj.parts_route_b].varValue = 0
    solver.use_empties_route_bin[obj.empties_route_a].varValue = 1

    solver.convert_solutions()

    assert solver.solution_parts_routes == {obj.parts_route_a}
    assert solver.solution_empties_routes == {obj.empties_route_a}


def test_solve_calls_solve_model_and_convert_solutions(solver):
    solver.solve_model = Mock()
    solver.convert_solutions = Mock()
    solver.combine_roundtrips = Mock()

    solver.solve()

    solver.solve_model.assert_called_once()
    solver.convert_solutions.assert_called_once()
    solver.combine_roundtrips.assert_called_once()


def test_combine_roundtrips_groups_selected_routes_and_calls_iterator(solver, base_objects, monkeypatch):
    obj = base_objects

    solver.solution_parts_routes = {obj.parts_route_a, obj.parts_route_b}
    solver.solution_empties_routes = {obj.empties_route_a}
    group = (obj.carrier.group, obj.vehicle.id, obj.point.zip_code)

    var = pulp.LpVariable("rt", lowBound=0, cat="Integer")
    var.varValue = 3
    solver.roundtrips_by_group = {group: var}

    captured = {}

    def fake_group_key(route):
        return route.carrier.group, route.vehicle.id, route.starting_point.zip_code

    def fake_iterate_trip_combination(
        selected_parts_by_group,
        selected_empties_by_group,
        roundtrip_allocations,
    ):
        captured["selected_parts_by_group"] = selected_parts_by_group
        captured["selected_empties_by_group"] = selected_empties_by_group
        captured["roundtrip_allocations"] = roundtrip_allocations
        return {"trip_1", "trip_2"}

    import services.solver
    monkeypatch.setattr(services.solver, "_group_key", fake_group_key)
    monkeypatch.setattr(services.solver, "iterate_trip_combination", fake_iterate_trip_combination)

    solver.combine_roundtrips()

    assert set(captured["selected_parts_by_group"][group]) == {obj.parts_route_a, obj.parts_route_b}
    assert set(captured["selected_empties_by_group"][group]) == {obj.empties_route_a}
    assert captured["roundtrip_allocations"] == {group: 3}
    assert solver.solution_trips == {"trip_1", "trip_2"}


def test_solve_model_raises_when_not_optimal(solver, monkeypatch):
    class DummyNonOptimal(Exception):
        pass

    import services.solver
    monkeypatch.setattr(services.solver, "NonOptimalSolutionError", DummyNonOptimal)

    solver.model = pulp.LpProblem("test", pulp.LpMinimize)

    def fake_solve(_solver):
        solver.model.status = pulp.LpStatusInfeasible

    monkeypatch.setattr(solver.model, "solve", fake_solve)

    with pytest.raises(DummyNonOptimal):
        solver.solve_model()


def test_build_calls_get_roundtrip_savings_by_group(solver, base_objects):
    obj = base_objects
    solver.vehicle_permutation_service.parts_result = {obj.parts_route_a}
    solver.vehicle_permutation_service.empties_result = {obj.empties_route_a}

    solver.get_roundtrip_savings_by_group = Mock()
    solver.build_model = Mock()

    solver.build()

    solver.get_roundtrip_savings_by_group.assert_called_once()