from collections import defaultdict

import pandas as pd

from domain.hub import Hub
from domain.project import Project
from domain.routes.direct_route import DirectRoute
from domain.routes.first_leg_route import FirstLegRoute
from domain.routes.route_pattern import RoutePattern
from domain.scenario import Scenario
from domain.shipper import Shipper
from domain.trip import Trip
from infrastructure.data_loader import DataLoader
from paths import get_helper_path
from settings import DEFAULT_VEHICLE_ID


def get_cofors(shipper_list: list[Shipper] | set[Shipper] | None) -> list[str]:
    if not shipper_list:
        return []
    return [s.cofor for s in shipper_list if s]


class HubSwapService:
    def __init__(self):
        self.hub_helper: pd.DataFrame | None = None
        self.hubs_by_zip_key = None
        self.hubs_by_country = None

    @staticmethod
    def preview_swap_threshold(scenario: Scenario, thresholds: dict[str, float]) -> dict[str, list[str]]:
        current_direct_shippers = set(scenario.direct_shippers.values())
        current_hub_shippers = set(scenario.hub_shippers.values())

        direct_to_move = {s for s in current_direct_shippers if s.qualifies_for_hub(thresholds)}
        hub_to_move = {s for s in current_hub_shippers if not s.qualifies_for_hub(thresholds)}

        new_direct_shippers = current_direct_shippers - direct_to_move | hub_to_move
        new_hub_shippers = current_hub_shippers - hub_to_move | direct_to_move

        return {
            "direct": get_cofors(new_direct_shippers),
            "hub": get_cofors(new_hub_shippers),
        }

    def move_direct_shippers_to_hub(self, project: Project, cofors: list[str]) -> list[Shipper]:
        """
        Coordinates all steps of moving shippers from Direct network to Hub.
        :param project: Current Project object.
        :param cofors: List of COFORs of the shippers that will be moved.
        :return: List of shippers that couldn't be assigned to a Hub.
        """
        scenario = project.current_scenario
        direct_to_move = {scenario.direct_shippers[cofor] for cofor in cofors}
        self._prepare_hub_helper(project.plant.name, scenario.get_in_use_hubs())
        shippers_without_hub = []

        for shipper in direct_to_move:
            assigned_hub = self._assign_hub_to_shipper(shipper)
            if not assigned_hub:
                shippers_without_hub.append(shipper.short_summary)
                continue

            self.move_direct_shipper_to_hub(project, shipper, assigned_hub)
        self._normalize_direct_shipper_allocations(scenario)

        return shippers_without_hub

    def move_direct_shipper_to_hub(self, project: Project, shipper: Shipper, hub: Hub) -> None:
        """
        Moves shipper from direct network to assigned Hub.
        :param project: Current Project.
        :param shipper: Shipper to be moved.
        :param hub: Hub to which the shipper was assigned.
        """
        move_parts = shipper.has_parts_demand
        move_empties = hub.has_empties_flow and shipper.has_empties_demand

        if not move_parts and not move_empties:
            return

        self._remove_shipper_from_direct_network(
            project,
            shipper,
            remove_parts=move_parts,
            remove_empties=move_empties,
        )
        self._add_shipper_to_hub(project, shipper, hub)

    @staticmethod
    def _remove_shipper_from_direct_network(
            project: Project,
            shipper: Shipper,
            remove_parts: bool,
            remove_empties: bool,
    ) -> None:
        scenario = project.current_scenario
        current_shipper_trips = set()

        if remove_parts:
            current_shipper_trips |= set(scenario.find_shipper_trips(shipper, "parts"))

        if remove_empties:
            current_shipper_trips |= set(scenario.find_shipper_trips(shipper, "empties"))

        if not current_shipper_trips:
            return

        if not scenario.draft_trips:
            scenario.create_draft_trips()

        for trip in current_shipper_trips:
            new_parts_route = trip.parts_route
            new_empties_route = trip.empties_route

            if (
                    remove_parts
                    and trip.parts_route is not None
                    and shipper in trip.parts_route.demand.pattern.shippers
            ):
                current_pattern = trip.parts_route.demand.pattern

                if current_pattern.count_of_stops == 1:
                    new_parts_route = None
                else:
                    new_pattern = current_pattern.remove_shipper(shipper)
                    new_pattern.order_shippers()
                    new_pattern.calculate_deviation()
                    new_parts_route = DirectRoute(new_pattern, trip.parts_route.vehicle)
                    project.context.tariffs_service.assign_ftl_mr_route(new_parts_route)

            if (
                    remove_empties
                    and trip.empties_route is not None
                    and shipper in trip.empties_route.demand.pattern.shippers
            ):
                current_pattern = trip.empties_route.demand.pattern

                if current_pattern.count_of_stops == 1:
                    new_empties_route = None
                else:
                    new_pattern = current_pattern.remove_shipper(shipper)
                    new_pattern.order_shippers()
                    new_pattern.calculate_deviation()
                    new_empties_route = DirectRoute(new_pattern, trip.empties_route.vehicle)
                    project.context.tariffs_service.assign_ftl_mr_route(new_empties_route)

            scenario.draft_trips.remove(trip)

            if new_parts_route is not None or new_empties_route is not None:
                scenario.draft_trips.add(
                    Trip(
                        parts_route=new_parts_route,
                        empties_route=new_empties_route,
                        frequency=max(
                            new_parts_route.frequency if new_parts_route else 0,
                            new_empties_route.frequency if new_empties_route else 0,
                        ),
                        roundtrip_id=trip.roundtrip_id,
                    )
                )

    @staticmethod
    def _normalize_direct_shipper_allocations(scenario: Scenario) -> None:
        shipper_routes = defaultdict(list)

        for trip in scenario.get_in_use_trips():
            for flow_direction, route in (
                    ("parts", trip.parts_route),
                    ("empties", trip.empties_route),
            ):
                if route is None:
                    continue
                for shipper in route.demand.pattern.shippers:
                    shipper_routes[(shipper, flow_direction)].append(route)

        for (shipper, _flow_direction), routes in shipper_routes.items():
            total_allocation = sum(
                route.demand.pattern.shipper_allocation.get(shipper, 0.0)
                for route in routes
            )

            if total_allocation <= 0:
                continue
            if abs(total_allocation - 1.0) < 1e-9:
                continue

            for route in routes:
                current = route.demand.pattern.shipper_allocation.get(shipper, 0.0)
                route.demand.pattern.shipper_allocation[shipper] = current / total_allocation

    @staticmethod
    def _add_shipper_to_hub(project: Project, shipper: Shipper, hub) -> None:
        """
        Add shipper to the assigned Hub, creating new first leg route(s), already priced.
        :param project: Current Project.
        :param shipper: Shipper to be added to the Hub.
        :param hub: Hub or RegionalHubView to which shipper was assigned.
        """
        core_hub = getattr(hub, "core_hub", hub)

        if shipper not in core_hub.shippers:
            core_hub.shippers.append(shipper)

        if shipper.has_parts_demand:
            new_parts_first_leg = FirstLegRoute(
                shipper=shipper,
                carrier=core_hub.first_leg_carrier,
                vehicle=core_hub.first_leg_vehicle,
                hub=core_hub,
                flow_direction="parts",
            )
            project.context.tariffs_service.assign_ltl_route(new_parts_first_leg)
            core_hub.parts_first_leg_routes.add(new_parts_first_leg)

        if core_hub.has_empties_flow and shipper.has_empties_demand:
            new_empties_first_leg = FirstLegRoute(
                shipper=shipper,
                carrier=core_hub.first_leg_carrier,
                vehicle=core_hub.first_leg_vehicle,
                hub=core_hub,
                flow_direction="empties",
            )
            project.context.tariffs_service.assign_ltl_route(new_empties_first_leg)
            core_hub.empties_first_leg_routes.add(new_empties_first_leg)

    def move_hub_shippers_to_direct(self, project: Project, cofors: list[str]) -> list[str]:
        """
        Coordinates all steps of moving shippers from Hub network to Direct.
        :param project: Current Project object.
        :param cofors: List of COFORs of the shippers that will be moved.
        """
        scenario = project.current_scenario
        failed_to_move = []

        for cofor in cofors:
            shipper = scenario.hub_shippers[cofor]
            hub = scenario.find_shipper_hub(shipper)
            core_hub = self._resolve_core_hub(hub)

            ok = self._add_shipper_to_direct_network(
                project,
                shipper,
                add_empties=core_hub.has_empties_flow,
            )
            if not ok:
                failed_to_move.append(cofor)
                continue

            self._remove_shipper_from_hub(project, shipper)

        return failed_to_move

    @staticmethod
    def _remove_shipper_from_hub(project: Project, shipper: Shipper) -> None:
        """
        Removes the selected shipper from whichever Hub it belongs to in current scenario.
        Mutates the canonical hub object, not the regional view.
        """
        scenario = project.current_scenario
        hub = scenario.find_shipper_hub(shipper)
        core_hub = getattr(hub, "core_hub", hub)

        core_hub.shippers.remove(shipper)
        core_hub.parts_first_leg_routes = {
            r for r in core_hub.parts_first_leg_routes if r.shipper != shipper
        }
        core_hub.empties_first_leg_routes = {
            r for r in core_hub.empties_first_leg_routes if r.shipper != shipper
        }

    @staticmethod
    def _add_shipper_to_direct_network(
            project: Project,
            shipper: Shipper,
            add_empties: bool,
    ) -> bool:
        scenario = project.current_scenario
        if not scenario.draft_trips:
            scenario.create_draft_trips()

        parts_route = None
        empties_route = None

        if shipper.has_parts_demand:
            parts_pattern = RoutePattern({shipper}, project.plant, "parts")
            parts_pattern.order_shippers()
            parts_pattern.calculate_deviation()

            parts_route = DirectRoute(
                pattern=parts_pattern,
                vehicle=project.get_vehicle_by_id(DEFAULT_VEHICLE_ID),
            )
            project.context.tariffs_service.assign_ftl_mr_route(parts_route)

            if parts_route.tariff_source == "Missing":
                return False

        if add_empties and shipper.has_empties_demand:
            empties_pattern = RoutePattern({shipper}, project.plant, "empties")
            empties_pattern.order_shippers()
            empties_pattern.calculate_deviation()

            empties_route = DirectRoute(
                pattern=empties_pattern,
                vehicle=project.get_vehicle_by_id(DEFAULT_VEHICLE_ID),
            )
            project.context.tariffs_service.assign_ftl_mr_route(empties_route)

            if empties_route.tariff_source == "Missing":
                return False

        if parts_route is None and empties_route is None:
            return False

        scenario.draft_trips.add(
            Trip(
                parts_route=parts_route,
                empties_route=empties_route,
                frequency=max(
                    parts_route.frequency if parts_route else 0,
                    empties_route.frequency if empties_route else 0,
                ),
            )
        )
        return True

    def _prepare_hub_helper(self, plant_name: str, hubs) -> None:
        """
        Prepares the "hub helper" database, that contains RFQs that help assign hubs to shippers.
        :param plant_name: Name of the plant of the current project.
        :param hubs: Available hubs for current scenario. Can be Hub or RegionalHubView.
        """
        data_loader = DataLoader(get_helper_path())
        hub_helper = data_loader.load_excel('hubs', 'Data_for XPCD')
        hub_helper['PLANT'] = hub_helper['PLANT'].replace("PLIN HORDAIN", "HORDAIN")
        hub_helper = hub_helper[hub_helper['PLANT'] == plant_name]
        hub_helper = hub_helper[["HUB_ID", "country_2digit", "2-digit_ZIP"]]
        hub_helper.rename(columns={
            "HUB_ID": "HUB cofor",
            "country_2digit": "Zip Key",
            "2-digit_ZIP": "Zip2",
        }, inplace=True)
        hub_helper["Zip Key"] = (
            hub_helper["Zip Key"]
            .astype(str)
            .str.replace("-", "", regex=False)
            .str.strip()
        )
        hub_helper["Country"] = hub_helper["Zip Key"].str[:2]
        hub_helper = hub_helper.drop_duplicates()

        hubs_by_cofor = {
            self._resolve_core_hub(hub).cofor: self._resolve_core_hub(hub)
            for hub in hubs
        }

        self.hub_helper = hub_helper
        self.hubs_by_zip_key = self.get_hubs_by_zipkey(hubs_by_cofor)
        self.hubs_by_country = self.get_hubs_by_country(hubs_by_cofor)

    @staticmethod
    def _resolve_core_hub(hub) -> Hub:
        return getattr(hub, "core_hub", hub)

    def _assign_hub_to_shipper(self, shipper: Shipper) -> Hub:
        """
        Assigns shipper to one of currently available canonical Hubs,
        based on zip code or country, depending on RFQ rules.
        """
        hub = self.hubs_by_zip_key.get(shipper.zip_key(2)) or self.hubs_by_country.get(shipper.country[:2])
        return hub

    def get_hubs_by_zipkey(self, hubs_by_cofor: dict[str, Hub]) -> dict[str, Hub]:
        """
        Creates a "Hubs" assignment dictionary keyed by Zip code.
        :param hubs_by_cofor: Currently available hubs keyed by their COFOR.
        :return: Dictionary keyed by Zip code.
        """
        hub_helper_zip_only = self.hub_helper[
            self.hub_helper["HUB cofor"].isin(hubs_by_cofor) & (self.hub_helper["Zip2"] != "ALL")
            ]
        return {
            row["Zip Key"]: hubs_by_cofor[row["HUB cofor"]]
            for _, row in hub_helper_zip_only.iterrows()
        }

    def get_hubs_by_country(self, hubs_by_cofor: dict[str, Hub]) -> dict[str, Hub]:
        """
        Creates a "Hubs" assignment dictionary keyed by Country.
        :param hubs_by_cofor: Currently available hubs keyed by their COFOR
        :return: Dictionary keyed by Country.
        """
        hub_helper_country_only = self.hub_helper[
            self.hub_helper["HUB cofor"].isin(hubs_by_cofor) & (self.hub_helper["Zip2"] == "ALL")
            ]
        return {
            row["Country"]: hubs_by_cofor[row["HUB cofor"]]
            for _, row in hub_helper_country_only.iterrows()
        }
