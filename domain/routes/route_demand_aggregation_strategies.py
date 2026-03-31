from domain.data_structures import Plant, Carrier
from domain.routes.route_pattern import RoutePattern
from domain.shipper import Shipper


class HubAggregateDemand:
    def __init__(self, hub):
        self.hub = hub

    @property
    def weight(self):
        return sum(s.weight for s in self.hub.shippers)

    @property
    def volume(self):
        return sum(s.volume for s in self.hub.shippers)

    @property
    def loading_meters(self):
        return sum(s.loading_meters for s in self.hub.shippers)

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
    def count_of_stops(self):
        return self.pattern.count_of_stops

    @property
    def deviation(self):
        return self.pattern.deviation

    @property
    def overutilization(self):
        return self.pattern.overutilization


class ShipperDemand:
    def __init__(self, shipper: Shipper, plant: Plant, carrier: Carrier):
        self.shipper = shipper
        self._plant = plant
        self._carrier = carrier

    @property
    def weight(self):
        return self.shipper.weight

    @property
    def volume(self):
        return self.shipper.volume

    @property
    def loading_meters(self):
        return self.shipper.loading_meters

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

