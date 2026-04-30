from collections import defaultdict
from typing import Optional, Callable

import pandas as pd

from ..domain.domain_algorithms import make_haversine_cache
from ..domain.exceptions import (
    ShippersWithoutLocationsError,
    MissingTariffsError,
    CarriersNotInHelperError,
)
from ..domain.hub import Hub
from ..domain.regional_hub_view import RegionalHubView
from ..domain.routes.first_leg_route import FirstLegRoute
from ..domain.routes.linehaul_route import LinehaulRoute
from ..domain.routes.direct_route import DirectRoute
from ..domain.project import Scenario, SourcingRegion, ProjectContext
from ..domain.routes.route_pattern import RoutePattern
from ..domain.shipper import Shipper
from ..domain.trip import Trip
from ..infrastructure.data_loader import DataLoader
from ..infrastructure.demand_data_transformer import DemandDataTransformer
from ..infrastructure.graf_loader import GrafLoader
from ..infrastructure.tariffs_transformer import TariffsTransformer
from ..paths import get_helper_path
from ..repositories.data_structures_repository import (
    SellerRepository,
    PlantRepository,
    CarrierRepository,
)
from ..repositories.hub_repository import HubRepository
from ..repositories.direct_route_repository import DirectRouteRepository
from ..repositories.route_pattern_repository import RoutePatternRepository
from ..repositories.shipper_repository import ShipperRepository
from ..repositories.tariffs_repository import (
    ftl_tariffs_from_dataframe,
    ltl_tariffs_from_dataframe, hub_tariffs_from_dataframe,
)
from ..repositories.trip_repository import TripRepository
from ..repositories.vehicle_repository import VehicleRepository
from ..services.tariff_service import TariffService

LogFn = Callable[[str], None]

BASELINE_SCENARIO = "AS-IS"
ALL_REGIONS = "ALL REGIONS"


def verify_coordinates(shippers: dict[str, Shipper]):
    shippers_without_coordinates = [
        cofor
        for cofor, shipper in shippers.items()
        if any(pd.isna(c) for c in shipper.coordinates) or not shipper.coordinates
    ]

    if shippers_without_coordinates:
        raise ShippersWithoutLocationsError(shippers_without_coordinates)


def verify_total_volume(route_patterns: list["RoutePattern"], shippers: list["Shipper"]):
    share_sum_by_shipper_and_flow = defaultdict(float)
    patterns_by_shipper_and_flow = defaultdict(list)

    for pattern in route_patterns:
        flow_direction = pattern.flow_direction

        for s, share in pattern.shipper_allocation.items():
            cofor = s.cofor if hasattr(s, "cofor") else s
            share = float(share or 0.0)
            key = (cofor, flow_direction)

            share_sum_by_shipper_and_flow[key] += share
            patterns_by_shipper_and_flow[key].append((pattern, share))

    for shipper in shippers:
        expected_demands = [
            shipper.parts_demand,
            shipper.empties_demand,
        ]

        for demand in expected_demands:
            if (
                demand.weight == 0.0
                and demand.volume == 0.0
                and demand.loading_meters == 0.0
            ):
                continue

            flow_code = "parts" if demand.type == "P" else "empties"
            key = (shipper.cofor, flow_code)
            total_share = share_sum_by_shipper_and_flow.get(key, 0.0)

            if abs(total_share - 1.0) > 1e-6:
                print(f"\n❌ Allocation error for shipper {shipper.cofor} / flow {demand.type}")
                print(f"Total allocation: {total_share:.6f}")

                if key not in patterns_by_shipper_and_flow:
                    print("Patterns contributing: NONE (shipper/flow never appears in shipper_allocation of any pattern)")
                    continue

                print("Patterns contributing:")
                for pattern, share in patterns_by_shipper_and_flow[key]:
                    print(
                        f"  Route: {pattern.route_name} | Flow: {pattern.flow_direction} | Allocation: {share:.6f}"
                    )

