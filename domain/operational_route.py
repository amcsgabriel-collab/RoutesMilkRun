from math import ceil

import pandas as pd

from domain.route_pattern import RoutePattern
from domain.data_structures import Vehicle
from domain.exceptions import RouteNotOrderedError, DeviationNotCalculatedError, VehicleCapacityError


def _safe_div(numerator, denominator):
    if denominator is None or denominator == 0:
        return 0.0
    return numerator / denominator


class OperationalRoute:
    def __init__(
            self,
            pattern: RoutePattern,
            vehicle: Vehicle,
    ):
        self.pattern = pattern
        self.vehicle = vehicle

        self.is_new_route = pattern.is_new_pattern
        self.verify_vehicle_capacity()
        self.base_cost = 0
        self.stop_cost = 0
        self.tariff_source = None
        self.frequency = 0
        self.weight_utilization = 0
        self.volume_utilization = 0
        self.loading_meters_utilization = 0
        self.max_utilization = 0

        self.compute_utilization()

    def __hash__(self):
        return hash((self.pattern, self.vehicle))

    def __eq__(self, other):
        return (isinstance(other, OperationalRoute)
                and self.pattern == other.pattern
                and self.vehicle == other.vehicle)

    def tariff_key(self, digits: int = 2):
        if self.pattern.starting_point is None:
            raise RouteNotOrderedError()
        if self.pattern.deviation_bin is None:
            raise DeviationNotCalculatedError()
        return (
            self.pattern.carrier,
            self.vehicle.id,
            self.pattern.deviation_bin,
            self.pattern.starting_point.zip_key(digits),
            self.pattern.starting_point.cofor
        )

    @property
    def route_cost(self):
        return self.base_cost + self.stop_cost * self.pattern.count_of_stops

    @property
    def total_cost(self):
        return self.route_cost * self.frequency

    def verify_vehicle_capacity(self) -> None:
        if self.vehicle.weight_capacity <= 0 or self.vehicle.volume_capacity <= 0 or self.vehicle.loading_meters_capacity <= 0:
            raise VehicleCapacityError(f'Vehicle has negative capacity: {self.vehicle.id}')

    def _safe_capacity_ratio(self, demand, capacity):
        if (
                demand is None
                or capacity in (None, 0)
                or self.pattern.overutilization in (None, 0)
        ):
            return 0.0

        adjusted_capacity = capacity * self.pattern.overutilization
        if adjusted_capacity == 0:
            return 0.0

        return demand / adjusted_capacity

    def compute_utilization(self):

        ratios = [
            self._safe_capacity_ratio(self.pattern.weight,
                                      self.vehicle.weight_capacity),

            self._safe_capacity_ratio(self.pattern.volume,
                                      self.vehicle.volume_capacity),

            self._safe_capacity_ratio(self.pattern.loading_meters,
                                      self.vehicle.loading_meters_capacity),
        ]

        max_ratio = max(ratios)
        self.frequency = ceil(max_ratio)
        self.weight_utilization = round(
            _safe_div(self.pattern.weight,
                      self.vehicle.weight_capacity * self.frequency),
            4
        )
        self.volume_utilization = round(
            _safe_div(self.pattern.volume,
                      self.vehicle.volume_capacity * self.frequency),
            4
        )
        self.loading_meters_utilization = round(
            _safe_div(self.pattern.loading_meters,
                      self.vehicle.loading_meters_capacity * self.frequency),
            4
        )
        self.max_utilization = max(
            self.weight_utilization,
            self.volume_utilization,
            self.loading_meters_utilization
        )

    @property
    def summary(self):
        return {
            "name": self.pattern.route_name,
            "vehicle": self.vehicle.id,
            "base_cost": self.base_cost,
            "stop_cost": self.stop_cost,
            "weight_utilization": self.weight_utilization,
            "volume_utilization": self.volume_utilization,
            "loading_meters_utilization": self.loading_meters_utilization,
            "frequency": self.frequency,
            "shippers": [shipper.cofor for shipper in self.pattern.shippers],
        }

    @property
    def shippers_keyed_summary(self):
        sequence = [s.cofor for s in self.pattern.sequence]
        return {
            "key": "|".join(sequence),
            "sequence": sequence,
            "frequency": self.frequency,
            "utilization": f"{self.max_utilization * 100:.2f}%",
            "cost": f"{self.total_cost:.2f}€",
        }

    def generate_route_name(self):
        return f"{self.pattern.starting_point.cofor}_{self.pattern.plant.cofor}#P"

    def generate_tour_name(self):
        return f"FT_{self.pattern.starting_point.cofor}_{self.pattern.plant.cofor}#PS" \
            if self.pattern.transport_concept == "FTL" \
            else f"M{self.pattern.mr_cluster}_{self.pattern.starting_point.cofor}_{self.pattern.plant.cofor}#PS"

    def to_dataframe(self) -> pd.DataFrame:
        rows = []

        shippers = sorted(
            self.pattern.shippers,
            key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
        )

        first_route_row = True

        for shipper in shippers:
            sellers = sorted(
                shipper.sellers,
                key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
            )

            first_shipper_row = True

            for seller in sellers:
                route_row = {
                    'Tour name': self.generate_tour_name() if self.pattern.is_new_pattern else self.pattern.tour,
                    'Route name': self.generate_route_name() if self.pattern.is_new_pattern else self.pattern.route_name,
                    'Shipper COFOR': shipper.cofor,
                    'Seller COFOR': seller.cofor,
                    'Hybrid COFOR': seller.cofor,
                    'Plant COFOR': self.pattern.plant.cofor,
                    'Parts or Empties': 'P',
                    'Index of MR': self.pattern.sequence.index(shipper) + 1,
                    'Roundtrip Identifier': 0,
                    'Docks (,)': '',
                    'First pickup': '',
                    'Total transit time (days)': '',
                    'First delivery': '',
                    'Carrier COFOR': shipper.carrier.cofor,
                    'Carrier ID': shipper.carrier.id,
                    'Carrier name': shipper.carrier.name,
                    'Means of Transport': self.vehicle.id,
                    'Transport Concept': self.pattern.transport_concept,
                    'MR Cluster\n(S, L, M, H)': self.pattern.mr_cluster if self.pattern.transport_concept == "MR" else "",
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
                    'Frequency / week': self.frequency,
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
                    'Avg. Loading Meters / week on route': self.pattern.loading_meters if first_route_row else '',
                    'Avg. Loading Meters / transport': self.pattern.loading_meters / self.frequency if (
                            first_route_row and self.frequency) else (0 if first_route_row else ''),
                    'Avg. Weight / week on route': self.pattern.weight if first_route_row else '',
                    'Avg. Weight / transport': self.pattern.weight / self.frequency if (
                            first_route_row and self.frequency) else (0 if first_route_row else ''),
                    'Avg. Volume / week on route': self.pattern.volume if first_route_row else '',
                    'Avg. Volume / transport': self.pattern.volume / self.frequency if (
                            first_route_row and self.frequency) else (0 if first_route_row else ''),
                    'Avg. Loading meter utilization in %': self.loading_meters_utilization if first_route_row else '',
                    'Avg. Weight utilization in %': self.weight_utilization if first_route_row else '',
                    'Avg. Volume utilization in %': self.volume_utilization if first_route_row else '',
                    'Max. Utilization in %': self.max_utilization if first_route_row else '',
                    'Base cost': self.base_cost if first_route_row else '',
                    'Stop cost': self.stop_cost if first_route_row else '',
                    'Total costs per load': self.route_cost if first_route_row else '',
                    'Total costs per week': self.total_cost if first_route_row else '',
                    '[PERS. COLUMN] Original Network': shipper.original_network
                }
                rows.append(route_row)

                first_shipper_row = False
                first_route_row = False

        return pd.DataFrame(rows)
