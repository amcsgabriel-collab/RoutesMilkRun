from unittest.mock import MagicMock, PropertyMock

from domain.data_structures import Plant, Vehicle
from domain.domain_algorithms import make_haversine_cache, get_deviation_bin
from domain.operational_route import OperationalRoute
from domain.route_pattern import RoutePattern
from domain.shipper import Shipper
from infrastructure.data_loader import DataLoader
from paths import get_test_path
from services.solver import Solver, MilkRunSolver, FtlSolver
from services.tariff_service import TariffService
from services.vehicle_permutation_service import VehiclePermutationService

DISTANCE_FUNCTION = make_haversine_cache()


def make_plant():
    return Plant(
        cofor="s1",
        name="test",
        country='FR',
        zip='12',
        coordinates=(0, 0)
    )


def make_seller(weight=1_000, volume=10.0, loading_meters=1.5):
    seller = MagicMock()
    seller.weight = weight
    seller.volume = volume
    seller.loading_meters = loading_meters
    return seller


def make_carrier(id="C1", name="DHL services", group="DHL"):
    carrier = MagicMock()
    carrier.id = id
    carrier.name = name
    carrier.group = group
    return carrier


def make_shipper(
        cofor="S1",
        sellers=None,
        name="Test Shipper",
        zip_code="12345",
        city="TestCity",
        street="TestStreet",
        country="DE",
        sourcing_region="EU",
        carrier=None,
        coordinates=None,
) -> Shipper:
    return Shipper(
        cofor=cofor,
        sellers=sellers or [],
        name=name,
        zip_code=zip_code,
        city=city,
        street=street,
        country=country,
        sourcing_region=sourcing_region,
        carrier=carrier,
        coordinates=coordinates,
    )


def make_fake_shipper(
        cofor="SX",
        coordinates: tuple[float, float] = (10, 0),
        total_weight: float = 1_000,
        total_loading_meters: float = 1.5,
        total_volume: float = 10.0,
        is_ftl_exclusive: bool = False,
        carrier: str = make_carrier(),
        zip_key: str = 'FR45'
):
    shipper = MagicMock()
    shipper.cofor = cofor
    shipper.coordinates = coordinates
    shipper.carrier = carrier
    shipper.zip_key = zip_key

    type(shipper).total_weight = PropertyMock(return_value=total_weight)
    type(shipper).total_loading_meters = PropertyMock(return_value=total_loading_meters)
    type(shipper).total_volume = PropertyMock(return_value=total_volume)
    type(shipper).is_ftl_exclusive_shipper = PropertyMock(return_value=is_ftl_exclusive)

    return shipper


def make_basic_pattern(shippers: list, plant: Plant) -> RoutePattern:
    return RoutePattern(set(shippers), plant)


def make_ordered_pattern(shippers: list, plant: Plant) -> RoutePattern:
    r = make_basic_pattern(shippers, plant)
    r.order_shippers(DISTANCE_FUNCTION)
    return r


def make_pattern_with_demand(
        weight=5_000,
        volume=50,
        loading_meters=6.8,
        count_of_stops=2,
        overutilization=0.05,
        carrier_short_name="CAR",
        zip_key="FR12",
        deviation_bin=get_deviation_bin(0),
):
    """Returns a mock RoutePattern with controllable property values."""
    pattern = MagicMock()

    # Scalar attributes
    pattern.count_of_stops = count_of_stops
    pattern.overutilization = overutilization
    pattern.deviation_bin = deviation_bin

    # Nested: starting_point → carrier
    pattern.starting_point.carrier.short_name = carrier_short_name
    pattern.starting_point.zip_key = zip_key

    # Properties via PropertyMock
    type(pattern).weight = PropertyMock(return_value=weight)
    type(pattern).volume = PropertyMock(return_value=volume)
    type(pattern).loading_meters = PropertyMock(return_value=loading_meters)

    return pattern


