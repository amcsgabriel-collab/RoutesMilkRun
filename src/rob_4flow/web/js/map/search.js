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
  if (!mapInstance.searchHighlightedIds) {
    mapInstance.searchHighlightedIds = new Set();
  }

  clearSearchHighlight(mapInstance);

  const normalizedTerm = normalizeSearch(term);
  if (!normalizedTerm) return;

  for (const [featureId, feature] of mapInstance.features.entries()) {
    if (!mapInstance.isFeatureVisible(feature)) continue;
    if (!featureMatchesSearch(feature, normalizedTerm)) continue;

    const groupIds = mapInstance.getFeatureGroupIds(featureId);
    groupIds.forEach(id => mapInstance.searchHighlightedIds.add(id));
  }

  mapInstance.applyStyleToIds(mapInstance.searchHighlightedIds, "hover");
}

export function addSearchControl(mapInstance) {
  if (!mapInstance?.map) return;

  const SearchControl = L.Control.extend({
    options: {
      position: "topright",
    },

    onAdd() {
      const container = L.DomUtil.create(
        "div",
        "scenario-map-control scenario-map-search-control"
      );

      const input = L.DomUtil.create("input", "scenario-map-search-input", container);
      input.type = "search";
      input.placeholder = "Search map...";
      input.autocomplete = "off";

      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);

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

      return container;
    },
  });

  mapInstance.searchControl = new SearchControl();
  mapInstance.searchControl.addTo(mapInstance.map);
}