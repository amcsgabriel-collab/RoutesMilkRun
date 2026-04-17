import copy

from domain.demand import Demand
from domain.general_algorithms import decimal_to_dms_str
from domain.data_structures import Carrier

MIN_TRUCK_CAPACITIES = {'Weight Capacity': 24000, 'Load Meter Capacity': 13.6, 'Volume Capacity': 92.75}
MAX_FREQUENCY=5

class Shipper:
    def __init__(
            self,
            cofor: str,
            name: str,
            zip_code: str,
            city: str,
            street: str,
            country: str,
            sourcing_region: str,
            parts_demand: Demand,
            empties_demand: Demand,
            carrier: Carrier,
            original_network: str = None,
            coordinates: tuple[float, float] | None = None,
    ):
        self.cofor = cofor
        self.name = name
        self.original_network = original_network
        self.zip_code = zip_code
        self.city = city
        self.street = street
        self.country = country
        self.sourcing_region = sourcing_region
        self.parts_demand = parts_demand
        self.empties_demand = empties_demand
        self.carrier = carrier
        self.coordinates = coordinates


    def __eq__(self, other):
        return isinstance(other, Shipper) and self.cofor == other.cofor

    def __hash__(self):
        return hash(self.cofor)

    def copy(self):
        return copy.deepcopy(self)

    def zip_key(self, digits):
        return self.country + self.zip_code[:digits]

    @property
    def formatted_coordinates(self):
        return decimal_to_dms_str(self.coordinates)

    @property
    def has_parts_demand(self):
        return self.parts_demand is not None and self.parts_demand.is_not_zero

    @property
    def has_empties_demand(self):
        return self.empties_demand is not None and self.empties_demand.is_not_zero

    @property
    def is_ftl_exclusive_parts(self):
        return self.verify_ftl_exclusive(self.parts_demand)

    @property
    def is_ftl_exclusive_empties(self):
        return self.verify_ftl_exclusive(self.empties_demand)

    @staticmethod
    def verify_ftl_exclusive(demand):
        """
            Returns True if the shipper's demand exceeds the maximum theoretical
            capacity of frequency (MAX_TRUCKS) of the smallest available vehicle type,
            where milkruns would be inviable regardless of route combination.
            """
        return ((demand.weight > MIN_TRUCK_CAPACITIES["Weight Capacity"] * MAX_FREQUENCY)
                or (demand.volume > MIN_TRUCK_CAPACITIES["Volume Capacity"] * MAX_FREQUENCY)
                or (demand.loading_meters > MIN_TRUCK_CAPACITIES["Load Meter Capacity"] * MAX_FREQUENCY))

    def qualifies_for_hub(self, thresholds):
        if thresholds["weight"] is not None:
            if self.parts_demand.weight >= thresholds["weight"]:
                return False
        if thresholds["volume"] is not None:
            if self.parts_demand.volume >= thresholds["volume"]:
                return False
        if thresholds["loading_meters"] is not None:
            if self.parts_demand.loading_meters >= thresholds["loading_meters"]:
                return False
        return True

    @property
    def summary(self):
        return {
            "name": self.name,
            "cofor": self.cofor,
            "zip_key": self.zip_key(2),
            "coordinates": self.formatted_coordinates,
            "original_network": self.original_network,
            "parts_demand": {
                "weight": self.parts_demand.weight,
                "volume": self.parts_demand.volume,
                "loading_meters": self.parts_demand.loading_meters,
            },
            "empties_demand": {
                "weight": self.empties_demand.weight,
                "volume": self.empties_demand.volume,
                "loading_meters": self.empties_demand.loading_meters,
            },
        }