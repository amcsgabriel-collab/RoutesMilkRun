from domain.data_structures import Vehicle
from domain.routes.direct_route import DirectRoute
from domain.routes.route_pattern import RoutePattern


class VehiclePermutationService:
    def __init__(self, vehicles: set[Vehicle]):
        self.vehicles = vehicles

    def permutate(self, patterns: set[RoutePattern]) -> set[DirectRoute]:
        return {
            DirectRoute(pattern, vehicle)
            for vehicle in self.vehicles
            for pattern in patterns
        }