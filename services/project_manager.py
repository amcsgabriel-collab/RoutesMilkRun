from pathlib import Path
from typing import Optional, Callable

from domain.exceptions import CannotEditBaselineError, ExportingBaselineError, UnsavedScenarioError, \
    InvalidFileTypeError, NoProjectError
from domain.operational_route import OperationalRoute
from domain.project import Project, ProjectMeta
from domain.shipper import Shipper
from repositories.project_repository import ProjectRepository
from services.graf_exporter import export_graf
from services.hub_direct_swapper import hub_assigner, hub_direct_swap_algorithm
from services.kpi_exporter import KpiExporter
from services.map_generator import plot_route_map_embedded

LogFn = Callable[[str], None]


def get_cofors(shipper_list: list[Shipper] | set[Shipper] | None) -> list[str]:
    if not shipper_list:
        return []
    return [s.cofor for s in shipper_list if s]

def validate_path(path):
    if not path:
        raise ValueError("Error", "No path provided.")
    if Path(path).suffix != ".rob":
        raise InvalidFileTypeError


class ProjectManager:
    def __init__(
            self,
            project_repository: ProjectRepository,
            data_transformer,
            solver
    ):
        self.current_map_html = None
        self.new_hub_shippers = None
        self.new_direct_shippers = None
        self.current_project: Optional[Project] = None
        self.project_repository = project_repository
        self.data_transformer = data_transformer
        self.solver = solver

    @property
    def current_region(self):
        region = self.current_project.meta.current_region
        if not region:
            raise RuntimeError("Region not set in current project.")
        return self.current_project.context.regions[region]

    @property
    def current_scenario(self):
        scenario = self.current_project.meta.current_scenario
        if not scenario:
            raise RuntimeError("Scenario not set in current project.")
        return self.current_region.scenarios[scenario]

    def create_project(self, graf_path: str, progress_tracker: Optional[LogFn] = None):
        def _log(msg: str):
            if progress_tracker:
                progress_tracker(msg)

        _log("Starting data preparation...")
        data_transformer = self.data_transformer(graf_path, progress_tracker)
        context = data_transformer.build_context()
        _log("Data preparation concluded, creating project...")
        meta = ProjectMeta(
            graf_file_path=graf_path,
            current_region=next(iter(context.regions)),
            current_scenario='AS-IS',
        )
        self.current_project = Project(meta, context)
        _log("Preparing map...")
        self.update_map_html()

    def load_project(self, rob_file_path: str):
        if not rob_file_path:
            raise ValueError("Error", "No rob_file_path provided.")
        self.current_project = self.project_repository.load_project_from_rob(rob_file_path)
        self.update_map_html()

    def save_project(self):
        project = self._require_project()
        self.project_repository.save_project_to_rob(project)

    def save_project_as(self, rob_file_path: str):
        validate_path(rob_file_path)
        project = self._require_project()
        path = Path(rob_file_path)
        project.meta.name = path.stem
        project.meta.rob_file_path = rob_file_path
        self.save_project()

    def set_current_scenario(self, scenario_name: str):
        if not scenario_name:
            raise ValueError("Scenario name is required.")
        self.current_project.meta.current_scenario = scenario_name
        self.update_map_html()

    def set_current_region(self, region: str):
        if not region:
            raise ValueError("Region cannot be None.")
        self.current_project.meta.current_region = region
        self.set_current_scenario("AS-IS")

    def add_scenario(self):
        self._create_scenario('AS-IS')

    def duplicate_scenario(self, template_scenario_name):
        if not template_scenario_name:
            raise ValueError("Scenario name is required.")
        self._create_scenario(template_scenario_name)

    def _create_scenario(self, template: str = 'AS-IS'):
        scenarios = self.current_project.context.regions[self.current_project.meta.current_region].scenarios
        new_scenario = scenarios[template].copy()
        existing_names = set(scenarios.keys())
        base_name = "new_scenario" if template == "AS-IS" else f"{template}_copy"
        new_name = self._next_name(existing_names, base_name)
        new_scenario.name = new_name
        new_scenario.is_baseline = False
        scenarios[new_name] = new_scenario
        self.set_current_scenario(new_name)

    def delete_scenario(self, scenario_name: str):
        scenarios = self.current_project.context.regions[self.current_project.meta.current_region].scenarios
        if scenarios[scenario_name].is_baseline:
            raise CannotEditBaselineError()
        scenarios.pop(scenario_name)

    def _require_project(self) -> Project:
        if not self.current_project:
            raise NoProjectError()
        return self.current_project

    def solve_scenario(self):
        if not self.current_scenario:
            raise RuntimeError("Error", "No scenario is currently open")

        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()

        solver = self.solver(self.current_project)
        self.current_scenario.draft_routes = solver.run()
        self.update_map_html()

    def save_scenario(self):
        if not self.current_scenario:
            raise RuntimeError("Error", "No scenario is currently open")
        self.current_scenario.save()

    def get_scenario_kpis(self):
        return KpiExporter(self.current_scenario, self.current_region.scenarios['AS-IS']).get_kpis_template()

    def update_map_html(self):
        self.current_map_html = plot_route_map_embedded(self.current_scenario)

    def get_hub_direct_swap_data(self):
        return {
            'baseline_direct': list(self.current_region.scenarios['AS-IS'].direct_shippers.keys()),
            'baseline_hub': list(self.current_region.scenarios['AS-IS'].hub_shippers.keys()),
            'current_direct': list(self.current_scenario.direct_shippers.keys()),
            'current_hub': list(self.current_scenario.hub_shippers.keys()),
        }

    def apply_swap_threshold_preview(self, thresholds: dict[str, float]) -> dict[str, list[str]]:
        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()

        current_direct_shippers = list(self.current_scenario.direct_shippers.values())
        current_hub_shippers = list(self.current_scenario.hub_shippers.values())

        new_direct_shippers, new_hub_shippers = hub_direct_swap_algorithm(
            current_direct_shippers, current_hub_shippers, thresholds)
        new_direct_cofors = set(get_cofors(new_direct_shippers))
        new_hub_cofors = set(get_cofors(new_hub_shippers))

        final_direct_shippers = [
                                    s for s in current_direct_shippers
                                    if s.cofor not in new_hub_cofors
                                ] + [
                                    s for s in new_direct_shippers
                                    if s.cofor not in {x.cofor for x in current_direct_shippers}
                                ]

        final_hub_shippers = [
                                 s for s in current_hub_shippers
                                 if s.cofor not in new_direct_cofors
                             ] + [
                                 s for s in new_hub_shippers
                                 if s.cofor not in {x.cofor for x in current_hub_shippers}
                             ]

        return {
            "direct": get_cofors(final_direct_shippers),
            "hub": get_cofors(final_hub_shippers),
        }

    def swap_hub_direct(self, direct_cofors_to_add, hub_cofors_to_add):
        if self.current_scenario.is_baseline:
            raise CannotEditBaselineError()

        current_direct_shippers = self.current_scenario.direct_shippers
        current_hub_shippers = self.current_scenario.hub_shippers

        prepared_new_hub_shippers = hub_assigner(
            direct_shippers=[current_direct_shippers[cofor]
                             for cofor in hub_cofors_to_add
                             if cofor in current_direct_shippers],
            plant=self.current_project.context.plant,
            hubs=self.current_scenario.hubs,
            hub_tariffs=self.current_project.context.ltl_tariffs,
        )

        prepared_new_direct_shippers = {cofor: current_hub_shippers[cofor] for cofor in direct_cofors_to_add}


        self.current_scenario.direct_shippers = {cofor: shipper
                               for cofor, shipper in current_direct_shippers.items()
                               if cofor not in hub_cofors_to_add
                               } | {cofor: current_hub_shippers[cofor] for cofor in direct_cofors_to_add}

        for hub in self.current_scenario.hubs:
            hub.shippers = [s for s in hub.shippers if s not in prepared_new_direct_shippers]

        self.current_scenario.hub_shippers = {cofor: shipper
                            for cofor, shipper in current_hub_shippers.items()
                            if cofor not in direct_cofors_to_add
                            } | {s.cofor: s for s in prepared_new_hub_shippers}
        self.update_map_html()

    def lock_block_routes(self, from_side, mode, shippers_key):
        route = self.current_scenario.find_route(shippers_key)
        action_map = {
            ("left", "lock"): lambda: self.current_scenario.lock_route(route),
            ("left", "block"): lambda: self.current_scenario.block_route(route),
            ("right", "lock"): lambda: self.current_scenario.unlock_route(route),
            ("right", "block"): lambda: self.current_scenario.unblock_route(route),
        }
        action = action_map.get((from_side, mode))
        if action is None:
            raise ValueError("Invalid 'mode' or 'from_side'")
        action()

    def manual_lock_block_routes(self, mode, shippers_key, vehicle_id):
        if len(shippers_key) != len(shippers_key.unique()):
            raise ValueError("Duplicated shippers in selected list")

        route = self.current_scenario.find_route(shippers_key)
        if not route:
            vehicle = self.current_project.context.vehicles[vehicle_id]
            pattern = self.current_project.create_pattern(shippers_key)
            route = OperationalRoute(pattern, vehicle)
        action_map = {
            "lock": self.current_scenario.lock_route(route),
            "block": self.current_scenario.block_route(route)
        }
        action_map[mode]()

    def request_export_solution(self):
        if self.current_scenario.is_baseline:
            raise ExportingBaselineError()

        if self.current_scenario.draft_routes:
            raise UnsavedScenarioError()
        return True

    def export_solution(self, filepath):
        export_graf(
            path=filepath,
            scenario_hubs=self.current_scenario.hubs,
            scenario_routes=self.current_scenario.routes,
        )

    @staticmethod
    def _next_name(existing: set[str], base: str) -> str:
        """Return base, base1, base2, ... not present in existing."""
        if base not in existing:
            return base
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"
