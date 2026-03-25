from domain.data_structures import Vehicle
from domain.operational_route import OperationalRoute
from domain.route_pattern import RoutePattern


class VehiclePermutationService:
    def __init__(self, vehicles: set[Vehicle]):
        self.vehicles = vehicles

    def permutate(self, patterns: set[RoutePattern]) -> set[OperationalRoute]:
        return {
            OperationalRoute(pattern, vehicle)
            for vehicle in self.vehicles
            for pattern in patterns
        }