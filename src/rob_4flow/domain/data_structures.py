from dataclasses import dataclass

from .general_algorithms import decimal_to_dms_str


@dataclass(frozen=True)
class Plant:
    cofor: str
    name: str
    coordinates: tuple[float, float]
    country: str | None = None
    zip_code: str | None = None

    @property
    def formatted_coordinates(self):
        return decimal_to_dms_str(self.coordinates)

    def zip_key(self, digits):
        if not self.country or not self.zip_code:
            return None
        return self.country + self.zip_code[:digits]


@dataclass(frozen=True)
class Carrier:
    cofor: str
    id: str
    name: str
    group: str


@dataclass(frozen=True)
class Seller:
    cofor: str
    name: str
    zip: str
    city: str
    country: str
    docks: str


@dataclass(frozen=True)
class Vehicle:
    id:str
    weight_capacity:float
    volume_capacity:float
    loading_meters_capacity:float

    @property
    def summary(self) -> dict:
        return {
            "id": self.id,
            "weight": self.weight_capacity,
            "volume": self.volume_capacity,
            "loading_meters": self.loading_meters_capacity,
        }
