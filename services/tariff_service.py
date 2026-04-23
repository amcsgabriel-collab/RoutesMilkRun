from domain.routes.direct_route import DirectRoute
from domain.routes.first_leg_route import FirstLegRoute
from domain.routes.linehaul_route import LinehaulRoute
from domain.tariff import FtlTariff, LtlTariff, HubTariff


class TariffService:
    def __init__(
            self,
            ftl_mr_tariffs: dict[str, FtlTariff],
            ltl_tariffs: dict[str, LtlTariff],
            hub_tariffs: dict[str, HubTariff],
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

