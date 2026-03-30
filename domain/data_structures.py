from dataclasses import dataclass

from domain.general_algorithms import decimal_to_dms_str


@dataclass(frozen=True)
class Plant:
    cofor: str
    name: str
    # zip: str
    coordinates: tuple[float, float]

    @property
    def formatted_coordinates(self):
        return decimal_to_dms_str(self.coordinates)


@dataclass(frozen=True)
class Carrier:
    cofor: str
    id: str
    name: str
    group: str

    def to_dict(self) -> dict:
        return {
            "Carrier COFOR": self.cofor,
            "Carrier ID": self.id,
            "Carrier name": self.name,
            "Carrier Group": self.group,
        }


@dataclass(frozen=True)
class Seller:
    cofor: str
    name: str
    zip: str
    city: str
    country: str

    def to_dict(self):
        return {
            "Seller COFOR": self.cofor,
            "SELLER NAME": self.name,
            "SELLER ZIP CODE": self.zip,
            "SELLER CITY": self.city,
            "SELLER COUNTRY": self.country,
        }


@dataclass(frozen=True)
class Vehicle:
    id:str
    weight_capacity:float
    volume_capacity:float
    loading_meters_capacity:float

    def summary(self) -> dict:
        return {
            "id": self.id,
            "weight": self.weight_capacity,
            "volume": self.volume_capacity,
            "loading_meters": self.loading_meters_capacity,
        }
