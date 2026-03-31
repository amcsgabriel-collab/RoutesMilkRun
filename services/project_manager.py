from typing import Optional, Callable

from domain.exceptions import CannotEditBaselineError, UnsavedScenarioError
from domain.project import Project
from domain.shipper import Shipper
from services.graf_exporter import export_graf
from services.hub_swap_service import HubSwapService
from services.kpi_exporter import KpiExporter
from services.map_generator import generate_scenario_map_html
from services.project_service import ProjectService
from services.scenario_service import ScenarioService
from services.solver import Solver

LogFn = Callable[[str], None]


class ProjectManager:
    def __init__(self):
        self.project_service = ProjectService()
        self.project: Optional[Project] = None
        self.scenario_service = ScenarioService()
        self.hub_swap_service = HubSwapService()

    @property
    def current_scenario(self):
        return self.project.current_scenario

    @property
    def current_region(self):
        return self.project.current_region

    # PROJECT INTERFACE
    def create_project(self, graf_path: str, progress_tracker: LogFn) -> Project:
        self.project = self.project_service.create_project(graf_path, progress_tracker)

    def save_project(self):
        self.project_service.save_project(self.project)

    def save_project_as(self, new_path: str):
        self.project = self.project_service.save_project_as(self.project, new_path)

    def load_project(self, path):
        self.project = self.project_service.load_project(path)

    # SCENARIO INTERFACE
    def add_scenario(self):
        self.scenario_service.add_scenario(self.project)

    def duplicate_scenario(self, scenario_name):
        self.scenario_service.duplicate_scenario(self.project, scenario_name)

    def delete_scenario(self, scenario_name):
        self.scenario_service.delete_scenario(self.project, scenario_name)

    # ROUTE LOCKING & BLOCKING INTERFACE
    def get_lock_block_available_routes(self):
        return [r.shippers_keyed_summary for r in self.current_scenario.refresh_lock_block_available_routes()]

    def get_locked_routes(self):
        return [r.shippers_keyed_summary for r in self.current_scenario.locked_routes]

    def get_blocked_routes(self):
        return [r.shippers_keyed_summary for r in self.current_scenario.blocked_routes]

    def lock_route(self, shippers_key):
        route = self.current_scenario.find_route(shippers_key)
        self.current_scenario.lock_route(route)

    def lock_route_manual(self, shippers_key, vehicle_id):
        route = self.current_scenario.find_route(shippers_key)
        if not route:
            route = self.project.create_route(shippers_key, vehicle_id)
        self.current_scenario.lock_route(route)

    def unlock_route(self, shippers_key):
        route = self.current_scenario.find_route(shippers_key)
        self.current_scenario.unlock_route(route)

    def block_route(self, shippers_key):
        route = self.current_scenario.find_route(shippers_key)
        self.current_scenario.block_route(route)

    def block_route_manual(self, shippers_key, vehicle_id):
        route = self.current_scenario.find_route(shippers_key)
        if not route:
            route = self.project.create_route(shippers_key, vehicle_id)
        self.current_scenario.block_route(route)

    def unblock_route(self, shippers_key):
        route = self.current_scenario.find_route(shippers_key)
        self.current_scenario.unblock_route(route)

    # ________________________________________________________________
    # HUB / DIRECT NETWORK SWAP INTERFACE
    def get_shippers_cofor_per_network(self):
        return {
            'baseline_direct': list(self.project.current_region.scenarios['AS-IS'].direct_shippers.keys()),
            'baseline_hub': list(self.project.current_region.scenarios['AS-IS'].hub_shippers.keys()),
            'current_direct': list(self.project.current_scenario.direct_shippers.keys()),
            'current_hub': list(self.project.current_scenario.hub_shippers.keys()),
        }

    def preview_swap_threshold(self, thresholds):
        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()
        return self.hub_swap_service.preview_swap_threshold(self.current_scenario, thresholds)

    def move_hub_to_direct(self, hub_to_move: list[str]) -> list[str]:
        """
        Moves the selected list of shippers from the Hub network to Direct
        :param hub_to_move: List of Hub shipper COFORs to move.
        """
        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()
        scenario =  self.current_scenario
        print('HUB TO DIRECT: BEFORE')
        print("direct route weight:", sum(r.weight for r in scenario.get_in_use_routes()))
        print("first leg weight:", sum(r.weight for r in scenario.first_leg_routes))
        print("linehaul weight:", sum(r.weight for r in scenario.linehaul_routes))
        print("hub shipper weight:", sum(s.weight for hub in scenario.get_in_use_hubs() for s in hub.shippers))
        failed_shippers = self.hub_swap_service.move_hub_shippers_to_direct(self.project, hub_to_move)
        print('HUB TO DIRECT: AFTER')
        print("direct route weight:", sum(r.weight for r in scenario.get_in_use_routes()))
        print("first leg weight:", sum(r.weight for r in scenario.first_leg_routes))
        print("linehaul weight:", sum(r.weight for r in scenario.linehaul_routes))
        print("hub shipper weight:", sum(s.weight for hub in scenario.get_in_use_hubs() for s in hub.shippers))

        return failed_shippers

    def move_direct_to_hub(self, direct_to_move: list[str]) -> list[str]:
        """
        Tries to move the selected list of shippers from the Direct network to Hub. In case no Hub can be assigned,
        returns the shipper to be used in the "manual hub assignment" flow.
        :param direct_to_move: List of Direct shipper COFORs to move.
        :return: List of shipper COFORs that couldn't be assigned to a Hub.
        """
        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()
        scenario = self.current_scenario
        print('DIRECT TO HUB: BEFORE')
        print("direct route weight:", sum(r.weight for r in scenario.get_in_use_routes()))
        print("first leg weight:", sum(r.weight for r in scenario.first_leg_routes))
        print("linehaul weight:", sum(r.weight for r in scenario.linehaul_routes))
        print("hub shipper weight:", sum(s.weight for hub in scenario.get_in_use_hubs() for s in hub.shippers))
        shippers_without_hub = self.hub_swap_service.move_direct_shippers_to_hub(self.project, direct_to_move)
        print('DIRECT TO HUB: AFTER')
        print("direct route weight:", sum(r.weight for r in scenario.get_in_use_routes()))
        print("first leg weight:", sum(r.weight for r in scenario.first_leg_routes))
        print("linehaul weight:", sum(r.weight for r in scenario.linehaul_routes))
        print("hub shipper weight:", sum(s.weight for hub in scenario.get_in_use_hubs() for s in hub.shippers))
        return shippers_without_hub

    def manual_move_direct_to_hub(self, direct_to_move: str, assigned_hub: str) -> None:
        """
        Moves the specified shipper from the direct network to the assigned Hub.
        :param direct_to_move: COFOR of the shipper to be moved.
        :param assigned_hub: COFOR of the hub it was assigned to.
        """
        shipper = self.project.current_scenario.direct_shippers[direct_to_move]
        hub = self.project.current_scenario.get_hub_by_cofor(assigned_hub)
        self.hub_swap_service.move_direct_shipper_to_hub(self.project, shipper, hub)


    # ________________________________________________________________
    # SOLVER
    def solve_scenario(self):
        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()

        solver = Solver(self.project)
        self.current_scenario.draft_routes = solver.run()

    # ________________________________________________________________
    # MAP
    def get_map_html(self):
        return generate_scenario_map_html(self.current_scenario)

    # ________________________________________________________________
    # KPIs & GRAF Export
    def get_scenario_kpis(self):
        return KpiExporter(self.current_scenario, self.current_region.scenarios['AS-IS']).get_kpis_template()

    def request_export_solution(self):
        if self.current_scenario.draft_routes:
            raise UnsavedScenarioError()
        return True

    def export_solution(self, filepath):
        export_graf(
            path=filepath,
            scenario_hubs=self.current_scenario.hubs,
            scenario_routes=self.current_scenario.routes,
        )
