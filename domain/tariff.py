from dataclasses import dataclass


@dataclass(frozen=True)
class FtlTariff:
    base_cost: float
    stop_cost: float

    def price_for_stops(self, count_of_stops: int, deviation_km: int) -> float:
        if deviation_km > 150:
            return self.base_cost + self.stop_cost * deviation_km * count_of_stops
        else:
            return self.base_cost + self.stop_cost * count_of_stops


@dataclass(frozen=True)
class LtlTariff:
    cost_per_100kg: float
    min_price: float
    max_price: float

    def price_for_weight(self, chargeable_weight: float) -> float:
        raw_price = chargeable_weight / 100 * self.cost_per_100kg
        return max(min(raw_price, self.max_price), self.min_price)


@dataclass(frozen=True)
class HubTariff(LtlTariff):
    pass
