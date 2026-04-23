import pytest
from math import ceil

from domain.exceptions import DeviationNotCalculatedError, RouteNotOrderedError
from domain.operational_route import OperationalRoute
from tests.factories import make_vehicle, make_pattern_with_demand, make_basic_pattern, make_fake_shipper, make_plant, \
    make_ordered_pattern


@pytest.fixture
def default_route():
    """A balanced route where weight is the binding constraint."""
    vehicle = make_vehicle(
        weight_capacity=10_000,
        volume_capacity=100,
        loading_meters_capacity=13.6,
    )
    pattern = make_pattern_with_demand(
        weight=5_000,
        volume=50,
        loading_meters=6.8,
        count_of_stops=2,
        overutilization=1.05,
    )
    route = OperationalRoute(pattern=pattern, vehicle=vehicle)
    return route, pattern, vehicle


class TestTariffKey:

    def test_cant_get_tariff_key_before_ordering(self):
        s1 = make_fake_shipper()
        s2 = make_fake_shipper(cofor="s2")
        pattern = make_basic_pattern({s1, s2}, make_plant())
        vehicle = make_vehicle()
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)

        with pytest.raises(
                RouteNotOrderedError,
                match="Route pattern not yet ordered. Unable to create tariff key"
        ):
            route.tariff_key

    def test_cant_get_tariff_key_without_deviation(self):
        s1 = make_fake_shipper()
        s2 = make_fake_shipper(cofor="s2")
        pattern = make_ordered_pattern({s1, s2}, make_plant())
        vehicle = make_vehicle()
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)

        with pytest.raises(
                DeviationNotCalculatedError,
                match="Deviation Bin not yet calculated. Unable to create tariff key"
        ):
            route.tariff_key

    def test_tariff_key_is_tuple(self, default_route):
        route, pattern, vehicle = default_route
        assert isinstance(route.tariff_key, tuple)

    def test_tariff_key_has_five_elements(self, default_route):
        route, _, _ = default_route
        assert len(route.tariff_key) == 5

    def test_tariff_key_carrier_short_name(self, default_route):
        route, pattern, _ = default_route
        assert route.tariff_key[0] == pattern.carrier

    def test_tariff_key_vehicle(self, default_route):
        route, _, vehicle = default_route
        assert route.tariff_key[1] == vehicle.id

    def test_tariff_key_deviation_bin(self, default_route):
        route, pattern, _ = default_route
        assert route.tariff_key[2] == pattern.deviation_bin

    def test_tariff_key_zip_key(self, default_route):
        route, pattern, _ = default_route
        assert route.tariff_key[3] == pattern.starting_point.zip_key

    def test_tariff_key_cofor(self, default_route):
        route, pattern, _ = default_route
        assert route.tariff_key[4] == pattern.starting_point.cofor


class TestFrequency:
    def test_frequency_is_ceil(self, default_route):
        """Frequency must always be a ceiling, never fractional."""
        route, _, _ = default_route
        assert isinstance(route.frequency, int)

    def test_frequency_weight_is_binding(self):
        """When weight drives frequency, the result reflects that constraint."""
        vehicle = make_vehicle(weight_capacity=3_000, volume_capacity=1_000, loading_meters_capacity=1_000)
        pattern = make_pattern_with_demand(weight=10_000, volume=100, loading_meters=10, overutilization=1.0)
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)
        expected = ceil(10_000 / (3_000 * 1.0))  # overutilization=1.0 → divisor=capacity
        assert route.frequency == expected

    def test_frequency_volume_is_binding(self):
        vehicle = make_vehicle(weight_capacity=1_000_000, volume_capacity=10, loading_meters_capacity=1_000)
        pattern = make_pattern_with_demand(weight=1, volume=100, loading_meters=1, overutilization=1.0)
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)
        expected = ceil(100 / 10)
        assert route.frequency == expected

    def test_frequency_loading_meters_is_binding(self):
        vehicle = make_vehicle(weight_capacity=1_000_000, volume_capacity=1_000_000, loading_meters_capacity=5)
        pattern = make_pattern_with_demand(weight=1, volume=1, loading_meters=50, overutilization=1.0)
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)
        expected = ceil(50 / 5)
        assert route.frequency == expected

    def test_frequency_with_overutilization_reduces_trips(self):
        """Overutilization allowance should reduce the number of required trips."""
        vehicle = make_vehicle(weight_capacity=10_000, volume_capacity=1_000, loading_meters_capacity=1_000)
        pattern_no_ou = make_pattern_with_demand(weight=10_500, volume=1, loading_meters=1, overutilization=1.0)
        pattern_with_ou = make_pattern_with_demand(weight=10_500, volume=1, loading_meters=1, overutilization=1.05)
        route_no_ou = OperationalRoute(pattern=pattern_no_ou, vehicle=vehicle)
        route_with_ou = OperationalRoute(pattern=pattern_with_ou, vehicle=vehicle)
        assert route_with_ou.frequency <= route_no_ou.frequency

    def test_frequency_minimum_is_one(self):
        """Even a near-empty route should require at least 1 trip."""
        vehicle = make_vehicle(weight_capacity=100_000, volume_capacity=100_000, loading_meters_capacity=100_000)
        pattern = make_pattern_with_demand(weight=1, volume=1, loading_meters=1, overutilization=1.0)
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)
        assert route.frequency >= 1


