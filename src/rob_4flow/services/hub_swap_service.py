from collections import defaultdict

from ..domain.hub import Hub
from ..domain.project import Project
from ..domain.routes.direct_route import DirectRoute
from ..domain.routes.first_leg_route import FirstLegRoute
from ..domain.routes.route_pattern import RoutePattern
from ..domain.scenario import Scenario
from ..domain.shipper import Shipper
from ..domain.trip import Trip
from ..settings import DEFAULT_VEHICLE_ID


def get_cofors(shipper_list: list[Shipper] | set[Shipper] | None) -> list[str]:
    if not shipper_list:
        return []
    return [s.cofor for s in shipper_list if s]


def empty_map_changes() -> dict:
    return {
        "removed_direct_routes": [],
        "upserted_direct_routes": [],
        "upserted_hubs": [],
        "upserted_hub_shippers": [],
        "removed_hub_shippers": [],
    }


def extend_map_changes(target: dict, source: dict) -> None:
    for key, values in source.items():
        target[key].extend(values)


class HubSwapService:
    @staticmethod
    def preview_swap_threshold(scenario: Scenario, thresholds: dict[str, float]) -> dict[str, list[str]]:
        current_direct_shippers = set(scenario.direct_shippers.values())
        current_hub_shippers = set(scenario.hub_shippers.values())

        direct_to_move = {
            s for s in current_direct_shippers
            if s.current_network == "direct" and s.qualifies_for_hub(thresholds)
        }

        hub_to_move = {
            s for s in current_hub_shippers
            if s.current_network == "hub" and not s.qualifies_for_hub(thresholds)
        }

        new_direct_shippers = current_direct_shippers - direct_to_move | hub_to_move
        new_hub_shippers = current_hub_shippers - hub_to_move | direct_to_move

        return {
            "direct": get_cofors(new_direct_shippers),
            "hub": get_cofors(new_hub_shippers),
        }

    def move_direct_shippers_to_hub(self, project: Project, cofors: list[str]) -> dict:
        scenario = project.current_scenario
        scenario.create_draft_hubs()
        scenario.create_draft_trips()

        direct_to_move = {scenario.direct_shippers[cofor] for cofor in cofors}
        shippers_without_hub = []
        map_changes = empty_map_changes()

        for shipper in direct_to_move:
            assigned_hub = project.context.hub_assignment_service.assign_hub_to_shipper(
                shipper=shipper,
                hubs=scenario.get_in_use_hubs(),
            )

            if not assigned_hub:
                shippers_without_hub.append(shipper.short_summary)
                continue

            result = self.move_direct_shipper_to_hub(project, shipper, assigned_hub)

            if not result["ok"]:
                shippers_without_hub.append(shipper.short_summary)
                continue

            extend_map_changes(map_changes, result["map_changes"])

        self._normalize_direct_shipper_allocations(scenario)

        return {
            "failed": shippers_without_hub,
            "map_changes": map_changes,
        }

    def move_direct_shipper_to_hub(self, project: Project, shipper: Shipper, hub: Hub) -> dict:
        shipper.assigned_hub_cofor = hub.cofor

        move_parts = shipper.has_parts_demand
        move_empties = hub.has_empties_flow and shipper.has_empties_demand

        if not move_parts and not move_empties:
            return {
                "ok": False,
                "map_changes": empty_map_changes(),
            }

        ok = self._add_shipper_to_hub(project, shipper, hub)
        if not ok:
            return {
                "ok": False,
                "map_changes": empty_map_changes(),
            }

        direct_changes = self._remove_shipper_from_direct_network(
            project,
            shipper,
            remove_parts=move_parts,
            remove_empties=move_empties,
        )

        map_changes = empty_map_changes()
        map_changes["removed_direct_routes"].extend(direct_changes["removed_direct_routes"])
        map_changes["upserted_direct_routes"].extend(direct_changes["upserted_direct_routes"])
        map_changes["upserted_hubs"].append(self._resolve_core_hub(hub))
        map_changes["upserted_hub_shippers"].append(shipper)

        return {
            "ok": True,
            "map_changes": map_changes,
        }

    @staticmethod
    def _can_add_shipper_to_hub(project: Project, shipper: Shipper, hub) -> bool:
        core_hub = getattr(hub, "core_hub", hub)

        if shipper.has_parts_demand:
            route = FirstLegRoute(
                shipper=shipper,
                carrier=core_hub.first_leg_carrier,
                vehicle=core_hub.first_leg_vehicle,
                hub=core_hub,
                flow_direction="parts",
            )
            project.context.tariff_service.assign_ltl_route(route)

            if route.tariff_source == "Missing":
                return False

        if core_hub.has_empties_flow and shipper.has_empties_demand:
            route = FirstLegRoute(
                shipper=shipper,
                carrier=core_hub.first_leg_carrier,
                vehicle=core_hub.first_leg_vehicle,
                hub=core_hub,
                flow_direction="empties",
            )
            project.context.tariff_service.assign_ltl_route(route)

            if route.tariff_source == "Missing":
                return False

        return True

    @staticmethod
    def _remove_shipper_from_direct_network(
        project: Project,
        shipper: Shipper,
        remove_parts: bool,
        remove_empties: bool,
    ) -> dict:
        scenario = project.current_scenario
        current_shipper_trips = set()

        removed_direct_routes = []
        upserted_direct_routes = []

        if remove_parts:
            current_shipper_trips |= set(scenario.find_shipper_trips(shipper, "parts"))

        if remove_empties:
            current_shipper_trips |= set(scenario.find_shipper_trips(shipper, "empties"))

        if not current_shipper_trips:
            return {
                "removed_direct_routes": removed_direct_routes,
                "upserted_direct_routes": upserted_direct_routes,
            }

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
                removed_direct_routes.append(trip.parts_route)
                current_pattern = trip.parts_route.demand.pattern

                if current_pattern.count_of_stops == 1:
                    new_parts_route = None
                else:
                    new_pattern = current_pattern.remove_shipper(shipper)
                    new_pattern.order_shippers()
                    new_pattern.calculate_deviation()

                    new_parts_route = DirectRoute(new_pattern, trip.parts_route.vehicle)
                    project.context.tariff_service.assign_ftl_mr_route(new_parts_route)

                    upserted_direct_routes.append(new_parts_route)

            if (
                remove_empties
                and trip.empties_route is not None
                and shipper in trip.empties_route.demand.pattern.shippers
            ):
                removed_direct_routes.append(trip.empties_route)
                current_pattern = trip.empties_route.demand.pattern

                if current_pattern.count_of_stops == 1:
                    new_empties_route = None
                else:
                    new_pattern = current_pattern.remove_shipper(shipper)
                    new_pattern.order_shippers()
                    new_pattern.calculate_deviation()

                    new_empties_route = DirectRoute(new_pattern, trip.empties_route.vehicle)
                    project.context.tariff_service.assign_ftl_mr_route(new_empties_route)

                    upserted_direct_routes.append(new_empties_route)

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

        return {
            "removed_direct_routes": removed_direct_routes,
            "upserted_direct_routes": upserted_direct_routes,
        }

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
    def _add_shipper_to_hub(project: Project, shipper: Shipper, hub) -> bool:
        core_hub = getattr(hub, "core_hub", hub)

        new_parts_first_leg = None
        new_empties_first_leg = None

        if shipper.has_parts_demand:
            new_parts_first_leg = FirstLegRoute(
                shipper=shipper,
                carrier=core_hub.first_leg_carrier,
                vehicle=core_hub.first_leg_vehicle,
                hub=core_hub,
                flow_direction="parts",
            )
            project.context.tariff_service.assign_ltl_route(new_parts_first_leg)

            if new_parts_first_leg.tariff_source == "Missing":
                return False

        if core_hub.has_empties_flow and shipper.has_empties_demand:
            new_empties_first_leg = FirstLegRoute(
                shipper=shipper,
                carrier=core_hub.first_leg_carrier,
                vehicle=core_hub.first_leg_vehicle,
                hub=core_hub,
                flow_direction="empties",
            )
            project.context.tariff_service.assign_ltl_route(new_empties_first_leg)

            if new_empties_first_leg.tariff_source == "Missing":
                return False

        if shipper not in core_hub.shippers:
            core_hub.shippers.append(shipper)

        shipper.hub_carrier = core_hub.first_leg_carrier
        shipper.current_network = "hub"

        if new_parts_first_leg is not None:
            core_hub.parts_first_leg_routes.add(new_parts_first_leg)

        if new_empties_first_leg is not None:
            core_hub.empties_first_leg_routes.add(new_empties_first_leg)

        return True

    def move_hub_shippers_to_direct(self, project: Project, cofors: list[str]) -> dict:
        scenario = project.current_scenario
        scenario.create_draft_hubs()
        scenario.create_draft_trips()

        failed_to_move = []
        map_changes = empty_map_changes()

        for cofor in cofors:
            shipper = scenario.hub_shippers[cofor]
            hub = scenario.find_shipper_hub(shipper)
            core_hub = self._resolve_core_hub(hub)

            result = self._add_shipper_to_direct_network(
                project,
                shipper,
                add_empties=core_hub.has_empties_flow,
            )

            if not result["ok"]:
                failed_to_move.append(cofor)
                continue

            self._remove_shipper_from_hub(project, shipper)

            map_changes["upserted_direct_routes"].extend(result["direct_routes"])
            map_changes["upserted_hubs"].append(core_hub)
            map_changes["removed_hub_shippers"].append(shipper)

        return {
            "failed": failed_to_move,
            "map_changes": map_changes,
        }

    @staticmethod
    def _remove_shipper_from_hub(project: Project, shipper: Shipper) -> None:
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
    ) -> dict:
        scenario = project.current_scenario

        if not scenario.draft_trips:
            scenario.create_draft_trips()

        parts_route = None
        empties_route = None
        direct_routes = []

        if shipper.has_parts_demand:
            parts_pattern = RoutePattern(
                {shipper},
                project.plant,
                "parts",
                route_name=f"{shipper.cofor}#P",
            )
            parts_pattern.order_shippers()
            parts_pattern.calculate_deviation()

            parts_route = DirectRoute(
                pattern=parts_pattern,
                vehicle=project.get_vehicle_by_id(DEFAULT_VEHICLE_ID),
            )
            project.context.tariff_service.assign_ftl_mr_route(parts_route)

            if parts_route.tariff_source == "Missing":
                return {
                    "ok": False,
                    "direct_routes": [],
                }

            direct_routes.append(parts_route)

        if add_empties and shipper.has_empties_demand:
            empties_pattern = RoutePattern(
                {shipper},
                project.plant,
                "empties",
                route_name=f"{shipper.cofor}#E",
            )
            empties_pattern.order_shippers()
            empties_pattern.calculate_deviation()

            empties_route = DirectRoute(
                pattern=empties_pattern,
                vehicle=project.get_vehicle_by_id(DEFAULT_VEHICLE_ID),
            )
            project.context.tariff_service.assign_ftl_mr_route(empties_route)

            if empties_route.tariff_source == "Missing":
                return {
                    "ok": False,
                    "direct_routes": [],
                }

            direct_routes.append(empties_route)

        if parts_route is None and empties_route is None:
            return {
                "ok": False,
                "direct_routes": [],
            }

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

        shipper.current_network = "direct"

        return {
            "ok": True,
            "direct_routes": direct_routes,
        }

    @staticmethod
    def _resolve_core_hub(hub) -> Hub:
        return getattr(hub, "core_hub", hub)