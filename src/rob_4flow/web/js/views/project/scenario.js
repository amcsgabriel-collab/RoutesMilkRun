import { apiGet, apiPost, apiPut, apiDelete, apiPatch } from "../../api.js";
import { escapeHtml } from "../../utils.js";
import { loadScenarioKpis } from "../../ui/kpis_page_rendering.js";
import { showMap, getScenarioMap } from "../../ui/map_frame.js";

let state = {
  scenarios: [],
  selectedIndex: -1,
  mapUiState: {
    flow: "parts",
    show_baseline: false,
    active_networks: ["Direct", "Hubs"],
    show_last_leg: false,
  },
};

export function getState() {
  return state;
}

export function getScenarioState() {
  return state;
}

export function wireScenarioPanel() {
  document.getElementById("sc-add").addEventListener("click", handleAddScenario);
  document.getElementById("sc-duplicate").addEventListener("click", handleDuplicateScenario);
  document.getElementById("sc-delete").addEventListener("click", handleDeleteScenario);
  document.getElementById("sc-save").addEventListener("click", handleSaveScenario);
  document.getElementById("sc-discard").addEventListener("click", handleDiscardScenarioDraft);
}

export async function refreshScenarioData() {
  await loadScenarios();
  await applyScenarioSelectionFromServer();
  renderScenarios();
  await loadScenarioKpis();
}

async function handleAddScenario() {
  try {
    await apiPost("/api/scenario/add", {});
    await refreshScenarioData();
    await showMap();
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
    await apiPost("/api/scenario/duplicate", { name });
    await refreshScenarioData();
    await showMap();
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
    state.selectedIndex = -1;
    await refreshScenarioData();
    await showMap();
  } catch (err) {
    console.error("Delete failed:", err);
    alert("Delete failed: " + (err.message || err));
  }
}

async function handleSaveScenario() {
  if (!confirm("Are you sure you want to overwrite the current scenario routes?")) {
    return;
  }

  await apiPatch("/api/scenario");
  await refreshScenarioData();
  await showMap();
}

async function handleDiscardScenarioDraft() {
  if (state.selectedIndex < 0) return alert("Select a scenario first");

  const name = state.scenarios[state.selectedIndex].name;
  if (!confirm("Discard draft for scenario '" + name + "'?")) return;

  try {
    await apiDelete("/api/scenario/draft", { name });
    await refreshScenarioData();
    await showMap();
  } catch (err) {
    console.error("Discard draft failed:", err);
    alert("Discard draft failed: " + (err.message || err));
  }
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
    if (!Array.isArray(state.scenarios) || state.scenarios.length === 0) {
      await loadScenarios();
    }

    const project = await apiGet("/api/project");
    const currentScenario = project?.meta?.current_scenario;
    if (!currentScenario) return;

    const idx = state.scenarios.findIndex(s => s?.name === currentScenario);
    if (idx >= 0) {
      state.selectedIndex = idx;
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
    const safeName = escapeHtml(s?.name || `scenario ${i}`);
    const draftDot = s?.has_draft ? `<span class="scenario-dot"></span>` : "";

    return `
      <div class="scenario-item ${selected}" data-idx="${i}" role="button" tabindex="0">
        ${draftDot}${safeName}
      </div>
    `;
  }).join("");

  scenariosList.querySelectorAll(".scenario-item").forEach(node => {
    node.addEventListener("click", async () => {
      const idx = Number(node.dataset.idx);
      const scenario = state.scenarios[idx];
      if (!scenario) return;

      try {
        await apiPut("/api/scenario", { scenario_name: scenario.name });
        await refreshScenarioData();
        await showMap();
      } catch (err) {
        console.error("select scenario failed:", err);
        alert("Failed to select scenario: " + (err.message || err));
      }
    });

    node.addEventListener("keydown", event => {
      if (event.key === "Enter") node.click();
    });
  });
}

export async function applyMapPatchOrRefresh(mapPatch) {
  const map = getScenarioMap();

  if (map && mapPatch) {
    map.applyPatch(mapPatch);
    return;
  }

  await refreshScenarioData();
}