def verify_direct_trips_match_dataframe(
    trips: set[Trip],
    direct_demand_database: pd.DataFrame,
) -> None:
    expected_by_route = defaultdict(lambda: {
        "weight": 0.0,
        "volume": 0.0,
        "loading_meters": 0.0,
        "shippers": set(),
    })

    for _, row in direct_demand_database.iterrows():
        route_name = row["Route name"]

        expected_by_route[route_name]["weight"] += float(row["Avg. Weight / week"] or 0.0)
        expected_by_route[route_name]["volume"] += float(row["Avg. Volume / week"] or 0.0)
        expected_by_route[route_name]["loading_meters"] += float(
            row["Avg. Loading Meters / week"] or 0.0
        )
        expected_by_route[route_name]["shippers"].add(row["Shipper COFOR"])

    routes_by_name = {}

    for trip in trips:
        for route in (trip.parts_route, trip.empties_route):
            if route is not None:
                routes_by_name[route.route_name] = route

    missing_routes = sorted(set(expected_by_route) - set(routes_by_name))
    if missing_routes:
        print("\n❌ Direct routes missing from final trips:")
        for route_name in missing_routes:
            print(f"  {route_name}")

    allocation_by_shipper_and_flow = defaultdict(float)

    for route in routes_by_name.values():
        flow_direction = route.demand.flow_direction

        for shipper, allocation in route.demand.pattern.shipper_allocation.items():
            cofor = shipper.cofor if hasattr(shipper, "cofor") else shipper
            allocation_by_shipper_and_flow[(cofor, flow_direction)] += float(allocation or 0.0)


    for route_name, expected in expected_by_route.items():
        route = routes_by_name.get(route_name)
        if route is None:
            continue

        demand = route.demand

        actuals = {
            "weight": demand.weight,
            "volume": demand.volume,
            "loading_meters": demand.loading_meters,
        }

        for variable, actual in actuals.items():
            expected_value = expected[variable]
            if abs(float(actual or 0.0) - expected_value) > 1e-6:
                print(f"\n❌ Demand mismatch for route {route_name} / {variable}")
                print(f"Expected: {expected_value:.6f}")
                print(f"Actual:   {float(actual or 0.0):.6f}")

        flow_direction = route.demand.flow_direction
        for shipper in expected["shippers"]:
            total_allocation = allocation_by_shipper_and_flow[(shipper, flow_direction)]

            if abs(total_allocation - 1.0) > 1e-6:
                print(f"\n❌ Allocation error for shipper {shipper} / flow {flow_direction}")
                print(f"Total allocation across final direct routes: {total_allocation:.6f}")


def validate_ftl_missing_tariffs(routes: set[DirectRoute]) -> None:
    missing = [
        {
            "zip_key": route.demand.starting_point.zip_key(5),
            "cofor": route.demand.starting_point.cofor,
            "carrier": route.demand.carrier.group,
            "vehicle": route.vehicle.id,
            "deviation_bucket": route.deviation_bin,
        }
        for route in routes
        if route.tariff_source == "Missing"
    ]
    if missing:
        raise MissingTariffsError(tariff_type="ftl", missing_tariffs=missing)


def validate_ltl_missing_tariffs(routes: set[FirstLegRoute]) -> None:
    missing = [
        {
            "zip_key": route.demand.starting_point.zip_key(5),
            "cofor": route.demand.starting_point.cofor,
            "carrier": route.demand.carrier.group,
            "destination": route.destination.cofor,
            "weight_bracket": route.costing.weight_bracket_ltl(route),
        }
        for route in routes
        if route.tariff_source == "Missing"
    ]
    if missing:
        raise MissingTariffsError(tariff_type="ltl", missing_tariffs=missing)


