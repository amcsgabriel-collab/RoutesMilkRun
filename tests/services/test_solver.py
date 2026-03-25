import pulp
import pytest

from factories import make_solver, make_mr_solver, make_plant, make_fake_shipper, make_vehicle, make_carrier, \
    make_ftl_solver
from services.solver import MilkRunSolver
from tests.factories import make_vehicle_permutation_service, make_tariffs_service


# Receive a domain_data object with tariffs, shippers, sellers, etc. and then perform the solve flow, to output a "solution" object, which is a collection of routes.
# This collection of routes needs to follow a set of rules defined in each sub-solver flow.
# Also have a method to export the solution object to a "XLS table" format, according to Stellantis needs.

# Intended flow:
# Get domain objects: Plant, Shippers, Vehicles and Tariffs. Inside shippers: Carriers, Sellers
# Separate FTL points and MR points = Weight exceeds a limit. This should be modeled internally in the shipper object.
# Pass the FTL shippers to one solver, and the MR shippers to the other.

# Generate RoutePattern objects


@pytest.fixture
def solver():
    return make_solver()

@pytest.fixture()
def mr_solver():
    return make_mr_solver()

@pytest.fixture
def plant():
    return make_plant()

@pytest.fixture
def ftl_solver():
    return make_ftl_solver()


class TestShippersClassification:
    def test_ftl_shippers_correctly_separated(self, solver):
        assert all(s.is_ftl_exclusive_shipper is True for s in solver.ftl_shippers)

    def test_mr_shippers_correctly_separated(self, solver):
        assert all(s.is_ftl_exclusive_shipper is False for s in solver.mr_shippers)

    def test_not_in_both_lists(self, solver):
        assert solver.ftl_shippers.isdisjoint(solver.mr_shippers)

    def test_shippers_not_missing_from_both_lists(self, solver):
        assert len(solver.ftl_shippers) + len(solver.mr_shippers) == len(solver.context_objects.shippers)


class TestGenerateRoutePatterns:
    def test_generates_all_single_shipper_patterns(self, mr_solver):
        mr_solver.build()
        single_shipper_patterns = {p for p in mr_solver.patterns if p.count_of_stops == 1}
        assert len(single_shipper_patterns) == len(mr_solver.shippers)

    def test_no_pattern_exceeds_four_stops(self, mr_solver):
        mr_solver.build()
        assert all(p.count_of_stops <= 4 for p in mr_solver.patterns)

    def test_no_duplicate_patterns(self, mr_solver):
        mr_solver.build()
        assert len(mr_solver.patterns) == len(set(mr_solver.patterns))  # Might be redundant

    def test_every_shipper_in_at_least_one_pattern(self, mr_solver):
        mr_solver.build()
        covered = {s for p in mr_solver.patterns for s in p.shippers}
        assert covered == mr_solver.shippers

    def test_generating_correct_number_of_patterns(self, mr_solver):
        mr_solver.build()
        expected_combinations = 5 # 4 FTL routes + 2 possible MR routes - 1 blocked MR route
        assert len(mr_solver.patterns) == expected_combinations

    def test_correctly_blocking_pattern(self, mr_solver):
        mr_solver.build()
        assert mr_solver.patterns.isdisjoint(mr_solver.blocked_patterns)


class TestBuildModel:
    def test_model_is_created(self, mr_solver):
        mr_solver.build()
        assert mr_solver.model is not None

    def test_objective_is_minimization(self, mr_solver):
        mr_solver.build()
        assert mr_solver.model.sense == pulp.LpMinimize

    def test_one_constraint_per_shipper(self, mr_solver):
        mr_solver.build()
        # Number of constraints should be at least one per shipper
        assert len(mr_solver.model.constraints) >= len(mr_solver.shippers)

    def test_binary_variables_exist_for_all_routes(self, mr_solver):
        mr_solver.build()
        var_names = [v.name for v in mr_solver.model.variables()]
        assert len(var_names) == len(mr_solver.routes)

    def test_all_variables_are_binary(self, mr_solver):
        mr_solver.build()
        assert all(v.cat == "Integer" and v.upBound == 1
                   for v in mr_solver.model.variables())


class TestSolve:
    def test_solve_status_is_optimal(self, mr_solver):
        mr_solver.build()
        mr_solver.solve()
        assert mr_solver.solve_status == "Optimal"

    def test_every_shipper_is_covered(self, mr_solver):
        mr_solver.build()
        mr_solver.solve()
        for shipper in mr_solver.shippers:
            covered = any(
                shipper in route.pattern.shippers
                for route in mr_solver.solution_routes
            )
            assert covered, f"Shipper {shipper.cofor} not covered in solution"

    def test_no_shipper_covered_twice(self, mr_solver):
        mr_solver.build()
        mr_solver.solve()
        coverage_count = {s: 0 for s in mr_solver.shippers}
        for route in mr_solver.solution_routes:
            for shipper in route.pattern.shippers:
                coverage_count[shipper] += 1
        assert all(count == 1 for count in coverage_count.values())

    def test_solution_cost_is_positive(self, mr_solver):
        mr_solver.build()
        total = sum(r.total_cost for r in mr_solver.solution_routes)
        assert total >= 0


class TestSolveKnownInstance:
    """
    Use a tiny hand-crafted instance where you know the optimal solution.
    This is the most valuable test — it catches objective or constraint bugs
    that structural tests cannot.
    """
    def test_optimal_solution_on_trivial_instance(self, plant):
        """
        Two shippers, one vehicle, one possible route.
        Optimal solution must select that route.
        """
        s1 = make_fake_shipper(cofor="s1")
        s2 = make_fake_shipper(cofor="s2")
        v1 = make_vehicle(id="v1")

        mr_solver = MilkRunSolver(
            shippers={s1, s2},
            plant=plant,
            vehicle_permutation_service=make_vehicle_permutation_service({v1}),
            tariffs_service=make_tariffs_service(),
        )
        mr_solver.build()
        mr_solver.solve()

        assert mr_solver.solve_status == "Optimal"
        assert len(mr_solver.solution_routes) == 1
        assert mr_solver.solution_routes.pop().pattern.shippers == frozenset({s1, s2})

    def test_solver_picks_cheaper_route(self, plant):
        """
        Two routes cover the same shipper. Solver must pick the cheaper one.
        """
        s1 = make_fake_shipper(cofor="s1")
        v_cheap = make_vehicle(id="cheap")
        v_expensive = make_vehicle(id="expensive")

        mr_solver = MilkRunSolver(
            shippers={s1},
            plant=plant,
            vehicle_permutation_service=make_vehicle_permutation_service({v_cheap, v_expensive}),
            tariffs_service=make_tariffs_service(),  # ensure cheap < expensive in tariff table
        )
        mr_solver.build()
        mr_solver.solve()

        assert mr_solver.solution_routes.pop().vehicle.id == "cheap"


class TestFtlSolver:

    def test_creates_all_ftl_patterns(self, ftl_solver):
        ftl_solver.build()
        assert len(ftl_solver.patterns) == len(ftl_solver.shippers)

    def test_solves_for_all_shippers(self, ftl_solver):
        ftl_solver.build()
        ftl_solver.solve()
        assert len(ftl_solver.solution_routes) == len(ftl_solver.shippers)

    def test_picks_best_vehicle(self, ftl_solver):
        ftl_solver.build()
        ftl_solver.solve()
        route = ftl_solver.solution_routes.pop()
        assert route.vehicle.id == 'v1'