class TestUtilization:
    def test_utilizations_are_between_zero_and_one(self, default_route):
        route, _, _ = default_route
        for utilization in (route.weight_utilization, route.volume_utilization, route.loading_meters_utilization):
            assert 0 < utilization <= 1.05  # allow overutilization headroom

    def test_max_utilization_is_max_of_three(self, default_route):
        route, _, _ = default_route
        assert route.max_utilization == max(
            route.weight_utilization,
            route.volume_utilization,
            route.loading_meters_utilization,
        )

    def test_weight_utilization_formula(self):
        vehicle = make_vehicle(weight_capacity=10_000, volume_capacity=100_000, loading_meters_capacity=100_000)
        pattern = make_pattern_with_demand(weight=8_000, volume=1, loading_meters=1, overutilization=1.0)
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)
        expected = 8_000 / (10_000 * route.frequency)
        assert route.weight_utilization == pytest.approx(expected)

    def test_fully_loaded_vehicle_has_utilization_near_one(self):
        vehicle = make_vehicle(weight_capacity=10_000, volume_capacity=100_000, loading_meters_capacity=100_000)
        pattern = make_pattern_with_demand(weight=10_000, volume=1, loading_meters=1, overutilization=1.0)
        route = OperationalRoute(pattern=pattern, vehicle=vehicle)
        assert route.weight_utilization == pytest.approx(1.0)


class TestCosts:
    def test_initial_costs_are_zero(self, default_route):
        route, _, _ = default_route
        assert route.base_cost == 0
        assert route.stop_cost == 0

    def test_route_cost_with_no_stop_cost(self, default_route):
        route, _, _ = default_route
        route.base_cost = 500
        route.stop_cost = 0
        assert route.route_cost == 500

    def test_route_cost_formula(self, default_route):
        route, pattern, _ = default_route
        route.base_cost = 500
        route.stop_cost = 50
        expected = 500 + 50 * pattern.count_of_stops
        assert route.route_cost == expected

    def test_total_cost_is_route_cost_times_frequency(self, default_route):
        route, _, _ = default_route
        route.base_cost = 500
        route.stop_cost = 50
        assert route.total_cost == pytest.approx(route.route_cost * route.frequency)

    def test_total_cost_scales_with_frequency(self):
        """A route that needs more trips should cost proportionally more."""
        vehicle = make_vehicle(weight_capacity=1_000, volume_capacity=100_000, loading_meters_capacity=100_000)
        pattern_light = make_pattern_with_demand(weight=500, volume=1, loading_meters=1, overutilization=1.0)
        pattern_heavy = make_pattern_with_demand(weight=5_000, volume=1, loading_meters=1, overutilization=1.0)

        route_light = OperationalRoute(pattern=pattern_light, vehicle=vehicle)
        route_heavy = OperationalRoute(pattern=pattern_heavy, vehicle=vehicle)

        route_light.base_cost = route_heavy.base_cost = 1_000
        route_light.stop_cost = route_heavy.stop_cost = 0

        assert route_heavy.total_cost > route_light.total_cost
