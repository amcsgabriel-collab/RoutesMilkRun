from domain.data_structures import Vehicle, Carrier
from domain.routes.route import Route
from domain.routes.route_costing_strategies import TruckBasedCosting, WeightBasedCosting
from domain.routes.route_demand_aggregation_strategies import HubAggregateDemand
from domain.tariff import FtlTariff, LtlTariff


class LinehaulRoute(Route):
    def __init__(self, hub, vehicle: Vehicle, carrier: Carrier):
        costing = (
            TruckBasedCosting()
            if hub.linehaul_transport_concept == "FTL"
            else WeightBasedCosting()
        )
        super().__init__(
            vehicle=vehicle,
            demand=HubAggregateDemand(hub),
            costing=costing,

        )
        self.tariff: FtlTariff | LtlTariff | None = None
        self.linehaul_carrier: Carrier = carrier

    def __hash__(self):
        return hash(self.demand.hub)

    def __eq__(self, other):
        return ((isinstance(other, LinehaulRoute))
                and self.demand.hub == other.demand.hub)

    @property
    def carrier(self) -> Carrier:
        return self.linehaul_carrier

    @property
    def destination(self):
        return self.demand.plant.cofor
