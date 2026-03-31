from domain.data_structures import Vehicle, Carrier
from domain.routes.route import Route
from domain.routes.route_costing_strategies import WeightBasedCosting
from domain.routes.route_demand_aggregation_strategies import ShipperDemand
from domain.shipper import Shipper
from domain.tariff import LtlTariff, HubTariff

def get_frequency_bracket(chargeable_weight):
    if chargeable_weight is None:
        raise ValueError("Chargeable weight cannot be None")
    if chargeable_weight < 0:
        raise ValueError("Chargeable weight cannot be negative")
    if chargeable_weight <= 1000:
        return 1
    if chargeable_weight <= 2000:
        return 2
    if chargeable_weight <= 5000:
        return 3
    else:
        return 4

class FirstLegRoute(Route):
    def __init__(self, hub, shipper: Shipper, vehicle: Vehicle, carrier: Carrier):
        super().__init__(
            vehicle=vehicle,
            demand=ShipperDemand(
                shipper=shipper,
                plant=hub.plant,
                carrier=carrier
            ),
            costing=WeightBasedCosting(),
        )
        self.hub = hub
        self.shipper = shipper
        self.tariff: LtlTariff | HubTariff | None  = None
        self.transport_concept = "LTL"

    def __hash__(self):
        return hash(self.demand.shipper)

    def __eq__(self, other):
        return ((isinstance(other, FirstLegRoute))
                and self.demand.shipper == other.demand.shipper)

    @property
    def frequency(self):
        """
        Frequency of the first leg increases with specified weight thresholds, up to the linehaul frequency.
        """
        return min(
            get_frequency_bracket(self.costing.chargeable_weight(self)),
            self.hub.linehaul_route.frequency
        )

    @property
    def destination(self):
        return self.hub.cofor
