from domain.data_structures import Vehicle
from domain.exceptions import MissingVehiclesInHelperFileError
from domain.routes.direct_route import DirectRoute
from domain.routes.route_pattern import RoutePattern


class DirectRouteRepository:
    def __init__(self,
                 patterns_by_vehicle: dict[str, set[RoutePattern]],
                 vehicles: dict[str, Vehicle]
                 ):
        self._patterns_by_vehicle = patterns_by_vehicle
        self._vehicles = vehicles

    def get_all(self) -> set[DirectRoute]:

        missing_vehicles = set(v for v in self._patterns_by_vehicle.keys()).difference(set(v for v in self._vehicles.keys()))
        if missing_vehicles:
            raise MissingVehiclesInHelperFileError(missing_vehicles)

        return {
            DirectRoute(
                pattern=pattern,
                vehicle=self._vehicles[vehicle_id]
            )

            for vehicle_id, patterns in self._patterns_by_vehicle.items()
            for pattern in patterns
        }