// Configures the main "project" window.

import { apiGet, apiPost, apiPut, apiDelete, apiPatch } from "../api.js";
import { loadHtml, escapeHtml } from "../utils.js";
import { openShippersModal } from "../ui/shippers_table_modal.js"
import { openRoutesModal } from "../ui/routes_table_modal.js"
import { openHubsModal } from "../ui/hubs_table_modal.js"
import { openVehiclesModal } from "../ui/vehicles_table_modal.js"
import { openSwapModal } from '../ui/swap_hub_direct.js';
import { setAppBusy } from "../ui/overlay.js";
import { openLockRoutesModal, openBlockRoutesModal } from "../ui/lock_block_routes_modal.js";
import { loadScenarioKpis } from "../ui/kpis_page_rendering.js"
import { openSolveLogbox } from "../ui/solver_logbox.js";


let state = {
  scenarios: [],
  selectedIndex: -1,
  mapUiState: {
    flow: "parts",
    show_baseline: false,
    active_networks: ["Direct", "Hubs"],
  },
};

export async function showProjectPage() {
  const html = await loadHtml("/views_html/project.html");
  document.getElementById("content").innerHTML = html;
  await initializeProjectPage();
}

async function initializeProjectPage() {

  // Wiring up all project page action buttons.
  document.getElementById("region-select").addEventListener("change", onRegionChange);
  // Scenario actions
  document.getElementById("sc-add").addEventListener("click", handleAddScenario);
  document.getElementById("sc-duplicate").addEventListener("click", handleDuplicateScenario);
  document.getElementById("sc-delete").addEventListener("click", handleDeleteScenario);
  document.getElementById("sc-save").addEventListener("click", handleSaveScenario);
  // Tables
  document.getElementById("shippers-table").addEventListener("click", openShippersModal);
  document.getElementById("routes-table").addEventListener("click", openRoutesModal);
  document.getElementById("hubs-table").addEventListener("click", openHubsModal);
  document.getElementById("vehicles-table").addEventListener("click", openVehiclesModal);
  // Solver scenario actions
  document.getElementById("swap-hub-direct").addEventListener("click", openSwapModal);
  document.getElementById("solver-run").addEventListener("click", runSolver);
  document.getElementById("lock-routes")?.addEventListener("click", openLockRoutesModal);
  document.getElementById("block-routes")?.addEventListener("click", openBlockRoutesModal);
  document.getElementById("solution-export").addEventListener("click", exportSolution);
  // Toggle expand/hide the right panel.
  document.getElementById('right-panel-toggle').addEventListener('click', ToggleCollapseRightPanel)
  // Wire the toggling of the Map/KPIs panels
  wireToggleMap()
  // Wire map event-changing observer
  window.addEventListener("message", (event) => {
  if (event.data?.type !== "scenario-map-state-changed") return;

  const mapState = event.data.payload;
  state.mapUiState = {
    flow: mapState.flow ?? "parts",
    show_baseline: Boolean(mapState.show_baseline),
    active_networks: Array.isArray(mapState.active_networks)
      ? mapState.active_networks
      : ["Direct", "Hubs"],
      };
    });

  // Load project content and refresh UI.
  await refreshProjectData()
}

async function handleAddScenario() {
  try {
    await apiPost("/api/scenario/add", {});   // TODO: Add "name" to the scenario when creating.
    await refreshScenarioData();
  } catch (err) {
    console.error("Create scenario failed:", err);
    alert("Failed to create scenario: " + (err.message || err));
  }
}

async function handleDuplicateScenario() {
  if (state.selectedIndex < 0) return alert("Select a scenario first");
  const name = state.scenarios[state.selectedIndex].name;
  if (!confirm("Duplicate scenario '" + name + "'?")) return;
  try {
    // include newName so server can create a duplicate with the requested name
    await apiPost("/api/scenario/duplicate", { name });
    await refreshScenarioData();
  } catch (err) {
    console.error("Duplicate failed:", err);
    alert("Duplicate failed: " + (err.message || err));
  }
}

