from dataclasses import dataclass
from typing import Literal

from .data_structures import Seller


@dataclass
class Demand:
    weight: float
    volume: float
    loading_meters: float
    sellers: list[Seller]
    type: Literal["P", "E"]
    original_network: Literal["hub", "direct"]

    @property
    def is_not_zero(self):
        return (self.weight != 0
                and self.volume != 0
                and self.loading_meters != 0)
