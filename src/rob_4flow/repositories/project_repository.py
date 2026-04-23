from __future__ import annotations

import io
import json
import os
import pickle
import zipfile
from pathlib import Path
from typing import Dict, Tuple

from ..domain.project import ProjectMeta, Project


# -------------------------
# Atomic helpers (yours)
# -------------------------

def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# -------------------------
# ROB bundle format config
# -------------------------

ROB_EXTENSION = ".rob"
ROB_FORMAT_NAME = "ROB_PROJECT_BUNDLE"
ROB_SCHEMA_VERSION = 1

MANIFEST_NAME = "manifest.json"
META_NAME = "project_meta.json"
CONTEXT_NAME = "context.pkl"

INPUTS_DIR = "inputs/"
DEFAULT_GRAF_ARCNAME = "inputs/graf.xlsx"


# -------------------------
# Exceptions
# -------------------------

class RobFormatError(ValueError):
    pass


# -------------------------
# Bundle read/write
# -------------------------

def _write_rob_bundle(
    rob_path: Path,
    project_meta: dict,
    context_obj,
    input_files: Dict[str, Path],
) -> None:
    """
    Write a single .rob file (zip container).

    input_files: { "inputs/graf.xlsx": Path(...), "inputs/hubs.csv": Path(...), ... }
    """
    if rob_path.suffix.lower() != ROB_EXTENSION:
        raise RobFormatError(f"Expected '{ROB_EXTENSION}' file, got '{rob_path.suffix}'")

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        manifest = {"_format": ROB_FORMAT_NAME, "_version": ROB_SCHEMA_VERSION}
        z.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr(META_NAME, json.dumps(project_meta, ensure_ascii=False, indent=2))
        z.writestr(CONTEXT_NAME, pickle.dumps(context_obj, protocol=pickle.HIGHEST_PROTOCOL))

        for arcname, src_path in (input_files or {}).items():
            if not arcname.startswith(INPUTS_DIR):
                raise RobFormatError(f"Input archive name must start with '{INPUTS_DIR}': {arcname}")
            src_path = Path(src_path)
            if not src_path.exists():
                raise FileNotFoundError(f"Input file not found: {src_path}")
            z.write(src_path, arcname)

    _atomic_write_bytes(rob_path, mem.getvalue())


def _read_rob_bundle(rob_path: Path) -> Tuple[dict, object, Dict[str, bytes]]:
    """
    Read a .rob bundle.
    Returns (project_meta_dict, context_obj, inputs_bytes_dict)
      inputs_bytes_dict: { "inputs/graf.xlsx": b"...", ... }
    """
    if rob_path.suffix.lower() != ROB_EXTENSION:
        raise RobFormatError(f"Invalid file extension: {rob_path.suffix}")

    raw = rob_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw), mode="r") as z:
        # Validate manifest
        try:
            manifest = json.loads(z.read(MANIFEST_NAME).decode("utf-8"))
        except KeyError:
            raise RobFormatError("Missing manifest.json in .rob bundle")

        if manifest.get("_format") != ROB_FORMAT_NAME:
            raise RobFormatError("Invalid ROB bundle format (_format mismatch)")
        if manifest.get("_version") != ROB_SCHEMA_VERSION:
            raise RobFormatError(
                f"Incompatible ROB bundle version: {manifest.get('_version')} (expected {ROB_SCHEMA_VERSION})"
            )

        # Meta
        try:
            project_meta = json.loads(z.read(META_NAME).decode("utf-8"))
        except KeyError:
            raise RobFormatError("Missing project_meta.json in .rob bundle")

        # Context
        try:
            context_obj = pickle.loads(z.read(CONTEXT_NAME))
        except KeyError:
            raise RobFormatError("Missing context.pkl in .rob bundle")

        # Inputs
        inputs: Dict[str, bytes] = {}
        for name in z.namelist():
            if name.startswith(INPUTS_DIR) and not name.endswith("/"):
                inputs[name] = z.read(name)

    return project_meta, context_obj, inputs


# -------------------------
# ProjectRepository (single-file)
# -------------------------

