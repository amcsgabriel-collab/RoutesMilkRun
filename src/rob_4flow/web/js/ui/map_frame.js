import { ScenarioLeafletMap } from "../map/map.js";
import { apiGet, apiPost } from "../api.js";

let scenarioMap = null;
let eventsWired = false;
let handlers = {};

export function initMap() {
  const container = document.getElementById("map-placeholder");
  if (!container) return null;

  if (!scenarioMap) {
    scenarioMap = new ScenarioLeafletMap(container, {
      postToParent: false,
      showControls: true,
    });
  }

  return scenarioMap;
}

export function wireMapEvents(nextHandlers = {}) {
  handlers = {
    ...handlers,
    ...nextHandlers,
  };

  if (eventsWired) return;

  const container = document.getElementById("map-placeholder");
  if (!container) return;

  eventsWired = true;

  container.addEventListener("scenario-map-state-changed", (event) => {
    const state = handlers.getState?.();
    if (!state) return;

    const mapState = event.detail.payload;

    state.mapUiState = {
      flow: mapState.flow ?? "parts",
      show_baseline: Boolean(mapState.show_baseline),
      show_last_leg: Boolean(mapState.show_last_leg),
      show_unassigned_shippers: mapState.show_unassigned_shippers !== false,
      active_networks: Array.isArray(mapState.active_networks)
        ? mapState.active_networks
        : ["Direct", "Hubs"],
    };
  });

  container.addEventListener("scenario-map-object-selected", (event) => {
    const state = handlers.getState?.();
    if (!state) return;

    const selectedObject = event.detail.payload;

    state.selectedObject = selectedObject;
    handlers.renderSelectionSummary?.(selectedObject);
  });

  container.addEventListener("scenario-map-object-right-clicked", (event) => {
    const { payload, position } = event.detail;

    handlers.openContextMenu?.(position, payload);
  });
}

export async function showMap() {
  initMap();
  await renderScenarioMapFull();
}

export async function renderScenarioMapFull() {
  const map = initMap();
  const state = handlers.getState?.();

  if (!map || !state) return;

  const selectedScenario = state.scenarios[state.selectedIndex];

  const fullPayload = await apiGet("/api/scenario-map/full", {
    scenario_id: selectedScenario?.id,
    scenario_name: selectedScenario?.name,
    ui_state: state.mapUiState,
  });

  map.renderFull(fullPayload);
}

export function updateMapUiState(nextUiState) {
  const map = initMap();
  const state = handlers.getState?.();

  if (!map || !state) return;

  state.mapUiState = {
    ...state.mapUiState,
    ...nextUiState,
  };

  map.setUiState(state.mapUiState);
}

export function getScenarioMap() {
  return scenarioMap;
}