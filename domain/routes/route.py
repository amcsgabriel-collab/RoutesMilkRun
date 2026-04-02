import copy
from abc import abstractmethod, ABCMeta
from math import ceil

from domain.data_structures import Vehicle, Carrier


def _safe_div(numerator, denominator):
    if denominator is None or denominator == 0:
        return 0.0
    return numerator / denominator


class Route(metaclass=ABCMeta):
    METRICS = (
        ("weight", "weight_capacity"),
        ("volume", "volume_capacity"),
        ("loading_meters", "loading_meters_capacity"),
    )

    def __init__(self, vehicle: Vehicle, demand, costing):
        super.__init__(self)
        self.vehicle = vehicle
        self.demand = demand
        self.costing = costing
        self.tariff = None
        self.tariff_source = None

    def copy(self):
        return copy.deepcopy(self)

    def _ratio(self, demand_attr: str, capacity_attr: str, *, use_frequency: bool = False) -> float:
        demand_value = getattr(self.demand, demand_attr)
        capacity_value = getattr(self.vehicle, capacity_attr)

        denominator = capacity_value
        if use_frequency:
            denominator *= self.frequency
        else:
            denominator *= self.demand.overutilization

        return _safe_div(demand_value, denominator)

    @property
    def frequency(self) -> int:
        max_ratio = max(
            self._ratio(demand_attr, capacity_attr)
            for demand_attr, capacity_attr in self.METRICS
        )
        return ceil(max_ratio) if max_ratio > 0 else 0

    def utilization(self, metric: str) -> float:
        capacity_attr = f"{metric}_capacity"
        return round(
            self._ratio(metric, capacity_attr, use_frequency=True),
            4,
        ) * 100 if self.frequency else 0.0

    @property
    def carrier(self) -> Carrier:
        return self.demand.carrier

    @property
    def starting_point(self):
        return self.demand.starting_point

    @abstractmethod
    @property
    def destination(self):
        pass

    @property
    def commercial_origin(self):
        return self.starting_point if self.demand.flow_type == "parts" else self.destination

    @property
    def commercial_destination(self):
        return self.destination if self.demand.flow_type == "parts" else self.starting_point

    @property
    def weight(self):
        return self.demand.weight

    @property
    def volume(self):
        return self.demand.volume

    @property
    def loading_meters(self):
        return self.demand.loading_meters

    @property
    def weight_utilization(self) -> float:
        return self.utilization("weight")

    @property
    def volume_utilization(self) -> float:
        return self.utilization("volume")

    @property
    def loading_meters_utilization(self) -> float:
        return self.utilization("loading_meters")

    @property
    def max_utilization(self) -> float:
        return max(
            self.weight_utilization,
            self.volume_utilization,
            self.loading_meters_utilization,
        )

    @property
    def tariff_key_bundle(self):
        full_key = self.costing.build_tariff_key(self)
        if self.demand.flow_type == "parts":
            return [
                ("zip", self.costing.build_tariff_key(self, 2)[:4]), # By zip + country, 2 digits only
                ("zip", self.costing.build_tariff_key(self, 3)[:4]), # By zip + country, 3 digits
                ("zip", self.costing.build_tariff_key(self, 5)[:4]), # By zip + country, all 5 digits
                ("cofor", full_key[:3] + (full_key[4],)), # Finally, by COFOR.
            ]
        return [
            ("zip", self.costing.build_tariff_key(self, 2)[:4]), # By zip + country, 2 digits only
            ("zip", self.costing.build_tariff_key(self, 3)[:4]), # By zip + country, 3 digits
            ("zip", self.costing.build_tariff_key(self, 5)[:4]), # By zip + country, all 5 digits
            ("cofor", full_key[:3] + (full_key[4],)), # Finally, by COFOR.
        ]

    @property
    def route_cost(self):
        return self.costing.route_cost(self)

    @property
    def total_cost(self):
        return self.route_cost * self.frequency

    @abstractmethod
    def export_dataframe(self, *args, **kwargs):
        pass


