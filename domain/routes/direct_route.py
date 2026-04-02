import pandas as pd

from domain.data_structures import Vehicle
from domain.routes.route import Route
from domain.routes.route_costing_strategies import TruckBasedCosting
from domain.routes.route_demand_aggregation_strategies import MilkrunPatternDemand
from domain.routes.route_pattern import RoutePattern
from domain.tariff import FtlTariff


class DirectRoute(Route):
    def __init__(self, pattern: RoutePattern, vehicle: Vehicle, flow_type: str):
        super().__init__(
            vehicle=vehicle,
            demand=MilkrunPatternDemand(pattern=pattern, flow_type=flow_type),
            costing=TruckBasedCosting(),
        )
        self.tariff: FtlTariff | None = None

    def __hash__(self):
        return hash((self.demand.pattern, self.vehicle))

    def __eq__(self, other):
        return (isinstance(other, DirectRoute)
                and self.demand.pattern == other.demand.pattern
                and self.demand.vehicle == other.vehicle)

    @property
    def destination(self):
        return self.demand.pattern.plant

    @property
    def summary(self):
        return {
            "name": self.demand.pattern.route_name,
            "vehicle": self.vehicle.id,
            "base_cost": self.tariff.base_cost,
            "stop_cost": self.tariff.stop_cost,
            "weight_utilization": self.weight_utilization,
            "volume_utilization": self.volume_utilization,
            "loading_meters_utilization": self.loading_meters_utilization,
            "frequency": self.frequency,
            "shippers": [shipper.cofor for shipper in self.demand.pattern.shippers],
        }

    @property
    def shippers_keyed_summary(self):
        sequence = [s.cofor for s in self.demand.pattern.sequence]
        return {
            "key": "|".join(sequence),
            "sequence": sequence,
            "frequency": self.frequency,
            "utilization": f"{self.max_utilization * 100:.2f}%",
            "cost": f"{self.total_cost:.2f}€",
        }

    def generate_route_name(self):
        direction = "P" if self.demand.flow_type == "parts" else "E"
        return f"{self.demand.pattern.starting_point.cofor}_{self.demand.pattern.plant.cofor}#{direction}"

    @property
    def route_name(self):
        return self.generate_route_name() \
            if self.demand.pattern.is_new_pattern \
            else self.demand.pattern.route_name

    def generate_tour_name(self):
        return f"FT_{self.demand.pattern.starting_point.cofor}_{self.demand.pattern.plant.cofor}#PS" \
            if self.demand.pattern.transport_concept == "FTL" \
            else f"M{self.demand.pattern.mr_cluster}_{self.demand.pattern.starting_point.cofor}_{self.demand.pattern.plant.cofor}#PS"

    def export_dataframe(self, tour_name:str, roundtrip_id:str) -> pd.DataFrame:
        rows = []
        shippers = sorted(
            self.demand.pattern.shippers,
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
                    'Tour name': tour_name,
                    'Route name': self.route_name,
                    'Shipper COFOR': shipper.cofor,
                    'Seller COFOR': seller.cofor,
                    'Hybrid COFOR': seller.cofor,
                    'Plant COFOR': self.demand.plant.cofor,
                    'Parts or Empties': "P" if self.demand.flow_type == "parts" else "E",
                    'Index of MR': self.demand.pattern.sequence.index(shipper) + 1,
                    'Roundtrip Identifier': roundtrip_id,
                    'Docks (,)': '',
                    'First pickup': '',
                    'Total transit time (days)': '',
                    'First delivery': '',
                    'Carrier COFOR': shipper.carrier.cofor,
                    'Carrier ID': shipper.carrier.id,
                    'Carrier name': shipper.carrier.name,
                    'Means of Transport': self.vehicle.id,
                    'Transport Concept': self.demand.pattern.transport_concept,
                    'MR Cluster\n(S, L, M, H)': self.demand.pattern.mr_cluster if self.demand.pattern.transport_concept == "MR" else "",
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
                    'Avg. Loading Meters / week on route': self.demand.pattern.loading_meters if first_route_row else '',
                    'Avg. Loading Meters / transport': self.demand.pattern.loading_meters / self.frequency if (
                            first_route_row and self.frequency) else (0 if first_route_row else ''),
                    'Avg. Weight / week on route': self.demand.pattern.weight if first_route_row else '',
                    'Avg. Weight / transport': self.demand.pattern.weight / self.frequency if (
                            first_route_row and self.frequency) else (0 if first_route_row else ''),
                    'Avg. Volume / week on route': self.demand.pattern.volume if first_route_row else '',
                    'Avg. Volume / transport': self.demand.pattern.volume / self.frequency if (
                            first_route_row and self.frequency) else (0 if first_route_row else ''),
                    'Avg. Loading meter utilization in %': self.loading_meters_utilization if first_route_row else '',
                    'Avg. Weight utilization in %': self.weight_utilization if first_route_row else '',
                    'Avg. Volume utilization in %': self.volume_utilization if first_route_row else '',
                    'Max. Utilization in %': self.max_utilization if first_route_row else '',
                    'Base cost': self.tariff.base_cost if first_route_row else '',
                    'Stop cost': self.tariff.stop_cost if first_route_row else '',
                    'Total costs per load': self.route_cost if first_route_row else '',
                    'Total costs per week': self.total_cost if first_route_row else '',
                    '[PERS. COLUMN] Original Network': shipper.original_network
                }
                rows.append(route_row)

                first_shipper_row = False
                first_route_row = False

        return pd.DataFrame(rows)