import logging
import threading
from functools import wraps
from pathlib import Path
import queue
import uuid

from flask import Flask, jsonify, request, Response, stream_with_context, redirect
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from domain.exceptions import NoProjectError, UnsavedScenarioError, NonOptimalSolutionError, ExportingBaselineError, \
    CannotEditBaselineError, InvalidFileTypeError, ShippersWithoutLocationsError
from services.project_manager import ProjectManager

# ----------------------------------------------------
# APP SETUP

HERE = Path(__file__).resolve().parent  # backend/ directory
REPO_ROOT = HERE.parent  # repository root
WEB_ROOT = (REPO_ROOT / "web").resolve()  # absolute path to repo/web

app = Flask(
    __name__,
    static_folder=str(WEB_ROOT),
    static_url_path=""
)

CORS(app)
pm_lock = threading.RLock()

# ----------------------------------------------------
# Background tasks progress logger

TASKS = {}
TASKS_LOCK = threading.Lock()


def start_background_task(function, *args):
    task_id = str(uuid.uuid4())
    log_queue = queue.Queue()

    with TASKS_LOCK:
        TASKS[task_id] = {
            "queue": log_queue,
            "done": False,
            "error": None,
        }

    def progress(message):
        log_queue.put({"event": "log", "data": str(message)})

    def worker():
        try:
            function(*args, progress_tracker=progress)
        except Exception as e:
            logger.exception("Background task %s failed", task_id)
            error_payload = {
                "type": type(e).__name__,
                "message": str(e),
                "code": getattr(e, "code", None),
            }
            with TASKS_LOCK:
                TASKS[task_id]["error"] = error_payload
        finally:
            with TASKS_LOCK:
                TASKS[task_id]["done"] = True
    threading.Thread(target=worker, daemon=True).start()
    return task_id


@app.get("/api/tasks/<task_id>/events")
def task_events(task_id):
    with TASKS_LOCK:
        task = TASKS.get(task_id)
    if task is None:
        return jsonify({"error": "unknown task"}), 404

    q = task["queue"]

    def sse_event(event_name: str, data: str) -> str:
        lines = str(data).splitlines() or [""]
        parts = [f"event: {event_name}"]
        parts.extend(f"data: {line}" for line in lines)
        return "\n".join(parts) + "\n\n"

    @stream_with_context
    def event_stream():
        while True:
            try:
                item = q.get(timeout=1.0)
                yield sse_event(item["event"], item["data"])
            except queue.Empty:
                with TASKS_LOCK:
                    done = task.get("done", False)
                    task_error = task.get("error")

                if done:
                    if task_error:
                        import json
                        yield sse_event("task_error", json.dumps(task_error))

                    yield sse_event("done", "")
                    break

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# ----------------------------------------------------
# LOGGING

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# ----------------------------------------------------
# Project Manager setup

pm = ProjectManager()


# ----------------------------------------------------
# Decorators

