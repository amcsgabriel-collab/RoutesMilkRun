import pytest

from domain.domain_algorithms import get_deviation_bin
from domain.data_structures import Plant
from tests.factories import make_carrier, make_fake_shipper, make_basic_pattern, make_ordered_pattern, \
    DISTANCE_FUNCTION, make_plant


# ------------------------------------------------------------------------------------------
# FIXTURES
# ------------------------------------------------------------------------------------------

@pytest.fixture
def shippers():
    s1 = make_fake_shipper("s1", (10, 0), 2000, 2, 10)
    s2 = make_fake_shipper("s2", (20, 5), 2000, 3, 15)
    s3 = make_fake_shipper("s3", (30, 0), 2500, 2, 30)
    s4 = make_fake_shipper("s4", (25, 0), 7500, 6, 50)
    s5 = make_fake_shipper("s5", (30, -5), 7500, 10, 50)
    return [s1, s2, s3, s4, s5]


@pytest.fixture
def plant():
    return make_plant()

# ------------------------------------------------------------------------------------------
# ROUTE PATTERN TESTS
# ------------------------------------------------------------------------------------------

class TestRoutePatternCreation:
    def test_single_shipper_created_successfully(self, plant, shippers):
        r = make_basic_pattern(shippers[:1], plant)
        assert r.count_of_stops == 1

    def test_four_shippers_created_successfully(self, plant, shippers):
        r = make_basic_pattern(shippers[:4], plant)
        assert r.count_of_stops == 4

    def test_five_shippers_raises(self, plant, shippers):
        with pytest.raises(ValueError, match="Milkrun routes cannot have more than 4 stops. Got 5"):
            make_basic_pattern(shippers, plant)

    def test_empty_shippers_raises(self, plant):
        with pytest.raises(ValueError, match="Passed shippers list is empty. Please verify."):
            make_basic_pattern([], plant)

    def test_shippers_stored_as_frozenset(self, plant, shippers):
        r = make_basic_pattern(shippers[:2], plant)
        assert isinstance(r.shippers, frozenset)

    def test_count_of_stops_matches_input(self, plant, shippers):
        for n in range(1, 5):
            r = make_basic_pattern(shippers[:n], plant)
            assert r.count_of_stops == n

    def test_single_carrier_works(self, plant, shippers):
        r = make_basic_pattern(shippers[:3], plant)
        assert r.carrier == "DHL"

    def test_multiple_carriers_different_groups_raises_error(self, plant):
        carrier1 = make_carrier('C1', 'Carrier1', group='C1')
        carrier2 = make_carrier('C2', 'Carrier2', group='C2')
        s1 = make_fake_shipper(carrier=carrier1)
        s2 = make_fake_shipper(carrier=carrier2)
        with pytest.raises(
                ValueError,
                match='Milkrun routes cannot have more than one carrier'):
            make_basic_pattern({s1, s2}, plant)

    def test_multiple_carriers_in_same_group_works(self, plant):
        carrier1 = make_carrier('C1', 'Carrier1', group='C1')
        carrier2 = make_carrier('C2', 'Carrier2', group='C1')
        s1 = make_fake_shipper(carrier=carrier1)
        s2 = make_fake_shipper(carrier=carrier2)
        r = make_basic_pattern({s1, s2}, plant)
        assert r.carrier == "C1"


class TestRoutePatternIdentity:
    def test_same_shippers_are_equal(self, plant, shippers):
        r1 = make_basic_pattern(shippers[:3], plant)
        r2 = make_basic_pattern(shippers[:3], plant)
        assert r1 == r2

    def test_same_shippers_have_same_hash(self, plant, shippers):
        r1 = make_basic_pattern(shippers[:3], plant)
        r2 = make_basic_pattern(shippers[:3], plant)
        assert hash(r1) == hash(r2)

    def test_different_shippers_are_not_equal(self, plant, shippers):
        r1 = make_basic_pattern(shippers[:2], plant)
        r2 = make_basic_pattern(shippers[2:4], plant)
        assert r1 != r2

    def test_order_of_shippers_does_not_affect_equality(self, plant, shippers):
        r1 = make_basic_pattern(shippers[:3], plant)
        r2 = make_basic_pattern(list(reversed(shippers[:3])), plant)
        assert r1 == r2

    def test_usable_as_dict_key(self, plant, shippers):
        r = make_basic_pattern(shippers[:2], plant)
        d = {r: "value"}
        assert d[r] == "value"

    def test_usable_in_set(self, plant, shippers):
        r1 = make_basic_pattern(shippers[:2], plant)
        r2 = make_basic_pattern(shippers[:2], plant)
        assert len({r1, r2}) == 1


