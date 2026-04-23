from ..domain_algorithms import get_ltl_weight_bracket, get_hub_weight_bracket, get_deviation_bin
from .route import Route
from ...settings import VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE


def _flow_endpoints(route: Route, digits: int) -> dict[str, str]:
    return {
        "origin_zip": route.commercial_origin.zip_key(digits),
        "origin_cofor": route.commercial_origin.cofor,
        "destination_zip": route.commercial_destination.zip_key(digits),
        "destination_cofor": route.commercial_destination.cofor,
    }


def _tariff_bundle(route, common):
    k2 = _flow_endpoints(route, 2)
    k3 = _flow_endpoints(route, 3)
    k5 = _flow_endpoints(route, 5)

    if route.demand.flow_direction == "parts":
        return [
            ("zip", common + (k2["origin_zip"], k2["destination_cofor"])),
            ("zip", common + (k3["origin_zip"], k3["destination_cofor"])),
            ("zip", common + (k5["origin_zip"], k5["destination_cofor"])),
            ("cofor", common + (k5["origin_cofor"], k5["destination_cofor"])),
        ]

    return [
        ("zip", common + (k2["origin_cofor"], k2["destination_zip"])),
        ("zip", common + (k3["origin_cofor"], k3["destination_zip"])),
        ("zip", common + (k5["origin_cofor"], k5["destination_zip"])),
        ("cofor", common + (k5["origin_cofor"], k5["destination_cofor"])),
    ]


class WeightBasedCosting:
    @staticmethod
    def chargeable_weight(route: Route) -> float:
        return max(
            route.demand.weight,
            route.demand.volume * VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE,
        )

    def weight_bracket_ltl(self, route: Route):
        return get_ltl_weight_bracket(self.chargeable_weight(route))

    def weight_bracket_hub(self, route: Route):
        return get_hub_weight_bracket(self.chargeable_weight(route))

    def build_tariff_bundle(self, route: Route) -> list[tuple[str, tuple]]:
        carrier_group = route.carrier.group

        # Linehaul routes: try both LTL and HUB weight brackets
        if route.__class__.__name__ == "LinehaulRoute":
            ltl_common = (
                carrier_group,
                self.weight_bracket_ltl(route),
            )
            hub_common = (
                carrier_group,
                self.weight_bracket_hub(route),
            )
            return _tariff_bundle(route, ltl_common) + _tariff_bundle(route, hub_common)

        # First-leg and everything else: normal LTL bracket only
        common = (
            carrier_group,
            self.weight_bracket_ltl(route),
        )
        return _tariff_bundle(route, common)

    def route_cost(self, route: Route) -> float:
        if route.tariff is None:
            return 0.0
        return route.tariff.price_for_weight(self.chargeable_weight(route))


class TruckBasedCosting:

    @staticmethod
    def build_tariff_bundle(route: Route) -> list[tuple[str, tuple]]:
        common = (
            route.carrier.group,
            route.vehicle.id,
            get_deviation_bin(route.demand.deviation)[0],
        )
        bundle = _tariff_bundle(route, common)

        if route.__class__.__name__ == "LinehaulRoute" and route.demand.hub.linehaul_transport_concept == "FTL":
            return [item for item in bundle if item[0] == "cofor"]

        return bundle

    @staticmethod
    def route_cost(route: Route) -> float:
        if route.tariff is None:
            return 0.0
        return route.tariff.price_for_stops(route.demand.count_of_stops, route.demand.deviation)

    @staticmethod
    def roundtrip_route_cost(route: Route) -> float:
        if route.tariff is None:
            return 0.0
        return route.tariff.roundtrip_price_for_stops(route.demand.count_of_stops, route.demand.deviation)
