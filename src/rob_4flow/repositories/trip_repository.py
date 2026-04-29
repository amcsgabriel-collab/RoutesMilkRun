import pandas as pd

from ..domain.routes.direct_route import DirectRoute
from ..domain.trip import Trip


class TripRepository:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_all(
        self,
        parts_routes: list[DirectRoute] | set[DirectRoute],
        empties_routes: list[DirectRoute] | set[DirectRoute],
    ) -> set[Trip]:

        trips = set()

        parts_by_name = {
            route.demand.pattern.route_name: route
            for route in parts_routes
        }

        empties_by_name = {
            route.demand.pattern.route_name: route
            for route in empties_routes
        }

        roundtrip_rows = self._df[
            self._df["Roundtrip identifier"].notna()
            & (self._df["Roundtrip identifier"].astype(str).str.strip() != "")
        ]

        singletrip_rows = self._df[
            self._df["Roundtrip identifier"].isna()
            | (self._df["Roundtrip identifier"].astype(str).str.strip() == "")
        ]

        roundtrip_map: dict[str, dict[str, set[str]]] = {}

        for _, row in roundtrip_rows.iterrows():
            roundtrip_id = str(row["Roundtrip identifier"]).strip()
            route_name = row["Route name"]
            demand_type = str(row["Parts or Empties"]).strip()

            if roundtrip_id not in roundtrip_map:
                roundtrip_map[roundtrip_id] = {"P": set(), "E": set()}

            roundtrip_map[roundtrip_id][demand_type].add(route_name)

        # Validate roundtrip_id integrity in source data.
        invalid = []
        for roundtrip_id, data in roundtrip_map.items():
            if len(data["P"]) != 1 or len(data["E"]) != 1:
                invalid.append(
                    f"{roundtrip_id}: P={data['P']} E={data['E']}"
                )
        if invalid:
            raise ValueError(
                "Invalid roundtrip IDs (expected exactly 1 parts and 1 empties route):\n"
                + "\n".join(invalid)
            )

        # Actually create round trips from the map.
        for roundtrip_id, data in roundtrip_map.items():
            parts_route_name = next(iter(data["P"]))
            empties_route_name = next(iter(data["E"]))

            if parts_route_name is None:
                raise KeyError(f"Missing parts route name for roundtrip ID '{roundtrip_id}'")
            if empties_route_name is None:
                raise KeyError(f"Missing empties route name for roundtrip ID '{roundtrip_id}'")

            parts_route = parts_by_name.get(parts_route_name)
            empties_route = empties_by_name.get(empties_route_name)

            if parts_route is None:
                raise KeyError(
                    f"Parts route '{parts_route_name}' for roundtrip ID '{roundtrip_id}' was not found"
                )
            if empties_route is None:
                raise KeyError(
                    f"Empties route '{empties_route_name}' for roundtrip ID '{roundtrip_id}' was not found"
                )

            trips.add(Trip(
                parts_route=parts_route,
                empties_route=empties_route,
                frequency=max(parts_route.frequency, empties_route.frequency),
                roundtrip_id=roundtrip_id,
            ))

        for _, row in singletrip_rows.iterrows():
            route_name = row["Route name"]
            demand_type = row["Parts or Empties"]

            if demand_type == "P":
                parts_route = parts_by_name.get(route_name)
                if parts_route is None:
                    raise KeyError(f"Parts route '{route_name}' was not found")

                trips.add(Trip(
                    parts_route=parts_route,
                    empties_route=None,
                    frequency=parts_route.frequency
                ))

            elif demand_type == "E":
                empties_route = empties_by_name.get(route_name)
                if empties_route is None:
                    raise KeyError(f"Empties route '{route_name}' was not found")

                trips.add(Trip(
                    parts_route=None,
                    empties_route=empties_route,
                    frequency=empties_route.frequency
                ))

            else:
                raise ValueError(
                    f"Invalid value in 'Parts or Empties': {demand_type!r}"
                )

        return trips