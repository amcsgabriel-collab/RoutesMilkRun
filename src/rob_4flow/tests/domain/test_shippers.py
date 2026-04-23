import pytest

from domain.shipper import MIN_TRUCK_CAPACITIES, MAX_FREQUENCY
from tests.factories import make_shipper, make_carrier, make_seller


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def shipper():
    return make_shipper()


@pytest.fixture
def carrier():
    return make_carrier()


class TestZipKey:
    def test_zip_key_uses_first_two_digits(self):
        s = make_shipper(country="FR", zip_code="98765")
        assert s.zip_key == "FR98"

    def test_zip_key_different_countries(self):
        for country in ["FR", "DE", "ES", "IT"]:
            s = make_shipper(country=country, zip_code="99999")
            assert s.zip_key.startswith(country)


class TestIdentity:
    def test_same_cofor_are_equal(self):
        s1 = make_shipper(cofor="A", country="DE", zip_code="123")
        s2 = make_shipper(cofor="A", country="FR", zip_code="999")
        assert s1 == s2

    def test_different_cofor_are_not_equal(self):
        s1 = make_shipper(cofor="A")
        s2 = make_shipper(cofor="B")
        assert s1 != s2

    def test_same_cofor_have_same_hash(self):
        s1 = make_shipper(cofor="A")
        s2 = make_shipper(cofor="A")
        assert hash(s1) == hash(s2)

    def test_unique_in_set(self):
        s1 = make_shipper(cofor="A")
        s2 = make_shipper(cofor="A")
        s3 = make_shipper(cofor="B")
        assert len({s1, s2, s3}) == 2

    def test_usable_as_dict_key(self):
        s = make_shipper(cofor="A")
        d = {s: "value"}
        assert d[s] == "value"


class TestAggregatedProperties:
    def test_total_weight_is_sum_of_sellers(self):
        sellers = [make_seller(weight=1_000), make_seller(weight=2_000)]
        s = make_shipper(sellers=sellers)
        assert s.total_weight == 3_000

    def test_total_volume_is_sum_of_sellers(self):
        sellers = [make_seller(volume=10), make_seller(volume=20)]
        s = make_shipper(sellers=sellers)
        assert s.total_volume == 30

    def test_total_loading_meters_is_sum_of_sellers(self):
        sellers = [make_seller(loading_meters=3.4), make_seller(loading_meters=6.8)]
        s = make_shipper(sellers=sellers)
        assert s.total_loading_meters == pytest.approx(10.2)

    def test_empty_sellers_gives_zero_totals(self):
        s = make_shipper(sellers=[])
        assert s.total_weight == 0
        assert s.total_volume == 0
        assert s.total_loading_meters == 0


class TestToDict:
    def test_cofor_exported_correctly(self):
        s = make_shipper(cofor="S1")
        assert s.to_dict()["Shipper COFOR"] == "S1"

    def test_aggregated_values_exported(self):
        sellers = [make_seller(weight=500, volume=5, loading_meters=1.0)]
        s = make_shipper(sellers=sellers)
        d = s.to_dict()
        assert d["Weight"] == 500
        assert d["Volume"] == 5
        assert d["Load Meter"] == 1.0

    def test_carrier_fields_exported_when_present(self):
        c = make_carrier(id="C1", name="DHL")
        s = make_shipper(carrier=c)
        d = s.to_dict()
        assert d["Carrier ID"] == "C1"
        assert d["Carrier Name"] == "DHL"

    def test_carrier_fields_are_none_when_absent(self):
        s = make_shipper(carrier=None)
        d = s.to_dict()
        assert d["Carrier ID"] is None
        assert d["Carrier Name"] is None

    def test_all_expected_keys_present(self):
        s = make_shipper()
        expected_keys = {"Shipper COFOR", "Weight", "Volume", "Load Meter",
                         "Zip", "Country", "Sourcing Region", "Carrier ID", "Carrier Name"}
        assert expected_keys.issubset(s.to_dict().keys())


