from math import ceil

import pandas as pd

from domain.domain_algorithms import get_deviation_bin, get_ltl_weight_bracket
from domain.exceptions import VehicleCapacityError
from domain.general_algorithms import decimal_to_dms_str
from domain.data_structures import Carrier, Vehicle, Plant
from domain.hub_route import HubRoute
from domain.shipper import Shipper
from settings import VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE


def _safe_div(numerator, denominator):
    if denominator is None or denominator == 0:
        return 0.0
    return numerator / denominator

def get_frequency_bracket(chargeable_weight):
    if chargeable_weight is None:
        raise ValueError("Chargeable weight cannot be None")
    if chargeable_weight < 0:
        raise ValueError("Chargeable weight cannot be negative")
    if chargeable_weight <= 1000:
        return 1
    if chargeable_weight <= 2000:
        return 2
    if chargeable_weight <= 5000:
        return 3
    else:
        return 4

class Hub:
    first_leg_routes: set[HubRoute]
    def __init__(
            self,
            route: str,
            cofor: str,
            name: str,
            country: str,
            zip_code: str,
            plant: Plant,
            shippers: list[Shipper],
            first_leg_carrier: Carrier,
            first_leg_vehicle: Vehicle,
            linehaul_carrier: Carrier,
            linehaul_vehicle: Vehicle,
            linehaul_transport_concept,
            coordinates: tuple[float, float],
    ):
        self.route = route
        self.cofor = cofor
        self.name = name
        self.country = country
        self.zip_code = str(zip_code)
        self.plant = plant
        self.shippers = shippers
        self.first_leg_carrier = first_leg_carrier
        self.first_leg_vehicle = first_leg_vehicle
        self.first_leg_routes = set()
        self.linehaul_carrier = linehaul_carrier
        self.linehaul_vehicle = linehaul_vehicle
        self.linehaul_transport_concept = linehaul_transport_concept
        self.linehaul_base_cost = 0
        self.linehaul_cost_per_100kg = 0
        self.linehaul_min_price = 0
        self.linehaul_max_price = 0
        self.linehaul_tariff_source = None
        self.coordinates = coordinates
        self.refresh_first_leg_routes()
        self.set_first_leg_routes_frequency()

    @property
    def formatted_coordinates(self):
        return decimal_to_dms_str(self.coordinates)

    @property
    def first_leg_cost(self):
        return sum(route.total_cost for route in self.first_leg_routes)

    @property
    def total_cost(self):
        return self.linehaul_cost + self.first_leg_cost

    @property
    def pre_carriage_costs(self):
        return sum(r.total_cost for r in self.first_leg_routes)

    @property
    def total_pre_carriage_costs(self):
        return sum(r.total_cost for r in self.first_leg_routes)

    @property
    def linehaul_volume(self):
        return sum(s.shipper.volume for s in self.first_leg_routes)

    @property
    def linehaul_weight(self):
        return sum(s.shipper.weight for s in self.first_leg_routes)

    @property
    def linehaul_loading_meters(self):
        return sum(s.shipper.loading_meters for s in self.first_leg_routes)

    @property
    def linehaul_weight_utilization(self):
        return round(
            _safe_div(self.linehaul_weight,
                      self.linehaul_vehicle.weight_capacity * self.linehaul_frequency),
            4
        )

    @property
    def linehaul_volume_utilization(self):
        return round(
            _safe_div(self.linehaul_volume,
                      self.linehaul_vehicle.volume_capacity * self.linehaul_frequency),
            4
        )

    @property
    def linehaul_loading_meters_utilization(self):
        return round(
            _safe_div(self.linehaul_loading_meters,
                      self.linehaul_vehicle.loading_meters_capacity * self.linehaul_frequency),
            4
        )

    @property
    def linehaul_utilization(self):
        return max(
            self.linehaul_volume_utilization,
            self.linehaul_weight_utilization,
            self.linehaul_loading_meters_utilization,
        )

    @property
    def linehaul_frequency(self):
        ratios = [
            _safe_div(self.linehaul_weight,
                      self.linehaul_vehicle.weight_capacity),

            _safe_div(self.linehaul_volume,
                      self.linehaul_vehicle.volume_capacity),

            _safe_div(self.linehaul_loading_meters,
                      self.linehaul_vehicle.loading_meters_capacity),
        ]

        max_ratio = max(ratios)
        return ceil(max_ratio)

    @property
    def linehaul_cost(self):
        if self.linehaul_transport_concept in ['FTL', 'MR']:
            return self.linehaul_frequency * self.linehaul_base_cost
        else:
            return max(min(self.linehaul_chargeable_weight / 100 * self.linehaul_cost_per_100kg, self.linehaul_max_price), self.linehaul_min_price) * self.linehaul_frequency

    @property
    def linehaul_chargeable_weight(self):
        return max(
            self.linehaul_weight,
            self.linehaul_volume * VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE
        )

    @property
    def weight_bracket_ltl(self):
        return get_ltl_weight_bracket(self.linehaul_chargeable_weight)

    @property
    def summary(self):
        return {
            "name": self.name,
            "cofor": self.cofor,
            "first_leg_cost": self.first_leg_cost,
            "linehaul_frequency": self.linehaul_frequency,
            "linehaul_cost": self.linehaul_cost,
            "linehaul_weight": self.linehaul_weight,
            "linehaul_volume": self.linehaul_volume,
            "linehaul_loading_meters": self.linehaul_loading_meters,
            "linehaul_weight_utilization": self.linehaul_weight,
            "linehaul_volume_utilization": self.linehaul_volume,
            "linehaul_loading_meters_utilization": self.linehaul_loading_meters,
            "coordinates": self.coordinates,
        }

    @property
    def short_summary(self):
        return {
            "name": self.name,
            "cofor": self.cofor,
        }

    def zip_key(self, digits: int = 2):
        print(self.zip_code)
        return self.country + self.zip_code[:digits]

    def tariff_key_ftl(self, digits: int = 2):
        return (
            self.linehaul_carrier.group,
            self.linehaul_vehicle.id,
            get_deviation_bin(35)[0],
            self.zip_key(digits),
            self.cofor
        )

    def tariff_key_ltl(self, digits: int = 2):
        return (
            self.linehaul_carrier.group,
            self.weight_bracket_ltl,
            self.plant.cofor,
            self.zip_key(digits),
            self.cofor
        )

    def verify_vehicle_capacity(self) -> None:
        if (self.linehaul_vehicle.weight_capacity <= 0
                or self.linehaul_vehicle.volume_capacity <= 0
                or self.linehaul_vehicle.loading_meters_capacity <= 0
        ):
            raise VehicleCapacityError(f'Vehicle has negative capacity: {self.linehaul_vehicle.id}')

    @staticmethod
    def _safe_capacity_ratio(demand, capacity):
        if capacity == 0:
            return 0.0
        return demand / capacity

    def refresh_first_leg_routes(self):
        self.first_leg_routes = {
            HubRoute(shipper=shipper,
                carrier=self.first_leg_carrier,
                vehicle=self.first_leg_vehicle,
                plant=self.plant,
                destination_hub_cofor=self.cofor
                ) for shipper in self.shippers
        }

    def set_first_leg_routes_frequency(self):
        for route in self.first_leg_routes:
            route.frequency = min(get_frequency_bracket(route.chargeable_weight), self.linehaul_frequency)

    def generate_route_name(self):
        return f"GD_{self.name} #PS"

    def to_dataframe(self):
        rows = []

        routes = sorted(
            self.first_leg_routes,
            key=lambda r: ((r.shipper.name or "").lower(), (r.shipper.cofor or "").lower())
        )

        first_hub_row = True

        for route in routes:
            shipper = route.shipper
            sellers = sorted(
                shipper.sellers,
                key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
            )

            first_shipper_row = True

            for seller in sellers:
                route_row = {
                    'Route name': self.generate_route_name(),
                    'HUB Name': self.name,
                    'Shipper COFOR': shipper.cofor,
                    'Seller COFOR': seller.cofor,
                    'Hybrid COFOR': seller.cofor,
                    'Plant COFOR': self.plant.cofor,
                    'Parts or Empties': 'P',
                    'Docks (,)': '',
                    'First pickup': '',
                    'Total transit time (days)': '',
                    'First delivery': '',
                    'Carrier COFOR': shipper.carrier.cofor,
                    'Carrier ID': shipper.carrier.id,
                    'Carrier name': shipper.carrier.name,
                    'Means of Transport': route.vehicle.id,
                    # 'Transport Concept': self.transport_concept,
                    'Transport Concept': 'todo',
                    'SELLER NAME': seller.name,
                    'SELLER ZIP CODE': seller.zip,
                    'SELLER CITY': seller.city,
                    'SELLER COUNTRY': seller.country,
                    'SHIPPER NAME': shipper.name,
                    'SHIPPER  ZIP CODE': shipper.zip_code,
                    'SHIPPER CITY': shipper.city,
                    'SHIPPER STREET': shipper.street,
                    'SHIPPER COUNTRY': shipper.country,
                    'SHIPPER SOURCING REGION': shipper.sourcing_region,
                    'HEV: empties truck loading begins at Stellantis Plant': '',
                    'HEE: empties truck leaving plant site at Stellantis Plant': '',
                    'HMD: parts truck arrival at shipper location': '',
                    'HEF: parts truck leaving shipper location': '',
                    'Pick Mon': '',
                    'Pick Tue': '',
                    'Pick Wed': '',
                    'Pick Thu': '',
                    'Pick Fri': '',
                    'Pick Sat': '',
                    'Pick Sun': '',
                    'Frequency / week': route.frequency,
                    'DEL Mon': '',
                    'DEL Tue': '',
                    'DEL Wed': '',
                    'DEL Thu': '',
                    'DEL Fri': '',
                    'DEL Sat': '',
                    'DEL Sun': '',
                    'HAS: parts truck arrival at Stellantis plant': '',
                    'Parts truck unloading starts in last dock at Stellantis Plant': '',
                    'HDE: Empties truck arrival at supplier': '',
                    'Empties truck unloading complete at supplier location': '',
                    'PLE: HAS': '',
                    'PLE: HRQ/HEE Dock 1': '',
                    'PLE: HRQ/HEE Dock 2': '',
                    'PLE: HRQ/HEE Dock 3': '',
                    'PLE: HRQ/HEE Dock 4': '',
                    'PLE: HRQ/HEE Dock 5': '',
                    'PLE: HRQ/HEE Dock 6': '',
                    'PLE: HRQ/HEE Dock 7': '',
                    'PLE: HRQ/HEE Dock 8': '',
                    'Avg. Loading Meters / week': shipper.loading_meters if first_shipper_row else '',
                    'Avg. Weight / week': shipper.weight if first_shipper_row else '',
                    'Avg. Volume / week': shipper.volume if first_shipper_row else '',
                    'Avg. Loading Meters / week (Linehaul)': self.linehaul_loading_meters if first_hub_row else '',
                    'Avg. Loading Meters / transport': self.linehaul_loading_meters
                                                       / self.linehaul_frequency if (
                            first_hub_row and self.linehaul_frequency) else (0 if first_hub_row else ''),
                    'Avg. Weight / week (Linehaul)': self.linehaul_weight if first_hub_row else '',
                    'Avg. Weight / transport': self.linehaul_weight / self.linehaul_frequency if (
                            first_hub_row and self.linehaul_frequency) else (0 if first_hub_row else ''),
                    'Avg. Volume / week on route': self.linehaul_volume if first_hub_row else '',
                    'Avg. Volume / transport': self.linehaul_volume / self.linehaul_frequency if (
                            first_hub_row and self.linehaul_frequency) else (0 if first_hub_row else ''),
                    'Avg. Loading meter utilization in %': self.linehaul_loading_meters_utilization if first_hub_row else '',
                    'Avg. Weight utilization in %': self.linehaul_weight_utilization if first_hub_row else '',
                    'Avg. Volume utilization in %': self.linehaul_volume_utilization if first_hub_row else '',
                    'Max. Utilization in %': self.linehaul_utilization if first_hub_row else '',
                    'Pre/on carriage total costs': self.pre_carriage_costs if first_hub_row else '',
                    'Pre/on carriage costs per week': self.total_pre_carriage_costs if first_hub_row else '',
                    'Linehaul total costs': self.linehaul_base_cost if first_hub_row else '',
                    'Linehaul costs per week': self.linehaul_cost if first_hub_row else '',
                    '[PERS. COLUMN] Original Network': shipper.original_network
                }
                rows.append(route_row)
                first_shipper_row = False
                first_hub_row = False

        return pd.DataFrame(rows)
