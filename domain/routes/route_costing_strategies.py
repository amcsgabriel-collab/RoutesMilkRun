from domain.domain_algorithms import get_ltl_weight_bracket, get_hub_weight_bracket, get_deviation_bin
from domain.routes.route import Route
from settings import VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE


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

    def build_tariff_key(self, route: Route, digits: int = 2):
        origin = route.demand.starting_point
        return (
            route.demand.carrier.group,
            self.weight_bracket_ltl(route),
            route.demand.plant.cofor,
            origin.zip_key(digits),
            origin.cofor,
        )

    def route_cost(self, route: Route) -> float:
        if route.tariff is None:
            return 0.0
        return route.tariff.price_for_weight(self.chargeable_weight(route))


class TruckBasedCosting:
    @staticmethod
    def build_tariff_key(route: Route, digits: int = 2):
        origin = route.demand.starting_point
        return (
            route.demand.carrier,
            route.vehicle.id,
            get_deviation_bin(route.demand.deviation)[0],
            origin.zip_key(digits),
            origin.cofor,
        )

    @staticmethod
    def route_cost(route: Route) -> float:
        if route.tariff is None:
            return 0.0
        return route.tariff.price_for_stop(route.demand.count_of_stops, route.demand.deviation)

