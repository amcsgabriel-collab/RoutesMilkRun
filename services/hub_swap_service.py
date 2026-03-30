import pandas as pd

from domain.exceptions import CannotEditBaselineError
from domain.hub import Hub
from domain.project import Project
from domain.scenario import Scenario
from domain.shipper import Shipper
from infrastructure.data_loader import DataLoader
from paths import get_helper_path


def get_cofors(shipper_list: list[Shipper] | set[Shipper] | None) -> list[str]:
    if not shipper_list:
        return []
    return [s.cofor for s in shipper_list if s]


class HubSwapService:
    def __init__(self):
        self.hub_helper: pd.DataFrame | None= None
        self.hubs_by_zip_key = None
        self.hubs_by_country = None

    @staticmethod
    def preview_swap_threshold(scenario: Scenario, thresholds: dict[str, float]) -> dict[str, list[str]]:

        if scenario.is_baseline:
            raise CannotEditBaselineError()

        current_direct_shippers = set(scenario.direct_shippers.values())
        current_hub_shippers = set(scenario.hub_shippers.values())

        direct_to_move = {s for s in current_direct_shippers if s.qualifies_for_hub(thresholds)}
        hub_to_move = {s for s in current_hub_shippers if not s.qualifies_for_hub(thresholds)}

        new_direct_shippers = current_direct_shippers - direct_to_move | hub_to_move
        new_hub_shippers = current_hub_shippers - hub_to_move | direct_to_move

        return {
            "direct":get_cofors(new_direct_shippers),
            "hub": get_cofors(new_hub_shippers),
        }

    def move_direct_shippers_to_hub(self, project: Project, cofors: list[str]):
        scenario = project.current_scenario
        self.prepare_hub_helper(project.plant.name, scenario.get_in_use_hubs())
        direct_to_move = {scenario.direct_shippers[cofor] for cofor in cofors}
        shippers_without_hub = []
        for shipper in direct_to_move:
            assigned_hub = self.assign_hub_to_shipper(shipper)
            if assigned_hub:
                scenario.move_direct_to_hub(shipper, assigned_hub)
            else:
                shippers_without_hub.append(shipper)

    @staticmethod
    def move_hub_shippers_to_direct(project: Project, cofors: list[str]):
        scenario = project.current_scenario
        for cofor in cofors:
            scenario.move_hub_to_direct(cofor)
            shipper = scenario.direct_shippers[cofor]
            new_route = project.create_ftl_route(shipper)
            scenario.draft_routes.add(new_route)


    def prepare_hub_helper(self, plant_name: str, hubs: list[Hub]):
        data_loader = DataLoader(get_helper_path())
        hub_helper = data_loader.load_excel('hubs', 'Data_for XPCD')
        hub_helper['PLANT'] = hub_helper['PLANT'].replace("PLIN HORDAIN", "HORDAIN")
        hub_helper = hub_helper[hub_helper['PLANT'] == plant_name]
        hub_helper = hub_helper[["HUB_ID", "country_2digit", "2-digit_ZIP"]]
        # noinspection PyArgumentList
        hub_helper = hub_helper.rename(columns={
                "HUB_ID": "HUB cofor",
                "country_2digit": "Zip Key",
                "2-digit_ZIP": "Zip2",
            },
            inplace=True
        )
        hub_helper["Zip Key"] = (
            hub_helper["Zip Key"]
            .astype(str)
            .str.replace("-", "", regex=False)
            .str.strip()
        )
        hub_helper["Country"] = hub_helper["Zip Key"].str[:2]
        hubs_by_cofor = {hub.cofor: hub for hub in hubs}
        self.hub_helper = hub_helper
        self.hubs_by_zip_key = self.get_hubs_by_zipkey(hubs_by_cofor)
        self.hubs_by_country = self.get_hubs_by_country(hubs_by_cofor)

    def assign_hub_to_shipper(
            self,
            shipper: Shipper,
    ) -> tuple[list[Shipper], list[Shipper]]:
        hub = self.hubs_by_zip_key.get(shipper.zip_key(2)) or self.hubs_by_country.get(shipper.country[:2])
        return hub

    def get_hubs_by_zipkey(self, hubs_by_cofor):
        return {
            row["Zip Key"]: hubs_by_cofor[row["HUB cofor"]]
            for _, row in self.hub_helper.drop_duplicates().iterrows()
            if row["HUB cofor"] in hubs_by_cofor and row["Zip2"] != "ALL"
        }

    def get_hubs_by_country(self, hubs_by_cofor):
        return {
            row["Country"]: hubs_by_cofor[row["HUB cofor"]]
            for _, row in self.hub_helper.drop_duplicates().iterrows()
            if row["HUB cofor"] in hubs_by_cofor and row["Zip2"] == "ALL"
        }






            