def make_vehicle(
        id="srxx",
        weight_capacity=10_000,
        volume_capacity=100,
        loading_meters_capacity=13.6,
):
    """Returns a mock Vehicle with the given capacities."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.weight_capacity = weight_capacity
    vehicle.volume_capacity = volume_capacity
    vehicle.loading_meters_capacity = loading_meters_capacity
    return vehicle

def make_tariffs():
    return {
        ('Carrier1', 'v1', get_deviation_bin(0)[0], 'FR45'): (100, 10),
        ('Carrier1', 'v1', get_deviation_bin(110)[0], 'FR45'): (100, 50),
        ('Carrier1', 'v2', get_deviation_bin(0)[0], 'FR45'): (100, 10),
        ('Carrier1', 'v2', get_deviation_bin(110)[0], 'FR45'): (100, 50),
        ('DHL', 'v1', get_deviation_bin(0)[0], 's1'): (120, 10),
        ('DHL', 'v2', get_deviation_bin(0)[0], 's1'): (150, 10),
        ('DHL', 'v1', get_deviation_bin(0)[0], 's2'): (120, 10),
        ('DHL', 'v2', get_deviation_bin(0)[0], 's2'): (150, 10),
        ('DHL', 'cheap', get_deviation_bin(0)[0], 's1'): (50, 10),
        ('DHL', 'expensive', get_deviation_bin(0)[0], 's1'): (1000, 10)
    }

def make_route(**pattern_kwargs) -> tuple:
    """Convenience: returns (route, pattern, vehicle) for assertions."""
    vehicle = make_vehicle()
    pattern = make_pattern_with_demand(**pattern_kwargs)
    route = OperationalRoute(pattern=pattern, vehicle=vehicle)
    return route, pattern, vehicle

def make_context_object():
    shipper1 = make_fake_shipper(is_ftl_exclusive=False)
    shipper2 = make_fake_shipper(is_ftl_exclusive=True)
    shipper3 = make_fake_shipper(is_ftl_exclusive=False)
    shippers = {shipper1, shipper2, shipper3}

    context = MagicMock()
    context.shippers = shippers
    context.plant = make_plant()
    context.tariffs = make_tariffs()

    return context

def make_solver():
    return Solver(
        make_context_object()
    )

def make_vehicle_permutation_service(vehicles: set[Vehicle] | None = None):
    if vehicles is None:
        vehicles = {make_vehicle()}
    return VehiclePermutationService(vehicles)

def make_tariffs_service(tariffs: dict | None = None) -> TariffService:
    if tariffs is None:
        tariffs = make_tariffs()
    return TariffService(tariffs)

def make_route_tariff_key(destination_key: str | None = None, tariff_key: tuple | None = None):
    if destination_key == "COFOR":
        tariff_key = ('DHL', 'v1', get_deviation_bin(0)[0], 'FR31', 's1')
    elif destination_key == "ZIP" or tariff_key is None:
        tariff_key = ('Carrier1', 'v1', get_deviation_bin(0)[0], 'FR45', 's2')

    route = MagicMock()
    type(route).tariff_key = PropertyMock(return_value=tariff_key)
    return route

def make_mr_solver(tariffs=None):

    if tariffs is None:
        tariffs = make_tariffs()

    c1 = make_carrier(id="c1", name="Carrier1", group="Carrier1")
    c2 = make_carrier(id="c2", name="Carrier2", group="Carrier1")

    v1 = make_vehicle(id="v1")
    v2 = make_vehicle(id="v2")

    s1 = make_fake_shipper(cofor='s1')
    s2 = make_fake_shipper(cofor='s2' ,coordinates=(10, 10))
    s3 = make_fake_shipper(cofor='s3', carrier=c1)
    s4 = make_fake_shipper(cofor='s4', coordinates=(25, 10), carrier=c2)

    blocked_patterns = {RoutePattern({s1, s2}, plant=make_plant())}
    mr_shippers = {s1, s2, s3, s4}
    vehicles = {v1, v2}

    vehicle_permutation_service = make_vehicle_permutation_service(vehicles)
    tariffs_service = make_tariffs_service(tariffs)

    return MilkRunSolver(
        mr_shippers,
        plant=make_plant(),
        blocked_patterns=blocked_patterns,
        vehicle_permutation_service=vehicle_permutation_service,
        tariffs_service=tariffs_service,
    )

def make_ftl_solver(shippers: set[Shipper] | None = None) -> FtlSolver:
    tariffs_service = make_tariffs_service()
    s1 = make_fake_shipper(cofor='s1', is_ftl_exclusive=True)
    s2 = make_fake_shipper(cofor='s2', is_ftl_exclusive=True)
    v1 = make_vehicle(id="v1")
    v2 = make_vehicle(id="v2")
    vehicle_permutation_service = make_vehicle_permutation_service({v1, v2})
    if shippers is None:
        shippers = {s1, s2}
    plant = make_plant()

    return FtlSolver(
        shippers=shippers,
        plant=plant,
        tariffs_service=tariffs_service,
        vehicle_permutation_service=vehicle_permutation_service
    )

def make_vehicles_table():
    return DataLoader(get_test_path('infrastructure')).load('vehicles')