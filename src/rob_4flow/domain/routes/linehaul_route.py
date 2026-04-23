from ..data_structures import Vehicle, Carrier
from .route import Route
from .route_costing_strategies import TruckBasedCosting, WeightBasedCosting
from .route_demand_aggregation_strategies import HubAggregateDemand
from ..tariff import FtlTariff, LtlTariff


class LinehaulRoute(Route):
    def __init__(self, hub, vehicle: Vehicle, carrier: Carrier, flow_direction: str):
        costing = (
            TruckBasedCosting()
            if hub.linehaul_transport_concept == "FTL"
            else WeightBasedCosting()
        )
        super().__init__(
            vehicle=vehicle,
            demand=HubAggregateDemand(hub, flow_direction=flow_direction),
            costing=costing,
        )
        self.tariff: FtlTariff | LtlTariff | None = None
        self.linehaul_carrier: Carrier = carrier

    def __hash__(self):
        return hash((self.demand.hub, self.demand.flow_direction))

    def __eq__(self, other):
        return ((isinstance(other, LinehaulRoute))
                and self.demand.hub == other.demand.hub
                and self.demand.flow_direction == other.demand.flow_direction
                )

    @property
    def carrier(self) -> Carrier:
        return self.linehaul_carrier

    @property
    def destination(self):
        return self.demand.plant

    def export_dataframe(self):
        pass