def validate_linehaul_missing_tariffs(route: LinehaulRoute) -> None:
    missing = [
        {
            "zip_key": route.demand.starting_point.zip_key(2),
            "cofor": route.demand.starting_point.cofor,
            "carrier": route.carrier.group,
            "vehicle": route.vehicle.id,
            "deviation_bucket": route.deviation_bin,
        }
    ] if route.tariff_source == "Missing" else []
    if missing:
        raise MissingTariffsError(tariff_type="linehaul", missing_tariffs=missing)


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
        self.hub_tariffs_database = None
        self.carrier_helper = None
        self.plant_name_helper = None
        self.vehicles_database = None
        self.locations_database = None

        # Domain Objects
        self.plant = None
        self.vehicles = None
        self.as_is_scenario = None
        self.tariffs_service: TariffService | None = None

    def _log(self, msg: str):
        if self.logger:
            self.logger(msg)

    def _log_missing_tariffs(self, exc: MissingTariffsError) -> None:
        self._log(str(exc))

    def build_context(self):
        self._log("Loading Helper Data...")
        self._load_helper_data()

        self._log("Loading GRAF Data...")
        self._load_graf_data()

        self._log("Preparing GRAF demand data...")
        self._transform_graf_demand_data()

        self._log("Creating domain objects...")
        self._create_general_domain_objects()

        self._log("Preparing Tariffs...")
        self._create_tariffs()

        self._log("Creating global hubs...")
        global_hubs = self._create_hubs_global()

        self._log("Creating global trips...")
        global_trips = self._create_trips_global()

        self._log("Retaining only vehicles used by existing routes...")
        self._retain_only_used_vehicles(global_trips)

        self._log("Creating global baseline scenario...")
        global_baseline = Scenario(
            name=BASELINE_SCENARIO,
            trips=global_trips,
            hubs=global_hubs,
            is_baseline=True,
        )
        global_baseline.refresh_lock_block_available_routes()

        self._log("Splitting global baseline into sourcing regions...")
        regions = self._split_regions_from_global_baseline(global_baseline)

        self._log("Creating ALL_REGIONS...")
        regions[ALL_REGIONS] = SourcingRegion(
            name=ALL_REGIONS,
            scenarios={BASELINE_SCENARIO: global_baseline},
        )

        self._log("Creating Project Context...")
        return ProjectContext(
            plant=self.plant,
            vehicles=[v for v in self.vehicles.values()],
            tariffs_service=self.tariffs_service,
            regions=regions,
        )

    def _load_graf_data(self):
        self.direct_demand_database = self.graf_loader.load_demand_database("Direct")
        self.hub_demand_database = self.graf_loader.load_demand_database("Hub")
        self.tariffs_database = self.graf_loader.load_tariffs_database()
        self.carrier_helper = self.graf_loader.load_carrier_helper()
        self.plant_name_helper = self.graf_loader.load_plant_name_helper()
        self.vehicles_database = self.graf_loader.load_vehicles()

    def _load_helper_data(self):
        self.locations_database = self.data_loader.load_excel(
            "locations",
            "Locations",
            ["Key", "Latitude", "Longitude", "ZIP Code", "Country"],
        )

    def _transform_graf_demand_data(self):
        self.direct_demand_database = DemandDataTransformer(
            self.direct_demand_database,
            self.carrier_helper,
            self.plant_name_helper,
            self.locations_database,
        ).transform_database()

        self.hub_demand_database = DemandDataTransformer(
            self.hub_demand_database,
            self.carrier_helper,
            self.plant_name_helper,
            self.locations_database,
            is_hub_database=True,
        ).transform_database()

    def check_source_data(self):
        direct_carriers = set(self.direct_demand_database["Carrier ID"].unique())
        all_carriers = direct_carriers
        carriers_in_helper = set(self.carrier_helper["Carrier ID"].unique())
        if not all_carriers.issubset(carriers_in_helper):
            raise CarriersNotInHelperError(all_carriers.difference(carriers_in_helper))

        # TODO: Implement vehicle check to guarantee all missing vehicles get mapped.

    def _create_general_domain_objects(self) -> None:
        self.plant = PlantRepository(self.direct_demand_database).get_plant()
        self.vehicles = VehicleRepository(self.vehicles_database).extract_vehicles()

    def _create_tariffs(self) -> None:
        hub_cofors = list(self.hub_demand_database["HUB COFOR"].unique())
        transformer = TariffsTransformer(
            self.tariffs_database,
            hub_cofors=hub_cofors,
            plant_cofor=self.plant.cofor,
        )

        self.ftl_tariffs_database = transformer.get_transformed_tariffs("ftl")
        ftl_tariffs_by_key = ftl_tariffs_from_dataframe(self.ftl_tariffs_database)

        self.ltl_tariffs_database = transformer.get_transformed_tariffs("ltl")
        ltl_tariffs_by_key = ltl_tariffs_from_dataframe(self.ltl_tariffs_database)

        self.hub_tariffs_database = transformer.get_transformed_tariffs("hub")
        self.hub_tariffs_database.to_csv('hub_debug.csv')
        hub_tariffs_by_key = hub_tariffs_from_dataframe(self.hub_tariffs_database)

        self.tariffs_service = TariffService(
            ftl_mr_tariffs=ftl_tariffs_by_key,
            ltl_tariffs=ltl_tariffs_by_key,
            hub_tariffs=hub_tariffs_by_key,
        )

    def _create_hubs_global(self) -> set[Hub]:
        """
        Create all Hub domain objects from the full hub demand database, without region filtering.
        """
        aggregated_demand_by_shipper = DemandDataTransformer(
            self.hub_demand_database
        ).aggregate_database_by_shipper()

        sellers = SellerRepository(self.hub_demand_database).get_by_shipper()
        carriers = CarrierRepository(self.hub_demand_database).get_all_hub()

        hub_shippers_by_cofor = ShipperRepository(aggregated_demand_by_shipper).get_all(
            sellers_by_shipper=sellers,
            carriers=carriers["first_leg"],
            are_hub_shippers=True,
        )
        verify_coordinates(hub_shippers_by_cofor)

        hubs = HubRepository(self.hub_demand_database).get_all(
            shippers=hub_shippers_by_cofor,
            carriers=carriers,
            vehicles=self.vehicles,
            plant=self.plant,
        )

        self._assign_hub_tariffs(hubs)
        return hubs

    def _assign_with_hub_fallback(self, route) -> None:
        """
        Try normal tariff assignment first.
        If still missing, try HUB tariffs.
        Then validate.
        """
        if isinstance(route, set):
            if not route:
                return

            self.tariffs_service.assign_ltl_routes(route)

            missing_routes = {r for r in route if r.tariff_source == "Missing"}
            if missing_routes:
                self.tariffs_service.assign_hub_routes(missing_routes)

            try:
                validate_ltl_missing_tariffs(route)
            except MissingTariffsError as exc:
                self._log_missing_tariffs(exc)
            return

        if isinstance(route, LinehaulRoute):
            if route.demand.hub.linehaul_transport_concept in {"FTL", "MR"}:
                self.tariffs_service.assign_linehaul(route)
            else:
                self.tariffs_service.assign_hub_linehaul(route)

            try:
                validate_linehaul_missing_tariffs(route)
            except MissingTariffsError as exc:
                self._log_missing_tariffs(exc)
            return

        raise TypeError(f"Unsupported route type for hub fallback: {type(route)}")

    # def _assign_hub_tariffs(self, hubs: set[Hub]) -> None:
    #     for hub in hubs:
    #         self._assign_with_hub_fallback(hub.parts_first_leg_routes)
    #
    #         if hub.has_empties_flow:
    #             self._assign_with_hub_fallback(hub.empties_first_leg_routes)
    #
    #         self._assign_with_hub_fallback(hub.parts_linehaul_route)
    #
    #         if hub.has_empties_flow:
    #             self._assign_with_hub_fallback(hub.empties_linehaul_route)

    def _assign_hub_tariffs(self, hubs: set[Hub]) -> None:
        for hub in hubs:
            self._assign_with_hub_fallback(hub.parts_first_leg_routes)
            if hub.has_empties_flow:
                self._assign_with_hub_fallback(hub.empties_first_leg_routes)

            self._assign_with_hub_fallback(hub.parts_linehaul_route)
            if hub.has_empties_flow:
                self._assign_with_hub_fallback(hub.empties_linehaul_route)

    def _create_trips_global(self) -> set[Trip]:
        """
        Create all direct trips from the full direct demand database, without region filtering.
        """
        direct_sellers = SellerRepository(self.direct_demand_database).get_by_shipper()
        direct_carriers = CarrierRepository(self.direct_demand_database).get_all()

        aggregated_direct_demand_by_shipper = DemandDataTransformer(
            self.direct_demand_database
        ).aggregate_database_by_shipper()

        direct_shippers_by_cofor = ShipperRepository(
            aggregated_direct_demand_by_shipper
        ).get_all(
            carriers=direct_carriers,
            sellers_by_shipper=direct_sellers,
        )
        verify_coordinates(shippers=direct_shippers_by_cofor)

        aggregated_direct_demand_by_route = DemandDataTransformer(
            self.direct_demand_database
        ).aggregated_database_by_route()

        route_patterns_by_vehicle = RoutePatternRepository(
            aggregated_direct_demand_by_route,
            distance_function=make_haversine_cache(),
        ).get_all(
            shippers_by_cofor=direct_shippers_by_cofor,
            plant=self.plant,
        )

        verify_total_volume(
            route_patterns=[
                pattern
                for vehicle_set in route_patterns_by_vehicle.values()
                for pattern in vehicle_set
            ],
            shippers=[s for s in direct_shippers_by_cofor.values()],
        )

        direct_routes = DirectRouteRepository(
            patterns_by_vehicle=route_patterns_by_vehicle,
            vehicles=self.vehicles,
        ).get_all()

        self.tariffs_service.assign_ftl_mr_routes(direct_routes)

        try:
            validate_ftl_missing_tariffs(direct_routes)
        except MissingTariffsError as exc:
            self._log_missing_tariffs(exc)


        parts_routes = {
            route
            for route in direct_routes
            if route.demand.flow_direction == "parts"
        }
        empties_routes = {
            route
            for route in direct_routes
            if route.demand.flow_direction == "empties"
        }

        trips = TripRepository(
            aggregated_direct_demand_by_route
        ).get_all(
            parts_routes=parts_routes,
            empties_routes=empties_routes,
        )

        verify_direct_trips_match_dataframe(
            trips=trips,
            direct_demand_database=self.direct_demand_database,
        )

        return trips

    def _trip_owner_region(self, trip: Trip) -> str:
        """
        Assign a trip to exactly one sourcing region.

        Ownership rule:
        - use parts_route if present, otherwise empties_route
        - owner is the sourcing region of the route starting point
        """
        route = trip.parts_route or trip.empties_route
        if route is None:
            raise ValueError("Trip has neither parts_route nor empties_route.")

        owner = route.demand.starting_point
        region = getattr(owner, "sourcing_region", None)

        if not region:
            raise ValueError(
                f"Missing sourcing_region for trip owner starting point '{owner.cofor}'."
            )
        return region

    def _hub_owner_region(self, hub: Hub) -> str:
        """
        Assign a hub to exactly one sourcing region.

        Preferred rule:
        - use hub.sourcing_region if present

        Fallback:
        - if all hub shippers share the same sourcing region, use it

        Otherwise:
        - raise instead of silently double counting or arbitrarily assigning
        """
        explicit_region = getattr(hub, "sourcing_region", None)
        if explicit_region:
            return explicit_region

        shipper_regions = {
            getattr(shipper, "sourcing_region", None)
            for shipper in hub.shippers
        }

        if None in shipper_regions:
            raise ValueError(
                f"Hub '{hub.cofor}' has shippers with missing sourcing_region."
            )

        if not shipper_regions:
            raise ValueError(f"Hub '{hub.cofor}' has no shippers.")

        if len(shipper_regions) == 1:
            return next(iter(shipper_regions))

        raise ValueError(
            f"Hub '{hub.cofor}' spans multiple sourcing regions ({sorted(shipper_regions)}) "
            f"and has no explicit sourcing_region owner. "
            f"Set hub.sourcing_region during hub creation."
        )

    def _split_regions_from_global_baseline(
            self,
            global_baseline: Scenario,
    ) -> dict[str, SourcingRegion]:
        trips_by_region = defaultdict(set)
        hubs_by_region = defaultdict(set)

        for trip in global_baseline.trips:
            region = self._trip_owner_region(trip)
            trips_by_region[region].add(trip)

        for hub in global_baseline.hubs:
            shipper_regions = {
                s.sourcing_region
                for s in hub.shippers
                if getattr(s, "sourcing_region", None)
            }

            for region in shipper_regions:
                hubs_by_region[region].add(RegionalHubView(core_hub=hub, region=region))

        region_names = sorted(set(trips_by_region.keys()) | set(hubs_by_region.keys()))
        regions: dict[str, SourcingRegion] = {}

        for region_name in region_names:
            baseline_scenario = Scenario(
                name=BASELINE_SCENARIO,
                trips=trips_by_region[region_name],
                hubs=hubs_by_region[region_name],
                is_baseline=True,
            )
            baseline_scenario.refresh_lock_block_available_routes()

            regions[region_name] = SourcingRegion(
                name=region_name,
                scenarios={BASELINE_SCENARIO: baseline_scenario},
            )

        return regions

    def _retain_only_used_vehicles(self, trips: set[Trip]) -> None:
        used_vehicle_ids = {
            route.vehicle.id
            for trip in trips
            for route in (trip.parts_route, trip.empties_route)
            if route is not None
        }

        self.vehicles = {
            vehicle_id: vehicle
            for vehicle_id, vehicle in self.vehicles.items()
            if vehicle_id in used_vehicle_ids
        }

        self._log(f"Retained {len(self.vehicles)} vehicles used by existing routes")