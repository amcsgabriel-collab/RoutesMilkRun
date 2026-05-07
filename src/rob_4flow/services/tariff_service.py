import math

from ..domain.routes.direct_route import DirectRoute
from ..domain.routes.first_leg_route import FirstLegRoute
from ..domain.routes.linehaul_route import LinehaulRoute
from ..domain.tariff import FtlTariff, LtlTariff, HubTariff


class TariffService:
    def __init__(
            self,
            ftl_mr_tariffs: dict[tuple[str, str, str, str, str], FtlTariff],
            ltl_tariffs: dict[tuple[str, str, str, str], LtlTariff],
            hub_tariffs: dict[tuple[str, str, str, str], HubTariff],
    ):
        self.ftl_tariffs = ftl_mr_tariffs
        self.ltl_tariffs = ltl_tariffs
        self.hub_tariffs = hub_tariffs

    def assign_route(self, route, tariffs_base: dict) -> None:
        route.tariff, route.tariff_source = self._find_tariff(
            tariffs_base=tariffs_base,
            candidate_keys=route.tariff_key_bundle,
        )

    def assign_routes(self, routes, tariffs_base: dict) -> None:
        for route in routes:
            self.assign_route(route, tariffs_base)

    def assign_ftl_mr_route(self, route: DirectRoute) -> None:
        self.assign_route(route, self.ftl_tariffs)

    def assign_ftl_mr_routes(self, routes: set[DirectRoute]) -> None:
        self.assign_routes(routes, self.ftl_tariffs)

    def assign_ltl_route(self, route: FirstLegRoute) -> None:
        self.assign_route(route, self.ltl_tariffs)

    def assign_ltl_routes(self, routes: set[FirstLegRoute]) -> None:
        self.assign_routes(routes, self.ltl_tariffs)

    def assign_hub_route(self, route: FirstLegRoute) -> None:
        self.assign_route(route, self.hub_tariffs)

    def assign_hub_routes(self, routes: set[FirstLegRoute]) -> None:
        self.assign_routes(routes, self.hub_tariffs)

    def assign_linehaul(self, route: LinehaulRoute) -> None:
        self.assign_route(route, self.ftl_tariffs)

    def assign_ltl_linehaul(self, route: LinehaulRoute) -> None:
        self.assign_route(route, self.ltl_tariffs)

    def assign_hub_linehaul(self, route: LinehaulRoute) -> None:
        self.assign_route(route, self.hub_tariffs)

    # =========================
    # Lookup helper
    # =========================
    @staticmethod
    def _find_tariff(
            tariffs_base,
            candidate_keys
    ) -> tuple | tuple[None, str]:
        for key_type, key in candidate_keys:
            if key in tariffs_base:
                source = "Zip Key" if key_type == "zip" else "COFOR"
                return tariffs_base[key], source
        return None, "Missing"

    def serialize_tariffs(
            self,
            tariff_type="ltl_hub",
            query="",
            column_filters=None,
            limit=500,
            offset=0,
    ):
        column_filters = column_filters or {}

        rows = self._serialize_tariffs_by_type(tariff_type)

        if query:
            q = query.lower()
            rows = [
                row for row in rows
                if any(q in str(value).lower() for value in row.values())
            ]

        for field, expected_value in column_filters.items():
            expected_values = {
                value.strip().lower()
                for value in str(expected_value).split(",")
                if value.strip()
            }

            rows = [
                row for row in rows
                if str(row.get(field, "")).lower() in expected_values
            ]

        total = len(rows)

        return {
            "rows": rows[offset:offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _serialize_tariffs_by_type(self, tariff_type):

        if tariff_type == "ftl_mr":
            return [
                {
                    "tariff_type": "FTL",
                    "carrier_short_name": carrier,
                    "means_of_transport": means,
                    "deviation_bucket": deviation,
                    "origin_code": origin,
                    "destination_code": destination,
                    "base_cost": clean_json_value(tariff.base_cost),
                    "roundtrip_base_cost": clean_json_value(tariff.roundtrip_base_cost),
                    "stop_cost": clean_json_value(tariff.stop_cost),
                }
                for (carrier, means, deviation, origin, destination), tariff
                in self.ftl_tariffs.items()
            ]

        if tariff_type == "ltl_hub":
            return [
                {
                    "tariff_type": "LTL",
                    "carrier_short_name": carrier,
                    "chargeable_weight_bracket": bracket,
                    "origin_code": origin,
                    "destination_code": destination,
                    "cost_per_100kg": clean_json_value(tariff.cost_per_100kg),
                    "min_price": clean_json_value(tariff.min_price),
                    "max_price": clean_json_value(tariff.max_price),
                }
                for (carrier, bracket, origin, destination), tariff
                in self.ltl_tariffs.items()
            ] + [
                {
                    "tariff_type": "HUB",
                    "carrier_short_name": carrier,
                    "chargeable_weight_bracket": bracket,
                    "origin_code": origin,
                    "destination_code": destination,
                    "cost_per_100kg": clean_json_value(tariff.cost_per_100kg),
                    "min_price": clean_json_value(tariff.min_price),
                    "max_price": clean_json_value(tariff.max_price),
                }
                for (carrier, bracket, origin, destination), tariff
                in self.hub_tariffs.items()
            ]

        raise ValueError(f"Unknown tariff_type: {tariff_type}")

    def serialize_tariff_options(self, tariff_type="ltl_hub"):
        all_rows = self._serialize_tariffs_by_type(tariff_type)

        def unique(field):
            return sorted({
                str(row.get(field))
                for row in all_rows
                if row.get(field) not in (None, "")
            })

        options = {
            "origin_code": unique("origin_code"),
            "destination_code": unique("destination_code"),
            "carrier_short_name": unique("carrier_short_name"),
        }

        if tariff_type == "ftl_mr":
            options.update({
                "means_of_transport": unique("means_of_transport"),
                "deviation_bucket": unique("deviation_bucket"),
            })

        if tariff_type == "ltl_hub":
            options.update({
                "chargeable_weight_bracket": unique("chargeable_weight_bracket"),
            })

        return options


    def upsert(self, tariff_data):
        tariff_type = tariff_data["tariff_type"]

        if tariff_type == "ftl":
            key = (
                tariff_data["carrier_short_name"],
                tariff_data["means_of_transport"],
                tariff_data["deviation_bucket"],
                tariff_data["origin_code"],
                tariff_data["destination_code"],
            )

            self.ftl_tariffs[key] = FtlTariff(
                base_cost=tariff_data["base_cost"],
                roundtrip_base_cost=tariff_data["roundtrip_base_cost"],
                stop_cost=tariff_data["stop_cost"],
            )
            return

        if tariff_type == "ltl":
            key = (
                tariff_data["carrier_short_name"],
                tariff_data["chargeable_weight_bracket"],
                tariff_data["origin_code"],
                tariff_data["destination_code"],
            )

            self.ltl_tariffs[key] = LtlTariff(
                cost_per_100kg=tariff_data["cost_per_100kg"],
                min_price=tariff_data["min_price"],
                max_price=tariff_data["max_price"],
            )
            return

        if tariff_type == "hub":
            key = (
                tariff_data["carrier_short_name"],
                tariff_data["chargeable_weight_bracket"],
                tariff_data["origin_code"],
                tariff_data["destination_code"],
            )

            self.hub_tariffs[key] = HubTariff(
                cost_per_100kg=tariff_data["cost_per_100kg"],
                min_price=tariff_data["min_price"],
                max_price=tariff_data["max_price"],
            )
            return

        raise ValueError(f"Unknown tariff_type: {tariff_type}")


def clean_json_value(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    return value