from pathlib import Path
from typing import Optional, Callable

from ..domain.exceptions import NoProjectError, InvalidFileTypeError
from ..domain.project import ProjectMeta, Project
from ..repositories.project_repository import ProjectRepository
from .baseline_builder import BaselineBuilder

LogFn = Callable[[str], None]


def validate_path(path):
    if not path:
        raise ValueError("Error", "No path provided.")
    if Path(path).suffix != ".rob":
        raise InvalidFileTypeError


class ProjectService:
    project_repository = ProjectRepository()

    @staticmethod
    def create_project(graf_path: str, progress_tracker: Optional[LogFn] = None):
        def _log(msg: str):
            if progress_tracker:
                progress_tracker(msg)

        _log("Starting data preparation...")
        builder = BaselineBuilder(graf_path, progress_tracker)

        context = builder.build_context()
        _log("Data preparation concluded, creating project...")

        meta = ProjectMeta(
            graf_file_path=graf_path,
            current_region=next(iter(context.regions)),
            current_scenario='AS-IS',
        )
        return Project(meta, context)

    def load_project(self, rob_file_path: str):
        if not rob_file_path:
            raise ValueError("No rob_file_path provided.")
        return self.project_repository.load_project_from_rob(rob_file_path)

    def save_project(self, current_project: Project):
        project = self._require_project(current_project)
        self.project_repository.save_project_to_rob(project)

    def save_project_as(self, current_project: Project, rob_file_path: str):
        validate_path(rob_file_path)
        project = self._require_project(current_project)
        path = Path(rob_file_path)
        project.meta.name = path.stem
        project.meta.rob_file_path = rob_file_path
        self.save_project(project)
        return project

    @staticmethod
    def _require_project(current_project: Project) -> Project:
        if not current_project:
            raise NoProjectError()
        return current_project
