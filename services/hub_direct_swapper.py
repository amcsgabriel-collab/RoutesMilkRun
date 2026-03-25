from domain.data_structures import Plant
from domain.hub import Hub
from domain.shipper import Shipper
from infrastructure.data_loader import DataLoader
from paths import get_helper_path
from services.tariff_service import TariffService


def hub_direct_swap_algorithm(
        direct_shippers: list[Shipper],
        hub_shippers: list[Shipper],
        threshold: dict[str, float],
):
    def iterate_network(shippers_set, direct_bool):
        shippers_to_move = []
        for shipper in shippers_set:
            if shipper.qualifies_for_hub(threshold) == direct_bool:
                shippers_to_move.append(shipper)
        return shippers_to_move

    direct_to_move = iterate_network(direct_shippers, True)
    hub_to_move = iterate_network(hub_shippers, False)

    return hub_to_move, direct_to_move


class HubAssigner:
    def __init__(self, 
                 hub_tariffs: dict,
                 hubs: list[Hub],
                 plant: Plant
                 ):
        self.hub_tariffs = hub_tariffs
        self.hubs = hubs
        self.plant = plant
        self.tarrifs_service = TariffService(self.hub_tariffs)
        self.hub_helper = self.prepare_hub_helper()

    def prepare_hub_helper(self):
        data_loader = DataLoader(get_helper_path())
        hub_helper = data_loader.load_excel('hubs', 'Data_for XPCD')
        hub_helper['PLANT'] = hub_helper['PLANT'].replace("PLIN HORDAIN", "HORDAIN")
        hub_helper = hub_helper[hub_helper['PLANT'] == self.plant.name]
        hub_helper = hub_helper[["HUB_ID", "country_2digit", "2-digit_ZIP"]]
        hub_helper.rename(
            columns={
                "HUB_ID": "HUB cofor",
                "country_2digit": "Zip Key",
                "2-digit_ZIP": "Zip2",
            },
            inplace=True,
        )

        hub_helper["Zip Key"] = (
            hub_helper["Zip Key"]
            .astype(str)
            .str.replace("-", "", regex=False)
            .str.strip()
        )
        hub_helper["Country"] = hub_helper["Zip Key"].str[:2]
        hub_helper.to_csv("debug_hub_helper.csv", index=False)

        return hub_helper

    def assign_hubs(
        self,
        direct_shippers: list[Shipper],
    ) -> tuple[list[Shipper], list[Shipper]]:
        
        if not direct_shippers:
            return [], []

        hubs_by_cofor = {hub.cofor: hub for hub in self.hubs}
        hubs_by_zipkey = {
            row["Zip Key"]: hubs_by_cofor[row["HUB cofor"]]
            for _, row in self.hub_helper.drop_duplicates().iterrows()
            if row["HUB cofor"] in hubs_by_cofor and row["Zip2"] != "ALL"
        }
        hubs_by_country = {
            row["Country"]: hubs_by_cofor[row["HUB cofor"]]
            for _, row in self.hub_helper.drop_duplicates().iterrows()
            if row["HUB cofor"] in hubs_by_cofor and row["Zip2"] == "ALL"
        }

        new_direct_shippers = [s.copy() for s in direct_shippers]
        shippers_without_hub = []

        for shipper in new_direct_shippers:
            hub = hubs_by_zipkey.get(shipper.zip_key(2)) or hubs_by_country.get(shipper.country[:2])
            if hub is None:
                shippers_without_hub.append(shipper)
                continue

            shipper.carrier = hub.first_leg_carrier
            hub.shippers.append(shipper)
        
        return new_direct_shippers, shippers_without_hub
            
    def manually_assign_hub(self, shipper: Shipper, hub_cofor: str):
        hub = next((h for h in self.hubs if h.cofor == hub_cofor), None)
        if hub is None:
            raise ValueError(f"Hub with cofor {hub_cofor} not found")
        
        shipper.carrier = hub.first_leg_carrier
        hub.shippers.append(shipper)

    def refresh_hubs(self):
            for hub in self.hubs:
                hub.refresh_first_leg_routes()
                hub.set_first_leg_routes_frequency()
                self.tarrifs_service.assign_ltl(hub.first_leg_routes)