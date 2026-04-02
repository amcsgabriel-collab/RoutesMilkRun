from dataclasses import dataclass
from typing import Literal

from domain.data_structures import Seller


@dataclass
class Demand:
    weight: float
    volume: float
    loading_meters: float
    sellers: list[Seller]
    type: Literal["P", "E"]
    original_network: Literal["hub", "direct"]
