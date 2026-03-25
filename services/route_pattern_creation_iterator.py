from itertools import combinations

from domain.data_structures import Plant
from domain.route_pattern import RoutePattern
from domain.shipper import Shipper


def iterate_creation_of_route_patterns(
        shippers: set[Shipper],
        existing_patterns: set[RoutePattern],
        plant: Plant,
        max_stops: int = 4,
        blocked_combinations: set[RoutePattern] | None = None
) -> set[RoutePattern]:
    """
    Generate all valid RoutePatterns of size up to max_stops

    Existing patterns are reused when the shipper combination already exists,
    preserving their original route_name.

    Args:
        shippers: Set of shippers to be arranged.
        existing_patterns: Set of existing route patterns to be kept if matched.
        plant: Plant where optimization is happening.
        max_stops: Maximum route size (default = 4).
        blocked_combinations: Set of all route patterns prohibited by user.

    Returns:
        routes: Set of all valid RoutePatterns
    """
    route_id = 0
    routes = set()
    blocked_combinations = blocked_combinations or set()
    blocked_by_shippers = {pattern.shippers for pattern in blocked_combinations}
    existing_by_shippers = {pattern.shippers: pattern for pattern in existing_patterns}

    for num_points in range(1, max_stops + 1):
        for combination in combinations(shippers, num_points):

            route_key = frozenset(combination)
            if route_key in blocked_by_shippers:
                continue
            existing = existing_by_shippers.get(route_key)
            if existing:
                candidate = existing.copy()
                candidate.reset_allocation()
            else:
                candidate = RoutePattern(combination, plant)
                route_id += 1
                candidate.route_name = route_id
                candidate.is_new_pattern = True
            routes.add(candidate)

    return routes