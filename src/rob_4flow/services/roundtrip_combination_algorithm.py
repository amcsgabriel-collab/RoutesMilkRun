from ..domain.trip import Trip


def _chunk_frequency(freq: int, max_chunk: int = 5) -> list[int]:
    chunks = []
    remaining = int(freq)
    while remaining > 0:
        chunk = min(max_chunk, remaining)
        chunks.append(chunk)
        remaining -= chunk
    return chunks


def iterate_trip_combination(
    selected_parts_by_group: dict[tuple, list],
    selected_empties_by_group: dict[tuple, list],
    pair_allocations: dict[tuple, int] | None = None,
) -> set[Trip]:
    trips = set()
    all_groups = set(selected_parts_by_group.keys()) | set(selected_empties_by_group.keys())
    roundtrip_id = 1
    singletrip_id = 1

    parts_remaining = {}
    empties_remaining = {}

    for group in all_groups:
        for route in selected_parts_by_group.get(group, []):
            parts_remaining[route] = int(route.frequency)
        for route in selected_empties_by_group.get(group, []):
            empties_remaining[route] = int(route.frequency)

    pair_allocations = pair_allocations or {}

    for (parts_route, empties_route), allocated_freq in pair_allocations.items():
        if allocated_freq <= 0:
            continue

        feasible_freq = min(
            int(allocated_freq),
            parts_remaining.get(parts_route, 0),
            empties_remaining.get(empties_route, 0),
        )

        if feasible_freq <= 0:
            continue

        for chunk in _chunk_frequency(feasible_freq, max_chunk=5):
            trips.add(Trip(
                parts_route=parts_route,
                empties_route=empties_route,
                frequency=chunk,
                roundtrip_id=roundtrip_id,
            ))
            roundtrip_id += 1

        parts_remaining[parts_route] -= feasible_freq
        empties_remaining[empties_route] -= feasible_freq

    for route, remaining_freq in parts_remaining.items():
        for chunk in _chunk_frequency(remaining_freq, max_chunk=5):
            trips.add(Trip(
                parts_route=route,
                empties_route=None,
                frequency=chunk,
                name=singletrip_id,
            ))
            singletrip_id += 1

    for route, remaining_freq in empties_remaining.items():
        for chunk in _chunk_frequency(remaining_freq, max_chunk=5):
            trips.add(Trip(
                parts_route=None,
                empties_route=route,
                frequency=chunk,
                name=singletrip_id,
            ))
            singletrip_id += 1

    return trips