async function handleDeleteScenario() {
  if (state.selectedIndex < 0) return alert("Select a scenario first");
  const name = state.scenarios[state.selectedIndex].name;
  if (!confirm("Delete scenario '" + name + "'?")) return;
  try {
    await apiDelete("/api/scenario", { name });
    // clear selection locally
    state.selectedIndex = -1;
    await refreshScenarioData();
  } catch (err) {
    console.error("Delete failed:", err);
    alert("Delete failed: " + (err.message || err));
  }
}

async function handleSaveScenario() {
  if (!confirm("Are you sure you want to overwrite the current scenario routes?")) {
    return;
  }
  await apiPatch("/api/scenario")
  await refreshScenarioData()
}


// Show/hide the right panel and adjust formatting.
function ToggleCollapseRightPanel() {
  const grid = document.querySelector('.project-grid');
  const toggleBtn = document.getElementById('right-panel-toggle');
  const collapsed = grid.classList.toggle('right-collapsed');
  toggleBtn.textContent = collapsed ? '›' : '‹';
  toggleBtn.setAttribute('aria-expanded', String(!collapsed));
  toggleBtn.title = collapsed ? 'Expand panel' : 'Collapse panel';
}

export async function refreshProjectData() {
  await loadProjectOverview();
  await loadRegions();
  await refreshScenarioData()
}

// Load project metadata to fill in the overview card.
async function loadProjectOverview() {
  try {
    const project = await apiGet("/api/project");
    // Change project name in overview card.
    document.getElementById("overview-body").innerHTML =
      `<div><strong>Project:</strong> ${escapeHtml(project.meta.name || "")}</div>`;
    // Change plant name in overview card.
    document.getElementById("plant-name").innerHTML =
      `${escapeHtml(project.context.plant_name || "")}`;
  } catch (e) {
    document.getElementById("overview-body").textContent = "Failed to load";
  }
}

async function onRegionChange() {
  const select = document.getElementById("region-select");
  if (!select) return;

  const region = select.value;
  await apiPut("/api/region", { region });
  await refreshProjectData();
}

// Load the data that goes into the "Sourcing Region" selector and picks current selection from the project meta.
async function loadRegions() {
  const select = document.getElementById("region-select");
  if (!select) return;

  const regions = await apiGet("/api/regions");
  select.innerHTML = regions
    .map(r => `<option value="${r}">${r}</option>`)
    .join("");

  // Set current region from project meta.
  const project = await apiGet("/api/project");
  const currentRegion = project.meta.current_region;
  if (currentRegion) select.value = currentRegion;
}



async function refreshScenarioData() {
  await loadScenarios();
  applyScenarioSelectionFromServer();
  renderScenarios();
  renderScenarioSummary();
  await showMap();
  await loadScenarioKpis();
}

async function loadScenarios() {
  const scenariosList = document.getElementById("scenarios-list");
  scenariosList.textContent = "Loading...";
  try {
    const list = await apiGet("/api/scenarios");
    state.scenarios = Array.isArray(list) ? list : [];
    state.selectedIndex = -1;
  } catch (e) {
    console.error("loadScenarios error:", e);
    scenariosList.textContent = "Error loading scenarios";
  }
}

async function applyScenarioSelectionFromServer() {
  try {
    // make sure scenarios are loaded before applying server selection
    if (!Array.isArray(state.scenarios) || state.scenarios.length === 0) {
      await loadScenarios();
    }

    const project = await apiGet("/api/project");
    const currentScenario = project && project.meta && project.meta.current_scenario;
    if (!currentScenario) return;

    const idx = state.scenarios.findIndex(s => s && s.name === currentScenario);
    if (idx >= 0) {
      state.selectedIndex = idx;
      renderScenarios();
      renderScenarioSummary();
      await showMap();
      await loadScenarioKpis();
    }
  } catch (err) {
    console.warn("Could not apply selection from server:", err);
  }
}

