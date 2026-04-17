from domain.trip import Trip


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
    roundtrip_allocations: dict[tuple, int] | None = None,
) -> set[Trip]:
    trips = set()
    all_groups = set(selected_parts_by_group.keys()) | set(selected_empties_by_group.keys())
    roundtrip_id = 1
    singletrip_id = 1

    for group in all_groups:
        parts_remaining = {
            route: int(route.frequency)
            for route in selected_parts_by_group.get(group, [])
        }
        empties_remaining = {
            route: int(route.frequency)
            for route in selected_empties_by_group.get(group, [])
        }

        unlimited_roundtrips = roundtrip_allocations is None
        roundtrip_target = None if unlimited_roundtrips else int(roundtrip_allocations.get(group, 0))

        while True:
            available_parts = [r for r, freq in parts_remaining.items() if freq > 0]
            available_empties = [r for r, freq in empties_remaining.items() if freq > 0]

            if not available_parts or not available_empties:
                break

            if not unlimited_roundtrips and roundtrip_target <= 0:
                break

            best_pair = max(
                (
                    (parts_route, empties_route)
                    for parts_route in available_parts
                    for empties_route in available_empties
                ),
                key=lambda pair: (
                    (pair[0].total_cost - pair[0].roundtrip_total_cost)
                    + (pair[1].total_cost - pair[1].roundtrip_total_cost),
                    min(parts_remaining[pair[0]], empties_remaining[pair[1]]),
                ),
            )

            best_parts, best_empties = best_pair

            trip_freq = min(
                parts_remaining[best_parts],
                empties_remaining[best_empties],
                5,
            )

            if not unlimited_roundtrips:
                trip_freq = min(trip_freq, roundtrip_target)

            if trip_freq <= 0:
                break

            trips.add(Trip(
                parts_route=best_parts,
                empties_route=best_empties,
                frequency=trip_freq,
                roundtrip_id=roundtrip_id,
            ))

            parts_remaining[best_parts] -= trip_freq
            empties_remaining[best_empties] -= trip_freq

            if not unlimited_roundtrips:
                roundtrip_target -= trip_freq

            roundtrip_id += 1


        for route, remaining_freq in parts_remaining.items():
            for chunk in _chunk_frequency(remaining_freq, max_chunk=5):
                trips.add(Trip(
                    parts_route=route,
                    empties_route=None,
                    frequency=chunk,
                    name=singletrip_id
                ))
                singletrip_id += 1


        for route, remaining_freq in empties_remaining.items():
            for chunk in _chunk_frequency(remaining_freq, max_chunk=5):
                trips.add(Trip(
                    parts_route=None,
                    empties_route=route,
                    frequency=chunk,
                    name=singletrip_id
                ))
                singletrip_id += 1

    return trips