class TestHubEligibility:

    def _make_shipper_with_demand(self, weight, volume, loading_meters):
        return make_shipper(sellers=[make_seller(weight, volume, loading_meters)])

    @pytest.mark.parametrize("weight,volume,lm,thresholds,expected,case", [
        # All dimensions below threshold → qualifies
        (70, 10, 15, {"weight": 80, "volume": 20, "loading_meters": 20}, True, "All below thresholds"),
        # Exceeds weight → disqualified
        (100, 10, 10, {"weight": 80, "volume": 20, "loading_meters": 20}, False, "Above weight threshold"),
        # Exceeds volume → disqualified
        (70, 25, 10, {"weight": 80, "volume": 20, "loading_meters": 20}, False, "Above volume threshold"),
        # Exceeds loading meters → disqualified
        (70, 10, 25, {"weight": 80, "volume": 20, "loading_meters": 20}, False, "Above loading meters threshold"),
        # Exactly equal to threshold → disqualified (>= boundary)
        (80, 10, 10, {"weight": 80, "volume": None, "loading_meters": None}, False, "Equal to weight threshold"),
        # All thresholds None → always qualifies
        (70, 10, 25, {"weight": None, "volume": None, "loading_meters": None}, True, "All None thresholds"),
        # Single weight threshold only
        (100, 10, 10, {"weight": 110, "volume": None, "loading_meters": None}, True, "Single weight threshold, below"),
        # Single volume threshold only
        (100, 10, 10, {"weight": None, "volume": 20, "loading_meters": None}, True, "Single volume threshold, below"),
        # Single loading meters threshold only
        (100, 10, 10, {"weight": None, "volume": None, "loading_meters": 20}, True,
         "Single loading meters threshold, below"),
    ])
    def test_hub_eligibility(self, weight, volume, lm, thresholds, expected, case):
        s = self._make_shipper_with_demand(weight, volume, lm)
        assert s.qualifies_for_hub(thresholds) is expected, f"Failed: {case}"


class TestFtlExclusivity:
    """
    FTL exclusive = demand exceeds MAX_FREQUENCY * smallest vehicle capacity
    on at least one dimension, making milkrun infeasible.
    """

    def test_below_all_thresholds_is_not_exclusive(self):
        s = make_shipper(sellers=[make_seller(weight=1_000, volume=10, loading_meters=1.5)])
        assert s.is_ftl_exclusive_shipper is False

    def test_exceeds_weight_threshold_is_exclusive(self):
        excessive_weight = MIN_TRUCK_CAPACITIES["Weight Capacity"] * MAX_FREQUENCY + 1
        s = make_shipper(sellers=[make_seller(weight=excessive_weight)])
        assert s.is_ftl_exclusive_shipper is True

    def test_exceeds_volume_threshold_is_exclusive(self):
        excessive_volume = MIN_TRUCK_CAPACITIES["Volume Capacity"] * MAX_FREQUENCY + 1
        s = make_shipper(sellers=[make_seller(volume=excessive_volume)])
        assert s.is_ftl_exclusive_shipper is True

    def test_exceeds_loading_meters_threshold_is_exclusive(self):
        excessive_lm = MIN_TRUCK_CAPACITIES["Load Meter Capacity"] * MAX_FREQUENCY + 1
        s = make_shipper(sellers=[make_seller(loading_meters=excessive_lm)])
        assert s.is_ftl_exclusive_shipper is True

    def test_exactly_at_threshold_is_not_exclusive(self):
        """Boundary: exactly at the limit should not be exclusive (uses >)."""
        exact_weight = MIN_TRUCK_CAPACITIES["Weight Capacity"] * MAX_FREQUENCY
        s = make_shipper(sellers=[make_seller(weight=exact_weight)])
        assert s.is_ftl_exclusive_shipper is False