function renderScenarios() {
  const scenariosList = document.getElementById("scenarios-list");
  if (!Array.isArray(state.scenarios) || state.scenarios.length === 0) {
    scenariosList.innerHTML = "<div>No scenarios</div>";
    return;
  }

  scenariosList.innerHTML = state.scenarios.map((s, i) => {
    const selected = i === state.selectedIndex ? "selected" : "";
    const safeName = escapeHtml((s && s.name) || `scenario ${i}`);
    return `<div class="scenario-item ${selected}" data-idx="${i}" role="button" tabindex="0">
              ${safeName}
            </div>`;
  }).join("");

  // attach handlers
  scenariosList.querySelectorAll(".scenario-item").forEach(node => {
    node.addEventListener("click", async () => {
      const idx = Number(node.dataset.idx);
      const s = state.scenarios[idx];
      if (!s) return;
      try {
        await apiPut("/api/scenario", { scenario_name: s.name });
        await applyScenarioSelectionFromServer();
      } catch (err) {
        console.error("select scenario failed:", err);
        alert("Failed to select scenario: " + (err.message || err));
      }
    });

    // keyboard accessibility: Enter to select
    node.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") node.click();
    });
  });
}

function renderScenarioSummary() {
  const out = document.getElementById("scenario-summary");
  if (!out) return console.warn("No #scenario-summary element found");
  if (state.selectedIndex < 0) { out.textContent = "No scenario selected"; return; }
  const s = state.scenarios[state.selectedIndex];
  if (!s) { out.textContent = "No scenario selected"; return; }

  const costStr = (s.total_cost != null)
    ? Number(s.direct_total_cost).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })
    : "—";

  const freqStr = (s.trucks != null)
    ? Number(s.direct_trucks).toLocaleString(undefined, { maximumFractionDigits: 2 })
    : "—";

  const utilStr = (s.utilization != null)
    ? (Number(s.direct_utilization) * (Number(s.direct_utilization) <= 1 ? 100 : 1))
      .toLocaleString(undefined, { maximumFractionDigits: 1 }) + "%"
    : "—";

  const updatedStr = s.updated_at
    ? new Date(s.updated_at).toLocaleString()
    : "—";

  out.innerHTML = `
    <div><strong>${escapeHtml(s.name)}</strong></div>
    <div>Direct cost: ${costStr}</div>
    <div>Direct total frequency: ${freqStr}</div>
    <div>Direct overall utilization: ${utilStr}</div>
    <div>updated at: ${updatedStr}</div>
  `;
}

function wireToggleMap() {
  const tabButtons = document.querySelectorAll(".panel-tab");

  tabButtons.forEach(button => {
      button.addEventListener("click", () => {
          const selectedTab = button.dataset.tab;

          document.querySelectorAll(".panel-tab").forEach(btn => {
              btn.classList.remove("active");
          });
          document.querySelectorAll(".tab-pane").forEach(pane => {
              pane.classList.remove("active");
          });

          button.classList.add("active");
          document.getElementById(`tab-${selectedTab}`).classList.add("active");
    })});
};

export async function showMap() {
  const container = document.getElementById("map-placeholder");
  container.innerHTML = '<iframe id="map-iframe" style="width:100%;height:100%;border:0"></iframe>';
  const iframe = document.getElementById("map-iframe");

  try {
    const html = await apiPost("/api/map", {
      ui_state: state.mapUiState
    });
    iframe.srcdoc = html;
  } catch (e) {
    container.textContent = "Map load failed";
    alert("Map load failed: " + (e.message || e));
  }
}

async function runSolver() {
  if (!confirm("Run the solver for current scenario?")) {
    return;
  }
  try {
  await openSolveLogbox();
  await refreshScenarioData();
} catch (e) {
  alert(e.message || "Unexpected error during solving.");
}
}

async function exportSolution() {
  try {
    await apiPost("/api/export_solution/validate");
    const path = await window.pywebview.api.export_solution();
    await apiPost("/api/export_solution", { path });
    alert("Solution exported successfully.");
  } catch (e) {
    alert(e.message || "Unexpected error.");
  }
}

export function getState() { return state; }
