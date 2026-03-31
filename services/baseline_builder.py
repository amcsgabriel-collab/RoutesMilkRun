from collections import defaultdict
from typing import Optional, Callable

import pandas as pd

from domain.domain_algorithms import make_haversine_cache
from domain.exceptions import ShippersWithoutLocationsError, MissingTariffsError, CarriersNotInHelperError
from domain.hub import Hub
from domain.routes.first_leg_route import FirstLegRoute
from domain.routes.linehaul_route import LinehaulRoute
from domain.routes.direct_route import DirectRoute
from domain.project import Scenario, SourcingRegion, ProjectContext
from domain.routes.route_pattern import RoutePattern
from domain.shipper import Shipper
from infrastructure.data_loader import DataLoader
from infrastructure.demand_data_transformer import DemandDataTransformer
from infrastructure.graf_loader import GrafLoader
from infrastructure.tariffs_transformer import TariffsTransformer
from paths import get_helper_path
from repositories.data_structures_repository import SellerRepository, PlantRepository, CarrierRepository
from repositories.hub_repository import HubRepository
from repositories.direct_route_repository import DirectRouteRepository
from repositories.route_pattern_repository import RoutePatternRepository
from repositories.shipper_repository import ShipperRepository
from repositories.tariffs_repository import ftl_tariffs_from_dataframe, ltl_tariffs_from_dataframe
from repositories.vehicle_repository import VehicleRepository
from services.tariff_service import TariffService

LogFn = Callable[[str], None]


def verify_coordinates(shippers: dict[str, Shipper]):
    shippers_without_coordinates = [
        cofor
        for cofor, shipper in shippers.items()
        if any(pd.isna(c) for c in shipper.coordinates) or not shipper.coordinates
    ]

    if shippers_without_coordinates:
        raise ShippersWithoutLocationsError(shippers_without_coordinates)


def verify_total_volume(route_patterns: list["RoutePattern"], shippers: list["Shipper"]):
    share_sum_by_shipper = defaultdict(float)
    patterns_by_shipper = defaultdict(list)

    for pattern in route_patterns:
        for s, share in pattern.shipper_allocation.items():
            cofor = s.cofor if hasattr(s, "cofor") else s  # supports dict keyed by Shipper or by cofor
            share = float(share or 0.0)
            share_sum_by_shipper[cofor] += share
            patterns_by_shipper[cofor].append((pattern, share))

    # iterate over the full shipper list (not only those seen)
    for s in shippers:
        cofor = s.cofor
        total_share = share_sum_by_shipper.get(cofor, 0.0)

        if abs(total_share - 1.0) > 1e-6:
            print(f"\n❌ Allocation error for shipper {cofor}")
            print(f"Total allocation: {total_share:.6f}")

            if cofor not in patterns_by_shipper:
                print("Patterns contributing: NONE (shipper never appears in shipper_allocation of any pattern)")
                continue

            print("Patterns contributing:")
            for pattern, share in patterns_by_shipper[cofor]:
                print(f"  Route: {pattern.route_name} | Allocation: {share:.6f}")


def validate_ftl_missing_tariffs(routes: set[DirectRoute]) -> None:
    missing = [
        {"zip_key": route.demand.starting_point.zip_key(5),
         "cofor": route.demand.starting_point.cofor,
         "carrier": route.demand.carrier.group,
         "vehicle": route.vehicle.id,
         "deviation_bucket": route.demand.deviation_bin,
         } for route in routes if route.tariff_source == 'Missing'
    ]
    if missing:
        raise MissingTariffsError(tariff_type='ftl', missing_tariffs=missing)


def validate_ltl_missing_tariffs(routes: set[FirstLegRoute]) -> None:
    missing = [
        {"zip_key": route.demand.starting_point.zip_key(5),
         "cofor": route.demand.starting_point.cofor,
         "carrier": route.demand.carrier.group,
         "destination": route.destination,
         "weight_bracket": route.costing.weight_bracket_ltl(route),
         } for route in routes if route.tariff_source == 'Missing'
    ]
    if missing:
        raise MissingTariffsError(tariff_type='ltl', missing_tariffs=missing)


def validate_linehaul_missing_tariffs(route: LinehaulRoute) -> None:
    missing = [
        {
            "zip_key": route.demand.starting_point.zip_key(2),
            "cofor": route.demand.starting_point.cofor,
            "carrier": route.demand.carrier.group,
            "vehicle": route.vehicle.id,
            "deviation_bucket": route.demand.deviation_bin,
        }
    ] if route.tariff_source == "Missing" else []
    if missing:
        raise MissingTariffsError(tariff_type='linehaul', missing_tariffs=missing)


