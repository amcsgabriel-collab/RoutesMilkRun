from pathlib import Path
import sys

if getattr(sys, 'frozen', False):
    PROJECT_DIR = Path(sys._MEIPASS)
else:
    PROJECT_DIR = Path(__file__).resolve().parent

def get_local_path(*parts):
    return PROJECT_DIR.joinpath(*parts)

def get_helper_path(*parts):
    helper_dir = PROJECT_DIR / 'helper_files'
    if not helper_dir.exists():
        raise RuntimeError("helper_files directory not found")
    return helper_dir.joinpath(*parts)

def get_maps_path(*parts):
    maps_dir = PROJECT_DIR / 'exported_maps'
    if not maps_dir.exists():
        raise RuntimeError("exported_maps directory not found")
    return maps_dir.joinpath(*parts)

def get_test_path(*parts):
    tests_dir = PROJECT_DIR / 'tests'
    if not tests_dir.exists():
        raise RuntimeError("tests directory not found")
    return tests_dir.joinpath(*parts)

def get_projects_path(*parts):
    projects_dir = PROJECT_DIR / 'projects'
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir.joinpath(*parts)