def with_pm_lock(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with pm_lock:
            return fn(*args, **kwargs)

    return wrapper


def json_endpoint(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        return fn(data, *args, **kwargs)

    return wrapper


def query_endpoint(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        data = request.args.to_dict()
        return fn(data, *args, **kwargs)

    return wrapper


# ----------------------------------------------------
# Helper functions & general API setup

def success(data=None, code=200):
    return jsonify({"ok": True, "data": data}), code


def error(exception, extra=None):
    return jsonify({
        "ok": False,
        "error": str(exception),
        "type": type(exception).__name__,
        **(extra or {})
    })


@app.route('/favicon.ico')
def favicon():
    return redirect('/icon.png')

@app.before_request
def log_request():
    logger.info(
        "%s %s from %s",
        request.method,
        request.path,
        request.remote_addr
    )


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    logger.warning(
        "HTTPException: %s %s -> %s (%s)",
        request.method,
        request.path,
        e.code,
        type(e).__name__,
    )
    return error(e, {"path": request.path, "method": request.method}), e.code


@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    logger.exception("Unhandled Exception on %s %s", request.method, request.path)
    return error(e, {"path": request.path, "method": request.method}), 500


@app.errorhandler(UnsavedScenarioError)
def handle_unsaved_scenario(e):
    logger.warning("Unsaved Scenario Error: %s", e)
    return error(e), 400


@app.errorhandler(NonOptimalSolutionError)
def handle_non_optimal_solution(e):
    logger.warning("Non-Optimal Solution Error: %s", e)
    return error(e, {'non_optimal': True}), 500


@app.errorhandler(ExportingBaselineError)
def handle_export_baseline(e):
    logger.warning("Exporting Baseline Error: %s", e)
    return error(e), 400


@app.errorhandler(CannotEditBaselineError)
def handle_editing_baseline(e):
    logger.warning("Can't Edit Baseline Error: %s", e)
    return error(e), 400


@app.errorhandler(NoProjectError)
def handle_no_project(e):
    logger.warning("No project defined/selected. Cannot retrieve metadata: %s", e)
    return error(e), 404

@app.errorhandler(InvalidFileTypeError)
def handle_invalid_file_type(e):
    logger.warning("Invalid file type: %s", e)
    return error(e), 400


@app.errorhandler(ShippersWithoutLocationsError)
def handle_no_coordinates_shipper(e):
    logger.warning("Coordinates not found for shippers: %s", e)
    return error(e), 404

# ----------------------------------------------------

@app.post("/api/project/create")
@json_endpoint
@with_pm_lock
def create_project(data):
    task_id = start_background_task(pm.create_project, data.get("path"))
    return success(task_id, code=201)


@app.post("/api/project/load")
@json_endpoint
@with_pm_lock
def api_load_project(data):
    pm.load_project(data.get("path"))
    return success()


@app.post("/api/project/save")
@with_pm_lock
def api_save_project():
    if not pm.project.meta.rob_file_path:
        return success({'needs_save_as': True})
    pm.save_project()
    return success(pm.project.meta.rob_file_path)


@app.post("/api/project/save_as")
@json_endpoint
def api_save_project_as(data):
    pm.save_project_as(data.get("path").strip())
    return success()


@app.get("/api/project")
def api_project():
    return success(pm.project.summary)


# ----------------------------------------------------
# Regions & Scenarios

@app.get("/api/regions")
def api_regions():
    return success(pm.project.regions_list)


@app.put("/api/region")
@json_endpoint
@with_pm_lock
def api_region_select(data):
    pm.project.set_current_region(data.get("region"))
    return success()


@app.get("/api/scenarios")
def api_scenarios():
    scenario_summaries = [scenario.summary for scenario in pm.current_region.scenarios.values()]
    return success(scenario_summaries)


@app.put("/api/scenario")
@json_endpoint
@with_pm_lock
def api_scenario_select(data):
    pm.project.set_current_scenario(data.get("scenario_name"))
    return success()


@app.post("/api/scenario/add")
@with_pm_lock
def api_scenario_add():
    pm.add_scenario()
    return success(code=201)


@app.post("/api/scenario/duplicate")
@json_endpoint
@with_pm_lock
def api_scenario_duplicate(data):
    pm.duplicate_scenario(data.get("name"))
    return success(code=201)


@app.delete("/api/scenario")
@json_endpoint
@with_pm_lock
def api_scenario_delete(data):
    pm.delete_scenario(data.get("name"))
    return success()


@app.patch("/api/scenario")
@with_pm_lock
def api_scenario_save():
    pm.current_scenario.save()
    return success()


@app.get("/api/scenario/kpis")
@with_pm_lock
def api_scenario_kpis():
    scenario_kpis = pm.get_scenario_kpis()
    return success(scenario_kpis)

# ----------------------------------------------------
# Shippers, Routes & Vehicles

@app.get("/api/shippers")
def api_shippers():
    shippers_summaries = [shipper.summary for shipper in pm.current_scenario.direct_shippers.values()]
    hub_shippers_summary = [shipper.summary for shipper in pm.current_scenario.hub_shippers.values()]
    return success(shippers_summaries + hub_shippers_summary)


@app.get("/api/routes")
def api_routes():
    trip_summaries = [trip.summary for trip in pm.current_scenario.get_in_use_trips()]
    return success(trip_summaries)

@app.get("/api/hubs")
def api_hubs():
    hubs_summaries = [hub.summary for hub in pm.current_scenario.get_in_use_hubs()]
    return success(hubs_summaries)

@app.get("/api/vehicles")
def api_vehicles():
    vehicles_summary = [vehicle.summary for vehicle in pm.project.context.vehicles]
    return success(vehicles_summary)

# ----------------------------------------------------
# Vehicles Add / Delete
@app.post("/api/vehicles")
@with_pm_lock
@json_endpoint
def api_vehicles_add(data):
    new_vehicle = data.get("new_vehicle")
    pm.project.context.vehicles.append(new_vehicle)
    return success()

@app.delete("/api/vehicles")
@with_pm_lock
@json_endpoint
def api_vehicles_delete(data):
    ids_to_delete = data
    for id in ids_to_delete:
        vehicle = pm.project.get_vehicle_by_id(id)
        pm.project.context.vehicles.remove(vehicle)

    return success()

# ----------------------------------------------------
# Map HTML

@app.get("/api/map")
def api_map():
    html = pm.get_map_html()
    return success(html)


# ----------------------------------------------------
# Solver

@app.post("/api/solve_model")
@with_pm_lock
def api_solve_model():
    pm.solve_scenario()
    return success()


# ----------------------------------------------------
# Hub / Direct swap

@app.get("/api/swap_hub/load")
def api_swap_load():
    data = pm.get_shippers_cofor_per_network()
    return success(data)


@app.post("/api/swap_hub/apply_thresholds_preview")
@json_endpoint
def api_swap_apply_thresholds(data):
    swapped = pm.preview_swap_threshold(data.get("thresholds"))
    return success(swapped)


@app.post("/api/swap_hub")
@json_endpoint
@with_pm_lock
def api_swap_hub(data):
    shippers_without_tariff = pm.move_hub_to_direct(data.get("direct_cofors_to_add")),
    shippers_without_hub = pm.move_direct_to_hub(data.get("hub_cofors_to_add"))
    pm.project.refresh_tariffs_scenario_hubs()
    return success(
        {'shippers_without_hub': shippers_without_hub,
         'shippers_without_tariff': shippers_without_tariff}
    )


@app.get("/api/swap_hub/available_hubs")
def api_swap_available_hubs():
    hubs = pm.current_scenario.get_in_use_hubs()
    hubs_summary = [hub.short_summary for hub in hubs]
    return success(hubs_summary)

@app.post("/api/swap_hub/resolve")
@json_endpoint
@with_pm_lock
def api_swap_resolve(data):
    for decision in data.get("decisions"):
        if decision.get("action") == "confirm_manual_swap":
            shipper_cofor = decision.get("shipper")
            hub_cofor = decision.get("selectedHub")
            pm.manual_move_direct_to_hub(shipper_cofor, hub_cofor)
    return success()


# ----------------------------------------------------
# Lock / Block routes

def _normalize_route_key(route_key):
    if not isinstance(route_key, list):
        raise ValueError("route_key must be a list")
    if not route_key:
        raise ValueError("route_key cannot be empty")
    if len(route_key) != len(set(route_key)):
        raise ValueError("duplicate suppliers in route_key")
    return tuple(sorted(route_key))


@app.get("/api/lock_block")
@query_endpoint
def get_lock_block_routes(data):
    mode = data.get("mode")
    current_routes = pm.get_lock_block_available_routes()
    target_routes = pm.get_locked_routes() if mode == "lock" else pm.get_blocked_routes()
    return success({
        "current_routes": current_routes,
        "target_routes": target_routes,
    })


@app.post("/api/lock_block/move")
@json_endpoint
@with_pm_lock
def move_lock_block_route(data):
    from_side = data.get("from_side")
    mode = data.get("mode")
    shippers_key = _normalize_route_key(data.get("route_key"))
    flow_direction = data.get("flow_direction")
    action_map = {
            ("left", "lock"): pm.lock_route,
            ("left", "block"): pm.block_route,
            ("right", "lock"): pm.unlock_route,
            ("right", "block"): pm.unblock_route,
        }
    action = action_map.get((from_side, mode))
    action(shippers_key, flow_direction)
    return success()


@app.get("/api/lock_block/suppliers")
@with_pm_lock
def get_lock_block_suppliers():
    suppliers = pm.current_scenario.lock_block_suppliers()
    return success(suppliers)


@app.get("/api/lock_block/vehicles")
def api_vehicles_lock_block():
    vehicles = [vehicle.id for vehicle in pm.project.context.vehicles]
    return success(vehicles)


@app.post("/api/lock_block/add_manual")
@json_endpoint
@with_pm_lock
def add_manual_route(data):
    mode = data.get("mode")
    shippers_key = _normalize_route_key(data.get("route_key"))
    vehicle_id = data.get("vehicle_id")
    if mode == "lock":
        pm.lock_route_manual(shippers_key, vehicle_id)
    elif mode == "block":
        pm.block_route_manual(shippers_key, vehicle_id)
    else:
        raise KeyError("Mode must be 'lock' or 'block'")
    return success()


# ----------------------------------------------------
# Export solutions
@app.post("/api/export_solution/validate")
def export_solution_validate():
    pm.request_export_solution()
    return success()


@app.post("/api/export_solution")
@json_endpoint
@with_pm_lock
def export_solution(data):
    pm.export_solution(data.get("path"))
    return success()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
