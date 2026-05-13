// render.js

export function renderBase(mapInstance, basePayload) {
  if (!basePayload) return;

  if (
    basePayload.map &&
    basePayload.map.tiles &&
    basePayload.map.tiles !== mapInstance.options.tileUrl
  ) {
    mapInstance.map.removeLayer(mapInstance.tileLayer);
    mapInstance.options.tileUrl = basePayload.map.tiles;
    mapInstance.options.tileOptions =
      basePayload.map.tileOptions || mapInstance.options.tileOptions;

    mapInstance.tileLayer = L.tileLayer(
      mapInstance.options.tileUrl,
      mapInstance.options.tileOptions
    ).addTo(mapInstance.map);
  }

  if (basePayload.uiState) {
    mapInstance.setUiState(basePayload.uiState, {
      sync: false,
      publish: false,
    });
  }

  mapInstance.clearBaseLayers();

  if (basePayload.plant) {
    mapInstance.upsertBaseFeature(basePayload.plant);
  }

  mapInstance.syncVisibleLayers({ publish: false });
  mapInstance.fitBounds(basePayload.bounds);
}

export function renderFull(mapInstance, fullPayload) {
  if (!fullPayload) return;

  if (fullPayload.base) {
    mapInstance.renderBase(fullPayload.base);
  } else if (fullPayload.uiState) {
    mapInstance.setUiState(fullPayload.uiState, {
      sync: false,
      publish: false,
    });
  }

  mapInstance.clearFeatureLayers();

  const features = [...(fullPayload.features || [])].sort((a, b) => {
    return (a.sortOrder || 100) - (b.sortOrder || 100);
  });

  features.forEach((feature) => {
    mapInstance.upsertFeature(feature, { sync: false });
  });

  mapInstance.syncVisibleLayers({ publish: true });
  mapInstance.fitBounds(fullPayload.bounds);
}

export function applyPatch(mapInstance, patch) {
  if (!patch) return;

  for (const op of patch.ops || []) {
    if (op.op === "upsertFeatures") {
      op.features.forEach(feature => mapInstance.upsertFeature(feature));
    }

    if (op.op === "removeFeatures") {
      op.ids.forEach(id => mapInstance.removeFeature(id));
    }

    if (op.op === "patchFeature") {
      mapInstance.patchFeature(op.id, op.changes);
    }

    if (op.op === "setUiState") {
      mapInstance.setUiState(op.uiState);
    }

    if (op.op === "renderBase") {
      mapInstance.renderBase(op.payload);
    }

    if (op.op === "renderFull") {
      mapInstance.renderFull(op.payload);
    }
  }

  if (patch.fitBounds === true && patch.bounds) {
    mapInstance.fitBounds(patch.bounds);
  }

  mapInstance.syncVisibleLayers();
}