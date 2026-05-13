# RoutesMilkRun - Technical Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Core Components](#core-components)
5. [Complex Parts Explained](#complex-parts-explained)
6. [Important Technical Decisions](#important-technical-decisions)
7. [Data Flow](#data-flow)
8. [Key Services](#key-services)

---

## Project Overview

**RoutesMilkRun** is a desktop application for optimizing logistics routes and supply chain management. It's designed to help analyze and optimize delivery routes for milk runs (circular delivery routes) and other supply chain scenarios.

### Language Composition
- **Python**: 70.1% (Backend, domain logic, business operations)
- **JavaScript**: 20% (Frontend UI, map interactions)
- **HTML**: 7% (UI Templates)
- **CSS**: 2.9% (Styling)

### Key Purpose
The application allows users to:
- Load supply chain data from Excel files (GRAF files)
- Create and manage multiple sourcing regions and scenarios
- Optimize delivery routes using constraint solvers
- Lock/block specific routes for manual control
- Swap between hub and direct delivery modes
- Export solutions back to Excel

---

## Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  PyWebView Desktop App                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Frontend (JavaScript/HTML/CSS)              │   │
│  │  - Scenario Management UI                           │   │
│  │  - Interactive Map (Leaflet.js)                     │   │
│  │  - Route/Vehicle/Tariff Management                 │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │ REST API (HTTP)                           │
│                 │ JSON payloads                             │
│  ┌──────────────▼───────────────────────────────────────┐   │
│  │        Backend (Flask) - app.py                     │   │
│  │  - REST Endpoints                                   │   │
│  │  - Project/Scenario Management                      │   │
│  │  - Background Task Management (SSE streams)         │   │
│  │  - Error Handling & Decorators                      │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
├─────────────────┼────────────────────────────────────────────┤
│ Backend Domain Layer                                         │
│  - ProjectManager (Coordination)                             │
│  - Project/Scenario (Domain Models)                          │
│  - Services (Tariffs, Hub Assignment, Solver)                │
│  - Repositories (Data persistence layer)                     │
└─────────────────────────────────────────────────────────────┘
```

### Three-Layer Architecture

```
PRESENTATION LAYER (PyWebView + Flask Static Files)
    ↓
BUSINESS LOGIC LAYER (Flask Endpoints + Services)
    ↓
DOMAIN/DATA LAYER (Project Models, Scenarios, Routes)
```

---

## Technology Stack

### Backend
- **Flask** - Web framework for REST API
- **Flask-CORS** - Cross-origin resource sharing
- **PyWebView** - Desktop application wrapper
- **PuLP** - Linear programming solver (optimization)
- **Pandas** - Data processing and Excel I/O
- **Haversine** - Geographic distance calculations
- **NumPy** - Numerical computations
- **Openpyxl/Pyxlsb/XlsxWriter** - Excel file handling

### Frontend
- **Leaflet.js** - Interactive map library (3rd party)
- **Vanilla JavaScript** - No heavy framework dependencies
- **Folium** - Map visualization generation (Python)

### Configuration
- **pyproject.toml** - Python package configuration (setuptools)

---

## Core Components

### 1. **Project Structure**

```
src/rob_4flow/
├── backend/
│   └── app.py                 # Flask application, all endpoints
├── domain/
│   ├── project.py             # Core Project/Scenario/Region models
│   ├── scenario.py            # Scenario state management
│   ├── data_structures.py     # Plant, Vehicle, Shipper models
│   ├── exceptions.py          # Custom exceptions
│   └── routes/                # Route-related domain objects
│       ├── direct_route.py    # Direct delivery routes
│       ├── route_pattern.py   # Route patterns/templates
│       ├── first_leg_route.py # Hub first-leg routes
│       └── linehaul_route.py  # Linehaul routes
├── services/
│   ├── project_manager.py     # Central coordinator
│   ├── project_service.py     # Project CRUD operations
│   ├── scenario_service.py    # Scenario management
│   ├── tariff_service.py      # Pricing logic
│   ├── hub_swap_service.py    # Hub/Direct swapping
│   ├── map_generator.py       # Map visualization generation
│   ├── solver/
│   │   └── coordinator.py     # Optimization solver orchestration
│   └── kpi_exporter.py        # KPI calculation & export
├── repositories/
│   ├── tariffs_repository.py  # Tariff data access
│   ├── trip_repository.py     # Trip data access
│   ├── vehicle_repository.py  # Vehicle data access
│   └── ...                    # Other repositories
├── infrastructure/
│   ├── graf_loader.py         # Excel data loading
│   ├── data_loader.py         # Generic data loading
│   └── tariffs_transformer.py # Tariff data transformation
├── web/
│   ├── js/
│   │   ├── api.js             # API request handler
│   │   ├── app.js             # Main app initialization
│   │   ├── map/               # Map-related JavaScript
│   │   │   ├── map.js         # Main map class
│   │   │   ├── render.js      # Rendering logic
│   │   │   ├── features.js    # Map features
│   │   │   └── ...
│   │   └── views/             # Page views
│   │       └── project/
│   │           ├── project.js # Project view
│   │           └── scenario.js # Scenario view
│   └── html/                  # HTML templates
├── pywebview_main.py          # Desktop app entry point
└── paths.py                   # Path utilities

```

### 2. **Key Domain Models**

#### **Project** (`domain/project.py`)
- **Purpose**: Root aggregate holding entire project state
- **Components**:
  - `ProjectMeta`: Metadata (name, dates, current selections, file paths)
  - `ProjectContext`: Shared data (plant, vehicles, services)
  - `SourcingRegion`: Geographic/logical region with multiple scenarios

```python
Project
├── meta: ProjectMeta (file paths, current selections)
├── context: ProjectContext
    ├── plant: Plant (origin/warehouse)
    ├── vehicles: List[Vehicle] (fleet)
    ├── tariff_service: TariffService
    ├── hub_assignment_service: HubAssignmentService
    └── regions: Dict[str, SourcingRegion]
        └── scenarios: Dict[str, Scenario]
```

#### **Scenario** (`domain/scenario.py`)
- **Purpose**: Represents a specific routing scenario (AS-IS baseline or optimized variants)
- **Complex Aspects**:
  - **Draft System**: Scenarios support draft trips/hubs for tentative changes
  - **Lock/Block System**: Routes can be locked (must use) or blocked (cannot use)
  - **Two Flow Directions**: Parts (outbound) and Empties (return flows)

```python
Scenario
├── trips: Set[Trip] (active routes)
├── draft_trips: Set[Trip] | None (tentative changes)
├── hubs: Set[Hub] (consolidation points)
├── draft_hubs: Set[Hub] | None
├── locked_routes: List[Route] (user-locked routes)
├── blocked_routes: List[Route] (user-blocked routes)
└── lock_block_available_routes: List[Route] (available for lock/block)
```

#### **Route Models** (Hierarchy)
```
Route (Abstract)
├── DirectRoute (Shipper → Warehouse, no consolidation)
├── FirstLegRoute (Shipper → Hub)
└── LinehaulRoute (Hub → Hub, Hub → Warehouse)
```

Each route has:
- `Demand` (volume, weight, loading meters)
- `Pattern` (route specification)
- Vehicle assignment
- Lock/block status

### 3. **ProjectManager** (`services/project_manager.py`)
- **Role**: Central coordinator between frontend and domain layer
- **Responsibilities**:
  - Orchestrates project load/save/create
  - Manages scenario operations
  - Coordinates route locking/blocking
  - Executes solver operations
  - Exports solutions

```python
ProjectManager
├── project_service: ProjectService
├── scenario_service: ScenarioService
├── hub_swap_service: HubSwapService
└── project: Project (current project state)
```

---

## Complex Parts Explained

### 1. **Draft System (Optimistic Editing)**

**Problem**: Users want to experiment with changes without immediately modifying the baseline.

**Solution**: Two-level state in Scenario:
```python
class Scenario:
    trips: set[Trip]          # Baseline/committed state
    draft_trips: set[Trip]    # Tentative changes
    
    def get_in_use_trips(self):
        return self.draft_trips or self.trips  # Draft takes precedence
```

**Usage**:
- When solver optimizes: Creates draft_trips with new routes
- User can "Save" (commit draft) or "Discard" (revert to baseline)
- Maps/reports use `get_in_use_trips()` to show current view

### 2. **Lock/Block System**

**Problem**: Some routes are operationally constrained. Users need to:
- **Lock**: Force optimizer to use specific routes
- **Block**: Prevent optimizer from using specific routes

**Implementation**:
```python
class Scenario:
    locked_routes: List[Route]    # Solver MUST use
    blocked_routes: List[Route]   # Solver CANNOT use
    lock_block_available_routes: List[Route]  # Available for changes
    
    def refresh_lock_block_available_routes(self):
        # Routes not already locked/blocked
        direct_routes = [r for r in trips if r not in locked/blocked]
        hub_routes = [r for r in hubs if r not in locked/blocked]
        return direct_routes + hub_routes
```

**API Example** (`app.py`):
```python
@app.post("/api/lock_block/move")
def move_lock_block_route(data):
    action_map = {
        ("left", "lock"): pm.lock_route,
        ("left", "block"): pm.block_route,
        ("right", "lock"): pm.unlock_route,
        ("right", "block"): pm.unblock_route,
    }
    action = action_map.get((from_side, mode))
    route = action(shippers_key, flow_direction)
```

### 3. **Background Task Management (SSE Streaming)**

**Problem**: Long-running operations (solver, project creation) would block the UI.

**Solution**: Server-Sent Events (SSE) streaming with progress updates

```python
# app.py
TASKS = {}  # Global task registry

def start_background_task(function, *args):
    task_id = uuid.uuid4()
    log_queue = queue.Queue()
    
    def worker():
        try:
            function(*args, progress_tracker=progress)  # Custom logger
        except Exception as e:
            TASKS[task_id]["error"] = error_payload
        finally:
            TASKS[task_id]["done"] = True
    
    thread = Thread(target=worker, daemon=True)
    thread.start()
    return task_id

@app.get("/api/tasks/<task_id>/events")
def task_events(task_id):
    @stream_with_context
    def event_stream():
        while True:
            item = queue.get(timeout=1.0)
            yield sse_event(item["event"], item["data"])
    return Response(event_stream(), mimetype="text/event-stream")
```

**Frontend Usage**:
```javascript
const res = await apiPost("/api/project/create", {path});  // Returns task_id
const eventSource = new EventSource(`/api/tasks/${res}/events`);
eventSource.onmessage = (e) => { /* progress */ };
eventSource.addEventListener("done", () => { /* complete */ });
```

### 4. **Map Rendering Pipeline**

**Problem**: Converting complex route/hub data into interactive Leaflet map.

**Solution**: Three-tier rendering system

```python
# services/map_generator.py

def build_scenario_map_full_payload(scenario):
    """Full render: Plant + all routes + hubs + shippers"""
    features = []
    
    # 1. Direct routes as line features
    for route in scenario.get_in_use_trips():
        features.extend(_direct_route_features(route))
    
    # 2. Hub circle features
    for hub in scenario.get_in_use_hubs():
        features.extend(_hub_features(hub))
    
    # 3. Shipper points (assigned to routes/hubs or unassigned)
    for shipper in scenario.shippers.values():
        if not is_assigned(shipper):
            features.append(_shipper_feature(shipper))
    
    return {
        "version": 1,
        "features": features,
        "bounds": calculate_bounds(),
        "uiState": {...}
    }

def build_scenario_map_patch(changes):
    """Incremental update: Only changed features"""
    return {
        "ops": [
            {"op": "upsertFeatures", "features": changes["new_routes"]},
            {"op": "removeFeatures", "ids": changes["deleted_routes"]},
            {"op": "patchFeature", "id": "hub_1", "changes": {...}},
        ],
        "bounds": new_bounds
    }
```

**Performance Optimization**: 
- `renderFull()` for initial load (full recalculation)
- `applyPatch()` for changes after solver runs (incremental updates)

### 5. **Two-Phase Solver Coordination**

**Problem**: Solver is heavy; need to track progress and handle failures gracefully.

**Solution**: Coordinator pattern with phase tracking

```python
# services/solver/coordinator.py

class SolverCoordinator:
    def solve(self, scenario, solve_hubs=False, overutilization=1.0):
        # Phase 1: Model building (slow but observable)
        self.progress_tracker("Building optimization model...")
        model = build_pulp_model(scenario, solve_hubs, overutilization)
        
        # Phase 2: Solving (actual PuLP solving)
        self.progress_tracker("Solving... (this may take minutes)")
        status = model.solve()
        
        if status != 1:
            if status == 0:
                raise NonOptimalSolutionError()
            raise SolverError(f"Status: {status}")
        
        # Phase 3: Solution extraction
        new_scenario = extract_solution(model, scenario)
        return new_scenario
```

---

## Important Technical Decisions

### 1. **PyWebView Instead of Electron**
- **Why**: Lighter weight, uses system Python/browser
- **Trade-off**: Less cross-platform support, but simpler distribution
- **Implementation**: `pywebview_main.py` handles window creation, file dialogs

### 2. **Flask for Local-Only API**
- **Why**: Lightweight, built-in, standard Python
- **Security**: Only listens on `127.0.0.1` (localhost)
- **CORS**: Enabled for flexibility but only used for localhost communication

### 3. **Dataclass + Pickle Persistence**
- **Why**: Simple serialization for scenario state
- **Trade-off**: Not human-readable, but fast for large datasets
- **Storage**: `.rob` files contain pickled Python objects

### 4. **Two Flow Directions (Parts/Empties)**
- **Modeling**: Realistic milk runs have dedicated outbound (parts) and return (empties) flows
- **Implementation**: Every Trip, Hub, Route has parts_flow and empties_flow variants
- **Complexity**: Adds significant conditional logic throughout codebase

### 5. **Lock/Block Before Solving**
- **Why**: Solver constraints must be known upfront
- **Not Post-Processing**: Solver runs WITH lock/block constraints, not filtering results
- **Performance**: Reduces solution space early, faster solving

### 6. **Incremental Map Patching**
- **Why**: Full re-render of large networks is slow
- **Patch Protocol**: JSON-based ops (upsert/remove/patch/setUiState)
- **Limitation**: Frontend must deserialize and apply patches correctly

### 7. **Hub Swapping as Separate Operation**
- **Why**: Changing hub allocation is complex; needs validation
- **Two Steps**:
  1. `preview_swap_threshold()` - Show what would change
  2. `move_hub_to_direct()` / `move_direct_to_hub()` - Execute changes
- **Benefit**: User can see impact before committing

### 8. **ProjectManager as Coordinator**
- **Why**: Decouples Flask endpoints from business logic
- **Pattern**: Similar to facade pattern
- **Benefit**: Easy to test, endpoint code stays thin

---

## Data Flow

### Load Project Flow
```
User selects .rob file
    ↓
JavaScript: openLoadProjectWindow() → window.pywebview.api.open_rob_file()
    ↓ (Native file dialog)
User selects file → path returned to JavaScript
    ↓
JavaScript: await apiPost("/api/project/load", {path})
    ↓
Flask: api_load_project(data)
    ↓
ProjectManager: pm.load_project(path)
    ↓
ProjectService: load_project()
    - Unpickle .rob file
    - Load raw GRAF data
    - Reconstruct Project object
    ↓
Response: success()
    ↓
JavaScript: await refreshProjectData()
    - Load regions, scenarios, KPIs
    - Render UI
    - Show map
```

### Solve Flow
```
User clicks "Solve Model"
    ↓
JavaScript: await apiPost("/api/solve_model", {solve_hubs, overutilization, max_stops})
    ↓
Flask: api_solve_model(data)
    - with pm_lock (thread-safe)
    - start_background_task(pm.solve_scenario, ...)
    ↓ Returns task_id immediately
JavaScript receives task_id
    ↓
JavaScript: new EventSource("/api/tasks/{task_id}/events")
    - Listen for "log" events (progress updates)
    - Listen for "done" event
    - Listen for "task_error" event
    ↓ (Meanwhile, background thread)
    ↓
ProjectManager: solve_scenario(solve_hubs, overutilization, max_stops)
    ↓
SolverCoordinator: solve()
    - Build model (with lock/block constraints)
    - Run PuLP solver
    - Extract solution → new Scenario with draft_trips
    ↓
Build map patch showing solver results
    ↓
post to log_queue: progress_tracker(f"Solved with {len(trips)} trips")
    ↓ Event stream delivers to frontend
    ↓
post to log_queue: "done"
    ↓
JavaScript: refreshScenarioData(), showMap()
    - Render new scenario
    - Display updated map with solution
```

### Save/Export Flow
```
User clicks "Save"
    ↓
JavaScript: await apiPost("/api/project/save", {})
    ↓
Flask: api_save_project()
    ↓
ProjectManager: pm.save_project()
    ↓
ProjectService: save_project()
    - Pickle Project object
    - Write to .rob file
    ↓
Response: success({path_saved})
    ↓
User clicks "Export Solution" (Excel)
    ↓
JavaScript: openExportDialog() → path = await window.pywebview.api.export_solution()
    ↓
JavaScript: await apiPost("/api/export_solution", {path})
    ↓
Flask: export_solution(data)
    ↓
ProjectManager: export_solution(path)
    ↓
KpiExporter: export() / GrafExporter: export()
    - Extract trips, routes, KPIs from scenario
    - Write Excel file with multiple sheets
    ↓
Response: success()
    ↓
JavaScript: alert("Exported successfully")
```

---

## Key Services

### 1. **ProjectService** (`services/project_service.py`)
- **Responsibility**: Create, load, save projects
- **Complex Logic**:
  - Loads GRAF Excel file → parses shippers, vehicles, demand
  - Builds baseline scenario (AS-IS)
  - Initializes tariff service
  - Handles file I/O (pickle serialization)

### 2. **ScenarioService** (`services/scenario_service.py`)
- **Responsibility**: Manage scenario lifecycle
- **Operations**:
  - Add scenario (copy of AS-IS)
  - Duplicate scenario (copy of any)
  - Delete scenario (except baseline)
  - Discard draft (revert to saved)

### 3. **TariffService** (`services/tariff_service.py`)
- **Responsibility**: Pricing and route costing
- **Complex Aspects**:
  - LTL (Less Than Truckload) tariffs for hub routes
  - FTL (Full Truckload) tariffs for direct routes
  - Hub assignment logic (which shipper goes to which hub)
  - Route cost calculation

### 4. **HubSwapService** (`services/hub_swap_service.py`)
- **Responsibility**: Moving shippers between hub and direct delivery
- **Operations**:
  - `move_hub_to_direct()` - Shipper leaves hub, joins direct route
  - `move_direct_to_hub()` - Shipper leaves direct route, joins hub
  - Validation (shipper must have valid coordinates, tariffs)

### 5. **SolverCoordinator** (`services/solver/coordinator.py`)
- **Responsibility**: Run optimization solver
- **Optimization Variables**:
  - `solve_hubs`: Whether to optimize hub assignments
  - `overutilization`: Vehicle capacity multiplier (e.g., 1.2 = 20% over capacity)
  - `max_stops`: Maximum stops per trip
- **Output**: New Scenario with optimized draft_trips

### 6. **MapGenerator** (`services/map_generator.py`)
- **Responsibility**: Generate map payloads for Leaflet.js
- **Complex Logic**:
  - Convert routes to GeoJSON LineStrings
  - Render hubs as circles with shipper allocations
  - Style based on flow direction (parts/empties), route type (hub/direct)
  - Generate incremental patches after solver runs
  - Handle unassigned shippers display

---

## Database/Persistence Strategy

**No Traditional Database** - Everything is in-memory + file-based:

1. **Project File** (`.rob`):
   - Pickled Python `Project` object
   - Contains all scenarios, routes, shippers
   - ~Fast to load, ~large file size

2. **Excel Files** (`.xlsx`):
   - Input: GRAF file with shipper data, demand, vehicles
   - Output: Exported solutions with KPIs, routes, assignments

3. **Memory State**:
   - `ProjectManager.project` holds live Project object
   - Changes during session (drafts, lock/block) stay in memory
   - Saved to `.rob` file when user saves

**Advantages**:
- Simple, no database server needed
- Entire project is one file (easy to share)
- Fast loading (single unpickle)

**Disadvantages**:
- Not scalable to very large projects
- No built-in query language
- Pickle security concerns (only load trusted `.rob` files)

---

## Error Handling

### Custom Exceptions (domain/exceptions.py)
```python
class UnsavedScenarioError(Exception):
    """User tried to run solver with unsaved scenario"""

class NonOptimalSolutionError(Exception):
    """Solver couldn't find optimal solution (timeout/infeasible)"""

class ExportingBaselineError(Exception):
    """User tried to export the AS-IS baseline"""

class CannotEditBaselineError(Exception):
    """User tried to modify baseline scenario"""

class NoProjectError(Exception):
    """No project loaded"""
```

### Flask Error Handlers
```python
@app.errorhandler(NonOptimalSolutionError)
def handle_non_optimal_solution(e):
    logger.warning("Non-Optimal Solution Error: %s", e)
    return error(e, {'non_optimal': True}), 500

@app.errorhandler(CannotEditBaselineError)
def handle_editing_baseline(e):
    logger.warning("Can't Edit Baseline Error: %s", e)
    return error(e), 400
```

### Frontend Error Handling
```javascript
try {
    await apiPost("/api/scenario/save", {});
} catch (err) {
    if (err.type === "CannotEditBaselineError") {
        alert("Cannot modify the baseline scenario");
    } else {
        alert(`Error: ${err.message}`);
    }
}
```

---

## Threading & Concurrency

### Problem
- Solver can take minutes
- UI must remain responsive
- Multiple operations could conflict (e.g., user saving while solver runs)

### Solution

**1. Background Threads**
```python
# app.py
thread = threading.Thread(target=worker, daemon=True)
thread.start()
```

**2. Lock Decorator**
```python
@with_pm_lock
def api_solve_model(data):
    # Only one endpoint can access ProjectManager at a time
    ...
```

**3. Thread-Safe Task Queue**
```python
TASKS_LOCK = threading.Lock()  # Protects TASKS dict
with TASKS_LOCK:
    TASKS[task_id] = {...}
```

**Implication**: Operations are serialized; long solver runs can block other operations.

---

## Configuration & Deployment

### Package Configuration (pyproject.toml)
```toml
[project]
name = "rob_4flow"
version = "0.1.3"
requires-python = ">=3.9"
dependencies = [
    "pywebview",        # Desktop wrapper
    "flask",            # Backend
    "pulp",             # Solver
    "pandas",           # Data processing
    "haversine",        # Distance calc
    "folium",           # Map generation
    # ... (other deps)
]

[tool.setuptools.package-data]
rob_4flow = [
    "helper_files/**/*",  # Reference data
    "web/**/*"            # Frontend assets
]
```

### Entry Point
- **CLI**: `pywebview_main.py` starts Flask server + opens desktop window
- **No CLI arguments** - All interaction through GUI
- **Development**: Can run Flask standalone via `app.py` for API testing

---

## Testing Considerations

**Current State**: No tests committed (focus on functionality first)

**Recommended Testing Strategy**:
1. **Unit Tests**: Services (ProjectService, ScenarioService, TariffService)
2. **Integration Tests**: ProjectManager with mock scenarios
3. **Solver Tests**: Small/medium sized optimization problems
4. **Map Generation Tests**: Payload structure validation
5. **Frontend Tests**: API mocking, UI interactions

---

## Future Enhancement Ideas

1. **Database Migration**: PostgreSQL for large projects
2. **Real-time Collaboration**: Multiple users editing same project
3. **Advanced Constraints**: Time windows, vehicle-specific routes
4. **Route Optimization**: Additional solvers (OSRM, Google OR-Tools)
5. **Analytics Dashboard**: Historical KPIs, performance trends
6. **REST API**: Expose as headless service (not just local desktop app)
7. **Mobile App**: React Native for mobile access

---

## Glossary

- **AS-IS**: Baseline scenario (current state)
- **Cofor**: Code representing a supplier/shipper
- **Direct Route**: Shipper → Warehouse (no hub consolidation)
- **FTL**: Full Truckload
- **GRAF**: Excel file format with supply chain data
- **Hub**: Consolidation point for multiple shippers
- **LTL**: Less Than Truckload
- **Milk Run**: Circular delivery route visiting multiple stops
- **Parts**: Outbound flow (warehouse to shippers)
- **Empties**: Return flow (shippers back to warehouse)
- **Shipper**: Supplier/customer location
- **Trip**: A complete delivery route (can contain parts and empties)
- **ROB**: RoutesMilkRun project file (pickled Project object)
- **SSE**: Server-Sent Events (streaming updates)

---

## Contact & Notes

For questions about specific components, refer to the source code in `src/rob_4flow/` which contains detailed comments in complex sections.

**Last Updated**: 2026-05-13
**Project Status**: Active Development (v0.1.3)