class ProjectRepository:
    """
    Single-file storage:

      <somewhere>/my_project.rob

    Inside .rob (zip):
      manifest.json
      project_meta.json
      context.pkl
      inputs/* (optional)
    """

    # --- Public API ---

    def save_project_to_rob(self, project: Project) -> None:
        """
        Save ALL project data into a single .rob file.
        - project_meta.json: meta dict
        - context.pkl: pickled project.context
        - inputs/*: optional binaries (graf.xlsx, hubs.csv, etc.)

        By default,
          - If project.meta.graf_file_path points to a real file, it is included as inputs/graf.xlsx
          - You can extend _collect_inputs() to include other files.
        """
        rob_path = Path(project.meta.rob_file_path)
        meta_dict = self._project_meta_to_dict(project.meta)
        input_files = self._collect_inputs(project)

        if DEFAULT_GRAF_ARCNAME in input_files:
            meta_dict["graf_file_path"] = DEFAULT_GRAF_ARCNAME

        _write_rob_bundle(
            rob_path=rob_path,
            project_meta=meta_dict,
            context_obj=project.context,
            input_files=input_files,
        )
        if DEFAULT_GRAF_ARCNAME in input_files:
            project.meta.graf_file_path = DEFAULT_GRAF_ARCNAME


    def load_project_from_rob(self, rob_path: str | Path) -> Project:
        """
        Load ALL project data from a single .rob file and return Project(meta, context).

        If you need the bundled inputs on disk (e.g., to hand to Excel readers),
        call extract_inputs(...) after load.
        """
        rob_path = Path(rob_path)
        meta_dict, context, _inputs = _read_rob_bundle(rob_path)
        meta = self._project_meta_from_dict(meta_dict)
        return Project(meta=meta, context=context)

    @staticmethod
    def extract_inputs(
        rob_path: str | Path,
        output_dir: str | Path,
        overwrite: bool = False,
    ) -> Dict[str, Path]:
        """
        Optional helper: extract bundled inputs/* to a directory.
        Returns mapping { "inputs/graf.xlsx": Path("/.../graf.xlsx"), ... }.

        This is only needed if parts of your code require actual filesystem paths.
        """
        rob_path = Path(rob_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        meta_dict, context, inputs = _read_rob_bundle(rob_path)

        written: Dict[str, Path] = {}
        for arcname, data in inputs.items():
            rel = Path(arcname)
            dst = output_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and not overwrite:
                written[arcname] = dst
                continue
            _atomic_write_bytes(dst, data)
            written[arcname] = dst

        return written

    @staticmethod
    def _collect_inputs(project: Project) -> Dict[str, Path]:
        """
        Decide which external files to embed into the .rob bundle.

        Current behavior:
          - If graf_file_path exists on disk AND is not already an internal bundle path, include it.

        Extend this to include hubs.csv, vehicles.csv, locations.csv, etc. if you have them.
        """
        inputs: Dict[str, Path] = {}

        graf_path = Path(project.meta.graf_file_path) if project.meta.graf_file_path else None
        if graf_path and graf_path.exists():
            inputs[DEFAULT_GRAF_ARCNAME] = graf_path
        return inputs

    @staticmethod
    def _project_meta_to_dict(meta: "ProjectMeta") -> dict:
        return {
            "name": meta.name,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "last_saved_at": meta.last_saved_at,
            "graf_file_path": meta.graf_file_path,
            "rob_file_path": meta.rob_file_path,
            "context_file_path": meta.context_file_path,
            "current_region": meta.current_region,
            "current_scenario": meta.current_scenario,
            "schema_version": meta.schema_version,
        }

    @staticmethod
    def _project_meta_from_dict(raw: dict) -> "ProjectMeta":
        return ProjectMeta(
            name=raw["name"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            last_saved_at=raw["last_saved_at"],
            graf_file_path=raw.get("graf_file_path"),
            rob_file_path=raw.get("rob_file_path"),
            context_file_path=raw.get("context_file_path"),
            current_region=raw.get("current_region"),
            current_scenario=raw.get("current_scenario"),
            schema_version=raw.get("schema_version"),
        )