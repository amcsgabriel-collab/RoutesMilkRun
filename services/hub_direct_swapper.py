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


def hub_assigner(
        direct_shippers: list[Shipper],
        plant: Plant,
        hubs: list[Hub],
        hub_tariffs: dict
) -> list[Shipper]:

    if not direct_shippers or len(direct_shippers) == 0:
        return []

    data_loader = DataLoader(get_helper_path())
    hub_helper = data_loader.load_excel('hubs', 'Data_for XPCD')
    hub_helper['PLANT'] = hub_helper['PLANT'].replace("PLIN HORDAIN", "HORDAIN")
    hub_helper = hub_helper[hub_helper['PLANT'] == plant.name]
    hub_helper = hub_helper[["HUB_ID", "country_2digit", "2-digit_ZIP"]]
    hub_helper.rename(columns={"HUB_ID": "HUB cofor",
                               "country_2digit": "Zip Key",
                               "2-digit_ZIP": "Zip2"},
                      inplace=True)

    hub_helper["Zip Key"] = hub_helper["Zip Key"].astype(str).str.replace("-", "", regex=False).str.strip()
    hub_helper["Country"] = hub_helper["Zip Key"].str[:2]
    hub_helper.to_csv("debug_hub_helper.csv", index=False)


    hubs_by_cofor = {hub.cofor:hub for hub in hubs}
    print(hubs_by_cofor)


    hubs_by_zipkey = {
        row["Zip Key"]: hubs_by_cofor[row["HUB cofor"]]
        for _, row in hub_helper.drop_duplicates().iterrows()
        if row["HUB cofor"] in hubs_by_cofor and row["Zip2"] != "ALL"
    }
    print(hubs_by_zipkey)

    hubs_by_country = {
        row["Country"]: hubs_by_cofor[row["HUB cofor"]]
        for _, row in hub_helper.drop_duplicates().iterrows()
        if row["HUB cofor"] in hubs_by_cofor and row["Zip2"] == "ALL"
    }
    print(hubs_by_country)

    new_direct_shippers = [s.copy() for s in direct_shippers]
    for shipper in new_direct_shippers:
        hub = hubs_by_zipkey.get(shipper.zip_key(2)) or hubs_by_country.get(shipper.country[:2])
        if hub is None:
            raise KeyError(f"No hub mapping for shipper zip_key={shipper.zip_key(2)!r}, country={shipper.country!r}")
        shipper.carrier = hub.first_leg_carrier
        hub.shippers.append(shipper)

    for hub in hubs_by_cofor.values():
        hub.refresh_first_leg_routes()
        TariffService(hub_tariffs).assign_ltl(hub.first_leg_routes)

    return new_direct_shippers