class BaselineBuilder:
    def __init__(self, graf_path, logger: Optional[LogFn] = None):

        self.graf_path = graf_path
        self.graf_loader = GrafLoader(graf_path)
        self.data_loader = DataLoader(get_helper_path())
        self.logger = logger

        self.direct_demand_database = pd.DataFrame()
        self.hub_demand_database = pd.DataFrame()
        self.tariffs_database = None
        self.ftl_tariffs_database = None
        self.hubs_list = []
        self.ltl_tariffs_database = None
        self.carrier_helper = None
        self.plant_name_helper = None
        self.vehicles_database = None
        self.locations_database = None

        # Domain Objects
        self.plant = None
        self.vehicles = None
        self.as_is_scenario = None

        self.direct_routes = None
        self.tariffs_service: TariffService | None = None

    def _log(self, msg: str):
        if self.logger:
            self.logger(msg)

    def build_context(self):
        self._log('Loading Helper Data...')
        self._load_helper_data()
        self._log('Loading GRAF Data...')
        self._load_graf_data()
        self._log('Preparing GRAF demand data...')
        self._transform_graf_demand_data()
        self._log('Creating domain objects...')
        self._create_general_domain_objects()
        self._log('Preparing Tariffs...')
        self._create_tariffs()
        self._log('Preparing Sourcing Regions...')
        regions = {
            region: self._create_region_baseline(region)
            for region in self.direct_demand_database['SHIPPER SOURCING REGION'].unique()
        }
        self._log('Creating Project Context...')
        return ProjectContext(
            plant=self.plant,
            vehicles=[v for v in self.vehicles.values()],
            tariffs_service=self.tariffs_service,
            regions=regions
        )

    def _load_graf_data(self):
        self.direct_demand_database = self.graf_loader.load_demand_database('Direct')
        self.hub_demand_database = self.graf_loader.load_demand_database('Hub')
        self.tariffs_database = self.graf_loader.load_tariffs_database()
        self.carrier_helper = self.graf_loader.load_carrier_helper()
        self.plant_name_helper = self.graf_loader.load_plant_name_helper()
        self.vehicles_database = self.graf_loader.load_vehicles()

    def _load_helper_data(self):
        self.locations_database = self.data_loader.load_excel(
            'locations',
            'Locations',
            ['Key', 'Latitude', 'Longitude', 'ZIP Code', 'Country']
        )

    def _transform_graf_demand_data(self):
        self.direct_demand_database = DemandDataTransformer(
            self.direct_demand_database,
            self.carrier_helper,
            self.plant_name_helper,
            self.locations_database
        ).transform_database()

        self.hub_demand_database = DemandDataTransformer(
            self.hub_demand_database,
            self.carrier_helper,
            self.plant_name_helper,
            self.locations_database,
            is_hub_database=True
        ).transform_database()

    def check_source_data(self):
        # Verifying if every carrier in the transport plans are in the helper sheet
        direct_carriers = set(self.direct_demand_database['Carrier ID'].unique())
        all_carriers = direct_carriers
        carriers_in_helper = set(self.carrier_helper['Carrier ID'].unique())
        if not all_carriers.issubset(carriers_in_helper):
            raise CarriersNotInHelperError(all_carriers.difference(carriers_in_helper))

        # TODO: Implement vehicle check to guarantee all missing vehicles get mapped.

    def _create_general_domain_objects(self) -> None:
        self.plant = PlantRepository(self.direct_demand_database).get_plant()
        self.vehicles = VehicleRepository(self.vehicles_database).extract_vehicles()

    def _create_tariffs(self) -> None:
        hub_cofors = list(self.hub_demand_database['HUB COFOR'].unique())
        transformer = TariffsTransformer(
            self.tariffs_database,
            hub_cofors=hub_cofors,
            plant_cofor=self.plant.cofor
        )

        self.ftl_tariffs_database = transformer.get_transformed_tariffs('ftl')
        ftl_tariffs_by_key = ftl_tariffs_from_dataframe(self.ftl_tariffs_database)

        self.ltl_tariffs_database = transformer.get_transformed_tariffs('ltl')
        ltl_tariffs_by_key = ltl_tariffs_from_dataframe(self.ltl_tariffs_database)

        self.tariffs_service = TariffService(
            ftl_mr_tariffs=ftl_tariffs_by_key,
            ltl_tariffs=ltl_tariffs_by_key,
            hub_tariffs=None
        )

    def _create_region_baseline(self, region: str) -> SourcingRegion:
        """
        Creates baseline scenario for specified sourcing region, with currently used Hubs and Direct Routes.
        Frequencies are already adjusted to currently available demand.
        :param region: Sourcing region name.
        :return: SourcingRegion object containing baseline scenario.
        """
        hubs = self._create_hubs(region)
        direct_routes = self._create_direct_routes(region)

        baseline_scenario = Scenario(
            name='AS-IS',
            routes=direct_routes,
            hubs=set(hubs),
        )
        baseline_scenario.is_baseline = True

        region = SourcingRegion(
            name=region,
            scenarios={baseline_scenario.name: baseline_scenario},
        )
        return region

    def _create_hubs(self, region: str) -> set[Hub]:
        """
        Create Hub domain objects and it's dependencies for the specified sourcing region.
        :param region:
        :return:
        """
        region_filtered_hub_database = self.hub_demand_database[
            self.hub_demand_database['SHIPPER SOURCING REGION'] == region]
        aggregated_demand_by_shipper = DemandDataTransformer(
            region_filtered_hub_database).aggregate_database_by_shipper()

        sellers = SellerRepository(region_filtered_hub_database).get_by_shipper()
        carriers = CarrierRepository(region_filtered_hub_database).get_all_hub()
        hub_shippers_by_cofor = ShipperRepository(aggregated_demand_by_shipper).get_all(
            sellers_by_shipper=sellers,
            carriers=carriers['first_leg'],
            are_hub_shippers=True
        )
        verify_coordinates(hub_shippers_by_cofor)

        hubs = HubRepository(region_filtered_hub_database).get_all(
            shippers=hub_shippers_by_cofor,
            carriers=carriers,
            vehicles=self.vehicles,
            plant=self.plant)

        self._assign_hub_tariffs(hubs)
        return hubs

    def _assign_hub_tariffs(self, hubs: list[Hub]) -> None:
        """ Retrieve and assign tariffs to hub first leg and linehaul routes. """
        for hub in hubs:
            self.tariffs_service.assign_ltl_routes(hub.first_leg_routes)
            validate_ltl_missing_tariffs(hub.first_leg_routes)

            if hub.linehaul_transport_concept in {"FTL", "MR"}:
                self.tariffs_service.assign_linehaul(hub.linehaul_route)
            else:
                self.tariffs_service.assign_ltl_linehaul(hub.linehaul_route)
            validate_linehaul_missing_tariffs(hub.linehaul_route)


    def _create_direct_routes(self, region):
        direct_demand_for_region = self.direct_demand_database[
            self.direct_demand_database['SHIPPER SOURCING REGION'] == region]

        # Creating Direct network objects
        direct_sellers = SellerRepository(direct_demand_for_region).get_by_shipper()
        direct_carriers = CarrierRepository(direct_demand_for_region).get_all()
        aggregated_direct_demand_by_shipper = DemandDataTransformer(
            direct_demand_for_region).aggregate_database_by_shipper()
        direct_shippers_by_cofor = ShipperRepository(
            aggregated_direct_demand_by_shipper
        ).get_all(
            carriers=direct_carriers,
            sellers_by_shipper=direct_sellers
        )
        verify_coordinates(shippers=direct_shippers_by_cofor)

        aggregated_direct_demand_by_route = DemandDataTransformer(
            direct_demand_for_region).aggregated_database_by_route()
        route_patterns_by_vehicle = RoutePatternRepository(
            aggregated_direct_demand_by_route,
            distance_function=make_haversine_cache()
        ).get_all(
            shippers_by_cofor=direct_shippers_by_cofor,
            plant=self.plant,
        )
        verify_total_volume(
            route_patterns=[pattern for vehicle_set in route_patterns_by_vehicle.values() for pattern in vehicle_set],
            shippers=[s for s in direct_shippers_by_cofor.values()]
        )

        direct_routes = DirectRouteRepository(
            patterns_by_vehicle=route_patterns_by_vehicle,
            vehicles=self.vehicles,
        ).get_all()

        self.tariffs_service.assign_ftl_mr_routes(direct_routes)
        validate_ftl_missing_tariffs(direct_routes)

        return direct_routes