class TestTransportConcept:
    def test_single_stop_is_ftl(self, plant, shippers):
        r = make_basic_pattern(shippers[:1], plant)
        assert r.transport_concept == "FTL"

    def test_multi_stop_is_milkrun(self, plant, shippers):
        for n in range(2, 5):
            r = make_basic_pattern(shippers[:n], plant)
            assert r.transport_concept == "MR"

    def test_ftl_overutilization_is_zero(self, plant, shippers):
        r = make_basic_pattern(shippers[:1], plant)
        assert r.overutilization == 1.0

    def test_mr_overutilization_is_five_percent(self, plant, shippers):
        r = make_basic_pattern(shippers[:2], plant)
        assert r.overutilization == 1.05


class TestAggregatedProperties:
    def test_weight_is_sum_of_shippers(self, plant, shippers):
        subset = shippers[:3]
        r = make_basic_pattern(subset, plant)
        assert r.weight == sum(s.total_weight for s in subset)

    def test_volume_is_sum_of_shippers(self, plant, shippers):
        subset = shippers[:3]
        r = make_basic_pattern(subset, plant)
        assert r.volume == sum(s.total_volume for s in subset)

    def test_loading_meters_is_sum_of_shippers(self, plant, shippers):
        subset = shippers[:3]
        r = make_basic_pattern(subset, plant)
        assert r.loading_meters == pytest.approx(sum(s.total_loading_meters for s in subset))

    def test_single_shipper_properties_match_shipper(self, plant):
        s = make_fake_shipper(total_weight=5_000, total_volume=42.0, total_loading_meters=7.2)
        r = make_basic_pattern([s], plant)
        assert r.weight == 5_000
        assert r.volume == pytest.approx(42.0)
        assert r.loading_meters == pytest.approx(7.2)


class TestShipperOrdering:
    def test_sequence_contains_all_shippers(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        assert set(r._sequence) == set(shippers[:3])

    def test_sequence_length_matches_stop_count(self, plant, shippers):
        for n in range(1, 5):
            r = make_ordered_pattern(shippers[:n], plant)
            assert len(r._sequence) == n

    def test_starting_point_is_farthest_from_plant(self, plant, shippers):
        """pick_starting_point selects the shipper farthest from the plant."""
        subset = shippers[:3]
        r = make_ordered_pattern(subset, plant)
        farthest = max(subset, key=lambda s: DISTANCE_FUNCTION(s.coordinates, plant.coordinates))
        assert r.starting_point == farthest

    def test_position_index_matches_sequence_order(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        for idx, shipper in enumerate(r._sequence):
            assert r._position[shipper] == idx

    def test_leg_distances_cover_all_shippers(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        assert set(r._leg_distance.keys()) == set(r._sequence)

    def test_leg_distances_are_positive(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        assert all(d > 0 for d in r._leg_distance.values())

    def test_single_stop_sequence_has_one_element(self, plant, shippers):
        r = make_ordered_pattern(shippers[:1], plant)
        assert len(r._sequence) == 1

    def test_ordering_is_deterministic(self, plant, shippers):
        """Calling order_shippers twice on equivalent patterns gives the same sequence."""
        r1 = make_ordered_pattern(shippers[:3], plant)
        r2 = make_ordered_pattern(shippers[:3], plant)
        assert r1._sequence == r2._sequence


class TestDeviationCalculation:
    def test_single_stop_deviation_is_zero(self, plant, shippers):
        r = make_ordered_pattern(shippers[:1], plant)
        r.calculate_deviation(DISTANCE_FUNCTION)
        assert r._deviation == 0

    def test_single_stop_deviation_bin_is_correct(self, plant, shippers):
        r = make_ordered_pattern(shippers[:1], plant)
        r.calculate_deviation(DISTANCE_FUNCTION)
        assert r.deviation_bin, r.mr_cluster == get_deviation_bin(0)

    def test_deviation_is_set_after_calculation(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        r.calculate_deviation(DISTANCE_FUNCTION)
        assert r._deviation is not None

    def test_deviation_bin_is_set_after_calculation(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        r.calculate_deviation(DISTANCE_FUNCTION)
        assert r.deviation_bin is not None

    def test_mr_cluster_is_set_after_calculation(self, plant, shippers):
        r = make_ordered_pattern(shippers[:3], plant)
        r.calculate_deviation(DISTANCE_FUNCTION)
        assert r.mr_cluster is not None

    def test_deviation_is_non_negative(self, plant, shippers):
        """Detour distance per stop should never be negative."""
        for n in range(2, 5):
            r = make_ordered_pattern(shippers[:n], plant)
            r.calculate_deviation(DISTANCE_FUNCTION)
            assert r._deviation >= 0

    def test_collinear_shippers_have_low_deviation(self, plant):
        """Shippers perfectly aligned toward plant incur minimal detour."""
        s1 = make_fake_shipper("A", (10, 0))
        s2 = make_fake_shipper("B", (20, 0))
        s3 = make_fake_shipper("C", (30, 0))
        r = make_ordered_pattern([s1, s2, s3], plant)
        r.calculate_deviation(DISTANCE_FUNCTION)
        assert r._deviation == pytest.approx(0, abs=1e-2)
