from typing import Literal

import pandas as pd

from domain.general_algorithms import decimal_to_dms_str
from domain.data_structures import Carrier, Vehicle, Plant
from domain.routes.first_leg_route import FirstLegRoute
from domain.routes.linehaul_route import LinehaulRoute
from domain.shipper import Shipper


class Hub:
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
            has_empties_flow: bool = False,
    ):
        self.route_id = route
        self.cofor = cofor
        self.name = name
        self.country = country
        self.zip_code = str(zip_code)
        self.plant = plant
        self.shippers = shippers
        self.has_empties_flow = has_empties_flow
        self.first_leg_carrier = first_leg_carrier
        self.first_leg_vehicle = first_leg_vehicle
        self.linehaul_transport_concept = linehaul_transport_concept
        self.parts_first_leg_routes = set()
        self.empties_first_leg_routes = set()
        self.parts_linehaul_route = LinehaulRoute(hub=self, vehicle=linehaul_vehicle, carrier=linehaul_carrier, flow_direction="parts")

        self.coordinates = coordinates
        self.refresh_first_leg_routes("parts")
        if self.has_empties_flow:
            self.refresh_first_leg_routes("empties")
            self.empties_linehaul_route = LinehaulRoute(hub=self,
                                                        vehicle=linehaul_vehicle,
                                                        carrier=linehaul_carrier,
                                                        flow_direction="empties")


    @property
    def formatted_coordinates(self):
        return decimal_to_dms_str(self.coordinates)

    @property
    def empties_pre_carriage_costs(self):
        return sum(r.total_cost for r in self.empties_first_leg_routes)

    @property
    def empties_total_cost(self):
        return self.empties_pre_carriage_costs + self.empties_linehaul_route.total_cost

    @property
    def parts_pre_carriage_costs(self):
        return sum(r.total_cost for r in self.parts_first_leg_routes)

    @property
    def parts_total_cost(self):
        return self.parts_pre_carriage_costs + self.parts_linehaul_route.total_cost

    @property
    def pre_carriage_costs(self):
        return self.parts_pre_carriage_costs + self.empties_pre_carriage_costs

    @property
    def linehaul_total_cost(self):
        return self.parts_linehaul_route.total_cost + (
            self.empties_linehaul_route.total_cost if self.has_empties_flow else 0
        )

    @property
    def total_costs(self):
        return self.pre_carriage_costs + self.linehaul_total_cost

    def zip_key(self, digits):
        return self.country + self.zip_code[:digits]

    def summary(self, flow_direction):
        if flow_direction == "parts":
            linehaul_route = self.parts_linehaul_route
            pre_carriage_costs = self.parts_pre_carriage_costs
        else:
            linehaul_route = self.empties_linehaul_route
            pre_carriage_costs = self.empties_pre_carriage_costs
        return {
            "name": self.name,
            "cofor": self.cofor,
            "first_leg_cost": pre_carriage_costs,
            "linehaul_frequency": linehaul_route.frequency,
            "linehaul_cost": linehaul_route.total_cost,
            "linehaul_weight": linehaul_route.weight,
            "linehaul_volume": linehaul_route.volume,
            "linehaul_loading_meters": linehaul_route.loading_meters,
            "linehaul_weight_utilization": linehaul_route.weight_utilization,
            "linehaul_volume_utilization": linehaul_route.volume_utilization,
            "linehaul_loading_meters_utilization": linehaul_route.loading_meters_utilization,
            "coordinates": self.coordinates,
        }

    @property
    def identity(self):
        return {
            "name": self.name,
            "cofor": self.cofor,
        }

    def refresh_first_leg_routes(self, flow_direction: str):
        attr = f"has_{flow_direction}_demand"
        routes = {
            FirstLegRoute(
                shipper=shipper,
                carrier=self.first_leg_carrier,
                vehicle=self.first_leg_vehicle,
                hub=self,
                flow_direction=flow_direction
            ) for shipper in self.shippers if getattr(shipper, attr)
        }
        if flow_direction == "parts":
            self.parts_first_leg_routes = routes
        else:
            self.empties_first_leg_routes = routes

    def generate_route_name(self, flow_direction):
        direction = "P" if flow_direction=="parts" else "E"
        trip_type = "R" if self.has_empties_flow else "S"
        return f"GD_{self.name} #{direction}{trip_type}"

    def to_dataframe(self):
        rows = []

        def append_flow_rows(
                flow: Literal["parts", "empties"],
                first_leg_routes: set[FirstLegRoute],
                linehaul_route,
                flow_code: str,
        ) -> None:
            routes = sorted(
                first_leg_routes,
                key=lambda r: ((r.shipper.name or "").lower(), (r.shipper.cofor or "").lower())
            )

            first_hub_row = True

            for route in routes:
                route_name = self.generate_route_name(flow)
                shipper = route.demand.shipper
                demand = shipper.parts_demand if flow_code == "P" else shipper.empties_demand
                sellers = sorted(
                    demand.sellers,
                    key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
                )

                first_shipper_row = True

                for seller in sellers:
                    route_row = {
                        'Route name': route_name,
                        'HUB Name': self.name,
                        'Shipper COFOR': shipper.cofor,
                        'Seller COFOR': seller.cofor,
                        'Hybrid COFOR': seller.cofor,
                        'Plant COFOR': self.plant.cofor,
                        'Parts or Empties': flow_code,
                        'Docks (,)': '',
                        'First pickup': '',
                        'Total transit time (days)': '',
                        'First delivery': '',
                        'Carrier COFOR': shipper.carrier.cofor,
                        'Carrier ID': shipper.carrier.id,
                        'Carrier name': shipper.carrier.name,
                        'Means of Transport': route.vehicle.id,
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
                        'Avg. Loading Meters / week': demand.loading_meters if first_shipper_row else '',
                        'Avg. Weight / week': demand.weight if first_shipper_row else '',
                        'Avg. Volume / week': demand.volume if first_shipper_row else '',
                        'Avg. Loading Meters / week (Linehaul)': linehaul_route.loading_meters if first_hub_row else '',
                        'Avg. Loading Meters / transport': (
                            linehaul_route.loading_meters / linehaul_route.frequency
                            if first_hub_row and linehaul_route.frequency else (0 if first_hub_row else '')
                        ),
                        'Avg. Weight / week (Linehaul)': linehaul_route.weight if first_hub_row else '',
                        'Avg. Weight / transport': (
                            linehaul_route.weight / linehaul_route.frequency
                            if first_hub_row and linehaul_route.frequency else (0 if first_hub_row else '')
                        ),
                        'Avg. Volume / week on route': linehaul_route.volume if first_hub_row else '',
                        'Avg. Volume / transport': (
                            linehaul_route.volume / linehaul_route.frequency
                            if first_hub_row and linehaul_route.frequency else (0 if first_hub_row else '')
                        ),
                        'Avg. Loading meter utilization in %': linehaul_route.loading_meters_utilization if first_hub_row else '',
                        'Avg. Weight utilization in %': linehaul_route.weight_utilization if first_hub_row else '',
                        'Avg. Volume utilization in %': linehaul_route.volume_utilization if first_hub_row else '',
                        'Max. Utilization in %': linehaul_route.utilization if first_hub_row else '',
                        'Pre/on carriage total costs': self.pre_carriage_costs if first_hub_row else '',
                        'Pre/on carriage costs per week': self.pre_carriage_costs if first_hub_row else '',
                        'Linehaul total costs': linehaul_route.route_cost if first_hub_row else '',
                        'Linehaul costs per week': linehaul_route.total_cost if first_hub_row else '',
                        '[PERS. COLUMN] Original Network': shipper.original_network,
                    }
                    rows.append(route_row)
                    first_shipper_row = False
                    first_hub_row = False

        append_flow_rows(
            flow="parts",
            first_leg_routes=self.parts_first_leg_routes,
            linehaul_route=self.parts_linehaul_route,
            flow_code="P",
        )

        if self.has_empties_flow:
            append_flow_rows(
                flow="empties",
                first_leg_routes=self.empties_first_leg_routes,
                linehaul_route=self.empties_linehaul_route,
                flow_code="E",
            )

        return pd.DataFrame(rows)
