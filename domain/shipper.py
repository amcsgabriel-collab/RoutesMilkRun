import copy

from domain.general_algorithms import decimal_to_dms_str
from domain.data_structures import Carrier, Seller

MIN_TRUCK_CAPACITIES = {'Weight Capacity': 24000, 'Load Meter Capacity': 13.6, 'Volume Capacity': 92.75}
MAX_FREQUENCY=5

class Shipper:
    def __init__(
            self,
            cofor: str,
            sellers: set[Seller],
            name: str,
            zip_code: str,
            city: str,
            street: str,
            country: str,
            sourcing_region: str,
            volume: float,
            weight: float,
            loading_meters: float,
            carrier: Carrier,
            original_network: str = None,
            coordinates: tuple[float, float] | None = None,
    ):
        self.cofor = cofor
        self.sellers = sellers
        self.name = name
        self.original_network = original_network
        self.zip_code = zip_code
        self.city = city
        self.street = street
        self.country = country
        self.sourcing_region = sourcing_region
        self.volume = volume
        self.weight = weight
        self.loading_meters = loading_meters
        self.carrier = carrier
        self.coordinates = coordinates
        self.is_ftl_exclusive_shipper = self.verify_ftl_exclusive_shipper()


    def __eq__(self, other):
        return isinstance(other, Shipper) and self.cofor == other.cofor

    def __hash__(self):
        return hash(self.cofor)

    def copy(self):
        return copy.deepcopy(self)

    @property
    def formatted_coordinates(self):
        return decimal_to_dms_str(self.coordinates)

    @property
    def has_demand(self):
        return (self.volume > 0) or (self.weight > 0) or (self.loading_meters > 0)

    def zip_key(self, digits):
        return self.country + self.zip_code[:digits]

    def verify_ftl_exclusive_shipper(self):
        """
            Returns True if the shipper's demand exceeds the maximum theoretical
            capacity of frequency (MAX_TRUCKS) of the smallest available vehicle type,
            where milkruns would be inviable regardless of route combination.
            """
        return ((self.weight > MIN_TRUCK_CAPACITIES["Weight Capacity"] * MAX_FREQUENCY)
                or (self.volume > MIN_TRUCK_CAPACITIES["Volume Capacity"] * MAX_FREQUENCY)
                or (self.loading_meters > MIN_TRUCK_CAPACITIES["Load Meter Capacity"] * MAX_FREQUENCY))

    def qualifies_for_hub(self, thresholds):
        if thresholds["weight"] is not None:
            if self.weight >= thresholds["weight"]:
                return False
        if thresholds["volume"] is not None:
            if self.volume >= thresholds["volume"]:
                return False
        if thresholds["loading_meters"] is not None:
            if self.loading_meters >= thresholds["loading_meters"]:
                return False
        return True

    @property
    def summary(self):
        return {
            "name": self.name,
            "cofor": self.cofor,
            "total_weight": self.weight,
            "total_volume": self.volume,
            "total_loading_meters": self.loading_meters,
            "coordinates": self.coordinates,
            "original_network": self.original_network,
        }