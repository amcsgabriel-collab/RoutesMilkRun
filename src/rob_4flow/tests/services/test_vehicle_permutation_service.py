from factories import make_vehicle_permutation_service, make_basic_pattern, make_vehicle, make_plant
from tests.factories import make_fake_shipper


def test_all_vehicles_assigned_to_all_patterns():
    v1 = make_vehicle()
    v2 = make_vehicle(id='v2')
    vehicle_permutation_service = make_vehicle_permutation_service({v1, v2})
    patterns = {make_basic_pattern({make_fake_shipper()}, make_plant())}
    routes = vehicle_permutation_service.permutate(patterns)

    assert len(routes) == len(vehicle_permutation_service.vehicles) * len(patterns)