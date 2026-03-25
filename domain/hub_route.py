from domain.data_structures import Plant, Vehicle, Carrier
from domain.domain_algorithms import get_hub_weight_bracket, get_ltl_weight_bracket
from domain.shipper import Shipper
from settings import VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE


class HubRoute:
    def __init__(
            self,
            shipper: Shipper,
            plant: Plant,
            vehicle: Vehicle,
            carrier: Carrier,
            destination_hub_cofor: str
    ):
        self.shipper = shipper
        self.plant = plant
        self.vehicle = vehicle
        self.carrier = carrier
        self.destination_hub_cofor = destination_hub_cofor
        self.cost_per_100kg = 0
        self.max_price = 0
        self.min_price = 0
        self.tariff_source = None
        self.transport_concept = 'LTL'
        self.frequency = None

    def __hash__(self):
        return hash(self.shipper)

    def __eq__(self, other):
        return ((isinstance(other, HubRoute))
                and self.shipper == other.shipper)

    @property
    def total_cost(self):
        if not self.frequency:
            raise RuntimeError('Frequency not set')
        return max(min(self.chargeable_weight / 100 * self.cost_per_100kg, self.max_price), self.min_price) * self.frequency


    @property
    def chargeable_weight(self):
        return max(
            self.shipper.weight,
            self.shipper.volume * VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE
        )

    @property
    def weight_bracket_ltl(self):
        return get_ltl_weight_bracket(self.chargeable_weight)

    @property
    def weight_bracket_hub(self):
        return get_ltl_weight_bracket(self.chargeable_weight)

    def tariff_key_ltl(self, digits: int = 2):
        return (
            self.carrier.group,
            self.weight_bracket_ltl,
            self.destination_hub_cofor,
            self.shipper.zip_key(digits),
            self.shipper.cofor
        )

    def tariff_key_hub(self, digits: int = 2):
        return (
            self.carrier.group,
            self.weight_bracket_hub,
            self.destination_hub_cofor,
            self.shipper.zip_key(digits),
            self.shipper.cofor
        )

