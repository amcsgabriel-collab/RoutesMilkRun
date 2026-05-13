from ..domain.hub import Hub
from ..domain.regional_hub_view import HubLike
from ..domain.shipper import Shipper
from ..infrastructure.data_loader import DataLoader
from ..paths import get_helper_path


class HubAssignmentService:
    def __init__(self, plant_name: str, hubs: list[HubLike] | set[HubLike]):
        hub_cofors = {
            self._core_hub(hub).cofor
            for hub in hubs
        }

        data_loader = DataLoader(get_helper_path())
        hub_helper = data_loader.load_excel("hubs", "Data_for XPCD")

        hub_helper["PLANT"] = hub_helper["PLANT"].replace("PLIN HORDAIN", "HORDAIN")
        hub_helper = hub_helper[hub_helper["PLANT"] == plant_name]
        hub_helper = hub_helper[["HUB_ID", "country_2digit", "2-digit_ZIP"]]

        hub_helper.rename(
            columns={
                "HUB_ID": "Hub cofor",
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
        hub_helper = hub_helper.drop_duplicates()

        zip_rows = hub_helper[
            hub_helper["Hub cofor"].isin(hub_cofors)
            & (hub_helper["Zip2"] != "ALL")
        ]
        country_rows = hub_helper[
            hub_helper["Hub cofor"].isin(hub_cofors)
            & (hub_helper["Zip2"] == "ALL")
        ]

        self.hubs_by_zip_key = {
            row["Zip Key"]: row["Hub cofor"]
            for _, row in zip_rows.iterrows()
        }

        self.hubs_by_country = {
            row["Country"]: row["Hub cofor"]
            for _, row in country_rows.iterrows()
        }

    def assign_hub_cofor_to_shipper(self, shipper: Shipper) -> str | None:
        assigned_hub_cofor = getattr(shipper, "assigned_hub_cofor", None)
        if assigned_hub_cofor:
            return assigned_hub_cofor

        assigned_hub_cofor = (
            self.hubs_by_zip_key.get(shipper.zip_key(2))
            or self.hubs_by_country.get(shipper.country[:2])
        )

        if assigned_hub_cofor:
            shipper.assigned_hub_cofor = assigned_hub_cofor

        return assigned_hub_cofor

    def assign_hub_to_shipper(
        self,
        *,
        shipper: Shipper,
        hubs: list[HubLike] | set[HubLike],
    ) -> HubLike | None:
        assigned_hub_cofor = self.assign_hub_cofor_to_shipper(shipper)

        if not assigned_hub_cofor:
            return None

        hubs_by_cofor = {
            self._core_hub(hub).cofor: hub
            for hub in hubs
        }

        return hubs_by_cofor.get(assigned_hub_cofor)

    @staticmethod
    def _core_hub(hub: HubLike) -> Hub:
        return getattr(hub, "core_hub", hub)