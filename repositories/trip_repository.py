import pandas as pd

from domain.routes.direct_route import DirectRoute
from domain.trip import Trip


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
        print(
            roundtrip_rows[["Roundtrip identifier", "Route name", "Parts or Empties"]]
            .value_counts()
        )

        singletrip_rows = self._df[
            self._df["Roundtrip identifier"].isna()
            | (self._df["Roundtrip identifier"].astype(str).str.strip() == "")
        ]
        print(
            singletrip_rows[["Route name", "Parts or Empties", "Roundtrip identifier"]]
            .value_counts()
        )

        roundtrip_map: dict[str, dict[str, str | int | None]] = {}

        for _, row in roundtrip_rows.iterrows():
            roundtrip_id = str(row["Roundtrip identifier"]).strip()
            route_name = row["Route name"]
            demand_type = row["Parts or Empties"]

            if roundtrip_id not in roundtrip_map:
                roundtrip_map[roundtrip_id] = {
                    "P": None,
                    "E": None,
                }

            roundtrip_map[roundtrip_id][demand_type] = route_name

        for roundtrip_id, data in roundtrip_map.items():
            parts_route_name = data["P"]
            empties_route_name = data["E"]

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