// controls.js

export function installControls(mapInstance) {
  if (!mapInstance?.map) return;

  mapInstance.searchHighlightedIds = mapInstance.searchHighlightedIds || new Set();

  const toolbarControl = L.control({ position: "topleft" });

  toolbarControl.onAdd = () => {
    const toolbar = L.DomUtil.create("div", "scenario-map-toolbar");

    L.DomEvent.disableClickPropagation(toolbar);
    L.DomEvent.disableScrollPropagation(toolbar);

    addSearchGroup(mapInstance, toolbar);
    addBaselineGroup(mapInstance, toolbar);
    addNetworkGroup(mapInstance, toolbar);
    addFlowGroup(mapInstance, toolbar);

    return toolbar;
  };

  toolbarControl.addTo(mapInstance.map);

  updateControls(mapInstance);
}

function addBaselineGroup(mapInstance, toolbar) {
  const group = L.DomUtil.create(
    "div",
    "scenario-map-control",
    toolbar
  );

  const baseline = makeButton(
    "Baseline",
    "baseline",
    () => mapInstance.toggleBaseline()
  );

  const lastLeg = makeButton(
    "Last leg",
    "lastLeg",
    () => mapInstance.toggleLastLeg()
  );

  const unassigned = makeButton(
    "Unassigned",
    "unassigned",
    () => mapInstance.toggleUnassignedShippers()
  );

  group.appendChild(baseline);
  group.appendChild(lastLeg);
  group.appendChild(unassigned);

  mapInstance.controlButtons = mapInstance.controlButtons || {
    networks: {},
    flows: {},
  };

  mapInstance.controlButtons.baseline = baseline;
  mapInstance.controlButtons.lastLeg = lastLeg;
  mapInstance.controlButtons.unassigned = unassigned;
}

function addNetworkGroup(mapInstance, toolbar) {
  const group = L.DomUtil.create(
    "div",
    "scenario-map-control",
    toolbar
  );

  const direct = makeButton(
    "Direct",
    "network",
    () => mapInstance.toggleNetwork("Direct")
  );

  const hubs = makeButton(
    "Hubs",
    "network",
    () => mapInstance.toggleNetwork("Hubs")
  );

  group.appendChild(direct);
  group.appendChild(hubs);

  mapInstance.controlButtons.networks.Direct = direct;
  mapInstance.controlButtons.networks.Hubs = hubs;
}

function addFlowGroup(mapInstance, toolbar) {
  const group = L.DomUtil.create(
    "div",
    "scenario-map-control",
    toolbar
  );

  const parts = makeButton(
    "Parts",
    "flow",
    () => mapInstance.selectFlow("parts")
  );

  const empties = makeButton(
    "Empties",
    "flow",
    () => mapInstance.selectFlow("empties")
  );

  group.appendChild(parts);
  group.appendChild(empties);

  mapInstance.controlButtons.flows.parts = parts;
  mapInstance.controlButtons.flows.empties = empties;
}

export function makeButton(label, type, onClick) {
  const button = L.DomUtil.create("button", "scenario-map-btn");
  button.type = "button";
  button.textContent = label;
  button.dataset.type = type;

  L.DomEvent.on(button, "click", (event) => {
    L.DomEvent.preventDefault(event);
    L.DomEvent.stopPropagation(event);
    onClick();
  });

  return button;
}

export function updateControls(mapInstance) {
  if (!mapInstance.controlButtons) return;

  mapInstance.controlButtons.baseline?.classList.toggle(
    "active",
    mapInstance.uiState.show_baseline
  );

  mapInstance.controlButtons.lastLeg?.classList.toggle(
    "active",
    mapInstance.uiState.show_last_leg
  );

  mapInstance.controlButtons.unassigned?.classList.toggle(
  "active",
  mapInstance.uiState.show_unassigned_shippers
  );

  Object.entries(mapInstance.controlButtons.networks || {}).forEach(
    ([network, button]) => {
      button.classList.toggle(
        "active",
        mapInstance.uiState.active_networks.includes(network)
      );
    }
  );

  Object.entries(mapInstance.controlButtons.flows || {}).forEach(
    ([flow, button]) => {
      button.classList.toggle("radio-active", mapInstance.uiState.flow === flow);
    }
  );
}

// search.js

function normalizeSearch(value) {
  return String(value ?? "").trim().toLowerCase();
}

function includesSearch(value, term) {
  return String(value ?? "").toLowerCase().includes(term);
}

function featureMatchesSearch(feature, term) {
  const payload = feature.payload || {};

  const values = [
    feature.id,

    payload.cofor,
    payload.name,
    payload.currentRoute,

    payload.route?.id,
    payload.route?.name,
    payload.route?.subtype,
    ...(payload.route?.key || []),

    payload.hub?.cofor,
    payload.hub?.name,

    payload.key,
    ...(payload.route_key || []),
  ];

  return values.some(value => includesSearch(value, term));
}

export function clearSearchHighlight(mapInstance) {
  if (!mapInstance.searchHighlightedIds?.size) return;

  const idsToReset = new Set(
    [...mapInstance.searchHighlightedIds].filter(
      id => !mapInstance.selectedGroupIds.has(id)
    )
  );

  mapInstance.applyStyleToIds(idsToReset, "normal");
  mapInstance.searchHighlightedIds.clear();
}

export function setSearchTerm(mapInstance, term) {
  mapInstance.searchTerm = term;

  if (normalizeSearch(term) && mapInstance.selectedGroupIds?.size) {
    mapInstance.clearSelection?.();
  }

  mapInstance.searchHighlightedIds = mapInstance.searchHighlightedIds || new Set();

  clearSearchHighlight(mapInstance);

  const normalizedTerm = normalizeSearch(term);
  if (!normalizedTerm) return;

  for (const [featureId, feature] of mapInstance.features.entries()) {
    if (!mapInstance.isFeatureVisible(feature)) continue;
    if (!featureMatchesSearch(feature, normalizedTerm)) continue;

    const groupIds = mapInstance.getFeatureGroupIds(featureId);
    groupIds.forEach(id => mapInstance.searchHighlightedIds.add(id));
  }

  mapInstance.applyStyleToIds(mapInstance.searchHighlightedIds, "selected");
}

function addSearchGroup(mapInstance, toolbar) {
  const group = L.DomUtil.create(
    "div",
    "scenario-map-control scenario-map-search-group",
    toolbar
  );

  const input = L.DomUtil.create(
    "input",
    "scenario-map-search-input",
    group
  );

  input.type = "search";
  input.placeholder = "Search map...";
  input.autocomplete = "off";

  input.addEventListener("input", () => {
    setSearchTerm(mapInstance, input.value);
  });

  input.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      input.value = "";
      clearSearchHighlight(mapInstance);
      input.blur();
    }
  });
}