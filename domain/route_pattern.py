import copy

from domain.exceptions import DeviationNotCalculatedError
from domain.shipper import Shipper
from domain.data_structures import Plant
from domain.domain_algorithms import get_deviation_bin, greedy_nearest_neighbor


class RoutePattern:
    count_of_stops: int
    starting_point: Shipper
    sequence: tuple[Shipper]
    leg_distance: tuple[float]

    def __init__(
            self,
            shippers: set[Shipper],
            plant: Plant,
            route_name: str | None = None,
            tour: str | None = None,
            mr_overutilization_rate: float = 0.05
    ):
        self.count_of_stops = len(shippers)
        if self.count_of_stops > 4:
            raise ValueError(f'Milkrun routes cannot have more than 4 stops. Got {self.count_of_stops}')
        if self.count_of_stops == 0:
            raise ValueError(f'Passed shippers list is empty. Please verify.')
        self.shippers = frozenset(shippers)
        self.is_new_pattern = False
        self.plant = plant
        self.route_name = route_name
        self.tour = tour
        self.starting_point = None
        self.sequence = None
        self.shipper_allocation = {shipper: 1 for shipper in shippers}
        self._leg_distance = None
        self._position = None
        self.deviation = None
        self.deviation_bin = None
        self.mr_cluster = None

        self.carriers = {s.carrier.group for s in shippers}
        if len(self.carriers) > 1:
            raise ValueError('Milkrun routes cannot have more than one carrier')
        self.carrier = self.carriers.pop()

        self.transport_concept = "MR" if self.count_of_stops > 1 else "FTL"
        self.overutilization = 1.0 + (mr_overutilization_rate if self.transport_concept == "MR" else 0)

    def __eq__(self, other):
        return (isinstance(other, RoutePattern)
                and self.shippers == other.shippers
                and self.route_name == other.route_name)

    def __hash__(self):
        return hash((self.shippers, self.route_name))

    def copy(self):
        return copy.deepcopy(self)

    @property
    def shippers_key(self):
        return tuple(sorted(s.cofor for s in self.shippers))

    @property
    def weight(self):
        return sum(shipper.weight * allocation for shipper, allocation in self.shipper_allocation.items())

    @property
    def volume(self):
        return sum(shipper.volume * allocation for shipper, allocation in self.shipper_allocation.items())

    @property
    def loading_meters(self):
        return sum(shipper.loading_meters * allocation for shipper, allocation in self.shipper_allocation.items())

    @property
    def has_over_150_km_deviation(self):
        if self.deviation is None:
            raise DeviationNotCalculatedError()
        return self.deviation > 150

    def reset_allocation(self):
        for shipper in self.shipper_allocation.keys():
            self.shipper_allocation[shipper] = 1

    def order_shippers(self, distance_function):

        self.starting_point = max(
            self.shippers,
            key=lambda p: distance_function(p.coordinates, self.plant.coordinates)
        )
        remaining = [p for p in self.shippers if p != self.starting_point]

        self.sequence, leg_distances = greedy_nearest_neighbor(
            starting_point=self.starting_point,
            remaining=remaining,
            plant=self.plant,
            dist_function=distance_function
        )
        self._leg_distance = {
            shipper: leg_distances[idx]
            for idx, shipper in enumerate(self.sequence)
        }

    def calculate_deviation(self, distance_function):

        self.deviation = 0

        if self.count_of_stops > 1:
            distance_direct = distance_function(self.sequence[0].coordinates, self.plant.coordinates)
            self.deviation = round((sum(self._leg_distance.values()) - distance_direct) / (self.count_of_stops - 1), 3)

        self.deviation_bin, self.mr_cluster = get_deviation_bin(self.deviation)
