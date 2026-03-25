from domain.hub import Hub
from domain.hub_route import HubRoute
from domain.operational_route import OperationalRoute


class TariffService:
    def __init__(self, tariffs: dict):
        self.tariffs = tariffs

    def assign_ftl(self, routes: set[OperationalRoute]) -> set[OperationalRoute]:
        for route in routes:
            tariff_key_zip = route.tariff_key()[:4]
            tariff_key_zip_3_dig = route.tariff_key(3)[:4]
            tariff_key_zip_5_dig = route.tariff_key(5)[:4]
            tariff_key_cofor = route.tariff_key()[:3] + (route.tariff_key()[4],)

            try:
                if tariff_key_zip in self.tariffs.keys():
                    route.base_cost, route.stop_cost = self.tariffs[tariff_key_zip]
                    route.tariff_source = "Zip Key"
                elif tariff_key_zip_3_dig in self.tariffs.keys():
                    route.base_cost, route.stop_cost = self.tariffs[tariff_key_zip_3_dig]
                    route.tariff_source = "Zip Key"
                elif tariff_key_zip_5_dig in self.tariffs.keys():
                    route.base_cost, route.stop_cost = self.tariffs[tariff_key_zip_5_dig]
                    route.tariff_source = "Zip Key"
                else:
                    route.base_cost, route.stop_cost = self.tariffs[tariff_key_cofor]
                    route.tariff_source = "COFOR"
            except KeyError:
                route.base_cost = 0
                route.stop_cost = 0
                route.tariff_source = "Missing"

            if route.pattern.has_over_150_km_deviation:
                route.stop_cost = route.stop_cost * route.pattern.deviation

        return routes

    def assign_ltl(self, routes: set[HubRoute]) -> set[HubRoute]:
        for route in routes:
            tariff_key_zip = route.tariff_key_ltl(2)[:4]
            tariff_key_zip_3_dig = route.tariff_key_ltl(3)[:4]
            tariff_key_zip_5_dig = route.tariff_key_ltl(5)[:4]
            tariff_key_cofor = route.tariff_key_ltl()[:3] + (route.tariff_key_ltl()[4],)
            try:
                if tariff_key_zip in self.tariffs.keys():
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_zip]
                    route.tariff_source = "LTL Zip Key"
                elif tariff_key_zip_3_dig in self.tariffs.keys():
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_zip_3_dig]
                    route.tariff_source = "LTL Zip Key"
                elif tariff_key_zip_5_dig in self.tariffs.keys():
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_zip_5_dig]
                    route.tariff_source = "LTL Zip Key"
                else:
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_cofor]
                    route.tariff_source = "LTL COFOR"
            except KeyError:
                route.cost_per_100kg, route.min_price, route.max_price = 0, 0, 0
                route.tariff_source = "Missing"
        return routes

    def assign_hub(self, routes: set[HubRoute]) -> set[HubRoute]:
        for route in routes:
            tariff_key_zip = route.tariff_key_hub(2)[:4]
            tariff_key_zip_3_dig = route.tariff_key_hub(3)[:4]
            tariff_key_zip_5_dig = route.tariff_key_hub(5)[:4]
            tariff_key_cofor = route.tariff_key_hub()[:3] + (route.tariff_key_hub()[4],)
            try:
                if tariff_key_zip in self.tariffs.keys():
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_zip]
                    route.tariff_source = "LTL Zip Key"
                elif tariff_key_zip_3_dig in self.tariffs.keys():
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_zip_3_dig]
                    route.tariff_source = "LTL Zip Key"
                elif tariff_key_zip_5_dig in self.tariffs.keys():
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_zip_5_dig]
                    route.tariff_source = "LTL Zip Key"
                else:
                    route.cost_per_100kg, route.min_price, route.max_price = self.tariffs[tariff_key_cofor]
                    route.tariff_source = "LTL COFOR"
            except KeyError:
                route.cost_per_100kg, route.min_price, route.max_price = 0, 0, 0
                route.tariff_source = "Missing"
        return routes


    def assign_linehaul(self, hub: Hub) -> None:
        tariff_key_zip = hub.tariff_key_ftl()[:4]
        tariff_key_zip_3_dig = hub.tariff_key_ftl(3)[:4]
        tariff_key_zip_5_dig = hub.tariff_key_ftl(5)[:4]
        tariff_key_cofor = hub.tariff_key_ftl()[:3] + (hub.tariff_key_ftl()[4],)
        try:
            if tariff_key_zip in self.tariffs.keys():
                hub.linehaul_base_cost = self.tariffs[tariff_key_zip][0]
                hub.linehaul_tariff_source = "Zip Key"
            elif tariff_key_zip_3_dig in self.tariffs.keys():
                hub.linehaul_base_cost = self.tariffs[tariff_key_zip_3_dig][0]
                hub.linehaul_tariff_source = "Zip Key"
            elif tariff_key_zip_5_dig in self.tariffs.keys():
                hub.linehaul_base_cost = self.tariffs[tariff_key_zip_5_dig][0]
                hub.linehaul_tariff_source = "Zip Key"
            else:
                hub.linehaul_base_cost = self.tariffs[tariff_key_cofor][0]
                hub.linehaul_tariff_source = "COFOR"
        except KeyError:
            hub.linehaul_base_cost = 0
            hub.linehaul_tariff_source = "Missing"


    def assign_ltl_linehaul(self, hub: Hub) -> None:
        tariff_key_zip = hub.tariff_key_ltl()[:4]
        tariff_key_zip_3_dig = hub.tariff_key_ltl(3)[:4]
        tariff_key_zip_5_dig = hub.tariff_key_ltl(5)[:4]
        tariff_key_cofor = hub.tariff_key_ltl()[:3] + (hub.tariff_key_ltl()[4],)

        try:
            if tariff_key_zip in self.tariffs.keys():
                hub.linehaul_cost_per_100kg, hub.linehaul_min_price, hub.linehaul_max_price = self.tariffs[tariff_key_zip]
                hub.linehaul_tariff_source = "LTL Zip Key"
            elif tariff_key_zip_3_dig in self.tariffs.keys():
                hub.linehaul_cost_per_100kg, hub.linehaul_min_price, hub.linehaul_max_price = self.tariffs[tariff_key_zip_3_dig]
                hub.linehaul_tariff_source = "LTL Zip Key"
            elif tariff_key_zip_5_dig in self.tariffs.keys():
                hub.linehaul_cost_per_100kg, hub.linehaul_min_price, hub.linehaul_max_price = self.tariffs[tariff_key_zip_5_dig]
                hub.linehaul_tariff_source = "LTL Zip Key"
            else:
                hub.linehaul_cost_per_100kg, hub.linehaul_min_price, hub.linehaul_max_price = self.tariffs[tariff_key_cofor]
                hub.linehaul_tariff_source = "LTL COFOR"
        except KeyError:
            hub.linehaul_cost_per_100kg, hub.linehaul_min_price, hub.linehaul_max_price = 0, 0, 0
            hub.linehaul_tariff_source = "Missing"
