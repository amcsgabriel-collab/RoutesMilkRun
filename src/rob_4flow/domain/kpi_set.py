from dataclasses import dataclass


@dataclass(frozen=True)
class KPISet:
    total_cost: float = 0.0
    trucks: float = 0.0
    utilization_numerator: float = 0.0
    weight: float = 0.0
    volume: float = 0.0
    loading_meters: float = 0.0

    @property
    def utilization(self) -> float:
        return (self.utilization_numerator / self.trucks) if self.trucks else 0.0

    @property
    def euro_per_truck(self) -> float:
        return self.total_cost / self.trucks if self.trucks else 0.0

    @property
    def volume_per_truck(self) -> float:
        return self.volume / self.trucks if self.trucks else 0.0

    def __add__(self, other: "KPISet") -> "KPISet":
        return KPISet(
            total_cost=self.total_cost + other.total_cost,
            trucks=self.trucks + other.trucks,
            weight=self.weight + other.weight,
            volume=self.volume + other.volume,
            loading_meters=self.loading_meters + other.loading_meters,
            utilization_numerator=self.utilization_numerator + other.utilization_numerator,
        )