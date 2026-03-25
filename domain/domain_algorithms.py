from typing import Callable

from haversine import haversine, Unit

from domain.data_structures import Plant
from domain.shipper import Shipper

ROAD_DISTANCE_CORRECTION_FACTOR = 1.3

Coordinates = tuple[float, float]

def greedy_nearest_neighbor(
        starting_point: Shipper,
        remaining: list[Shipper],
        plant:Plant,
        dist_function: Callable[[Coordinates, Coordinates], float],
) -> tuple[tuple[Shipper], tuple[float]]:

    sequence = [starting_point]
    leg_distances = []
    current = starting_point
    remaining = remaining.copy()
    while remaining:
        next_point, leg = min(
            ((p, dist_function(current.coordinates, p.coordinates)) for p in remaining),
            key=lambda x: x[1]
        )
        sequence.append(next_point)
        leg_distances.append(leg)
        remaining.remove(next_point)
        current = next_point

    # last leg to plant
    leg_distances.append(dist_function(current.coordinates, plant.coordinates))

    return sequence, leg_distances


def get_deviation_bin(deviation_km):
    if deviation_km <= 30:
        return 'Small (0-30km)', 'S'
    elif deviation_km <= 50:
        return 'Low (30-50 km)', 'L'
    elif deviation_km <= 100:
        return 'Medium (50-100km)', 'M'
    elif deviation_km <= 150:
        return 'High (100-150km)', 'H'
    else:
        return '>150km', 'VH'

def get_hub_weight_bracket(chargeable_weight):
    if chargeable_weight <= 3000:
        return '<=3000_HUB'
    elif chargeable_weight <= 5000:
        return '<=5000_HUB'
    elif chargeable_weight <= 7000:
        return '<=7000_HUB'
    elif chargeable_weight <= 10000:
        return '<=10000_HUB'
    elif chargeable_weight <= 15000:
        return '<=15000_HUB'
    elif chargeable_weight <= 20000:
        return '<=20000_HUB'
    else:
        return '>20000_HUB'

def get_ltl_weight_bracket(chargeable_weight):
    if chargeable_weight <= 200:
        return '<=200_LTL'
    elif chargeable_weight <= 600:
        return '<=600_LTL'
    elif chargeable_weight <= 1000:
        return '<=1000_LTL'
    elif chargeable_weight <= 2000:
        return '<=2000_LTL'
    elif chargeable_weight <= 4000:
        return '<=4000_LTL'
    elif chargeable_weight <= 10000:
        return '<=10000_LTL'
    elif chargeable_weight <= 15000:
        return '<=15000_LTL'
    elif chargeable_weight <= 20000:
        return '<=20000_LTL'
    elif chargeable_weight <= 25000:
        return '<=25000_LTL'
    else:
        return '>25000_LTL'


def make_haversine_cache():
    cache = {}

    def dist(a:Coordinates, b:Coordinates) -> float:
        key = (a, b) if a <= b else (b, a)
        if key not in cache:
            cache[key] = haversine(a, b, unit=Unit.KILOMETERS) * ROAD_DISTANCE_CORRECTION_FACTOR
        return cache[key]

    return dist

