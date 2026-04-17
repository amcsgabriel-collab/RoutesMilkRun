from domain.data_structures import Plant, Carrier
from domain.routes.route_pattern import RoutePattern
from domain.shipper import Shipper


class HubAggregateDemand:
    def __init__(self, hub, flow_direction):
        self.hub = hub
        self.flow_direction = flow_direction

    def _demand(self, shipper):
        return shipper.parts_demand if self.flow_direction == "parts" else shipper.empties_demand

    @property
    def weight(self):
        return sum(self._demand(s).weight for s in self.hub.shippers)

    @property
    def volume(self):
        return sum(self._demand(s).volume for s in self.hub.shippers)

    @property
    def loading_meters(self):
        return sum(self._demand(s).loading_meters for s in self.hub.shippers)

    @property
    def carrier(self):
        return None

    @property
    def plant(self):
        return self.hub.plant

    @property
    def starting_point(self):
        return self.hub

    @property
    def destination(self):
        return self.plant

    @property
    def deviation(self):
        return 35

    @property
    def count_of_stops(self):
        return 0

    @property
    def overutilization(self):
        return 1.0


class MilkrunPatternDemand:
    def __init__(self, pattern: RoutePattern):
        self.pattern = pattern
        self.flow_direction = pattern.flow_direction

    @property
    def weight(self):
        return self.pattern.weight

    @property
    def volume(self):
        return self.pattern.volume

    @property
    def loading_meters(self):
        return self.pattern.loading_meters

    @property
    def carrier(self):
        return self.starting_point.carrier

    @property
    def plant(self):
        return self.pattern.plant

    @property
    def starting_point(self):
        return self.pattern.starting_point

    @property
    def destination(self):
        return self.plant

    @property
    def count_of_stops(self):
        return self.pattern.count_of_stops

    @property
    def deviation(self):
        return self.pattern.deviation

    @property
    def overutilization(self):
        return self.pattern.overutilization


class ShipperDemand:
    def __init__(self, shipper: Shipper, plant: Plant, carrier: Carrier, flow_direction: str):
        self.shipper = shipper
        self._plant = plant
        self._carrier = carrier
        self.flow_direction = flow_direction

    @property
    def _demand(self):
        return self.shipper.parts_demand if self.flow_direction == "parts" else self.shipper.empties_demand

    @property
    def weight(self):
        return self._demand.weight

    @property
    def volume(self):
        return self._demand.volume

    @property
    def loading_meters(self):
        return self._demand.loading_meters

    @property
    def carrier(self):
        return self._carrier

    @property
    def plant(self):
        return self._plant

    @property
    def starting_point(self):
        return self.shipper

    @property
    def overutilization(self):
        return 1.0

