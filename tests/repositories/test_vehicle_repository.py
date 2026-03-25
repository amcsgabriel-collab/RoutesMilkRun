import pytest

from repositories.vehicle_repository import VehicleRepository
from tests.factories import make_vehicles_table


@pytest.fixture
def repository():
    return VehicleRepository(make_vehicles_table())

class TestVehicleRepository:

    def test_all_vehicles_created(self, repository):
        vehicles = repository.extract_vehicles()
        assert len(vehicles) == 4

    def test_other(self, repository):
        pass