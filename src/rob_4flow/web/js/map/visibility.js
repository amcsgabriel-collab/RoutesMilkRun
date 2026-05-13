// visibility.js

export function isFeatureVisible(mapInstance, feature) {
  if (!feature) return false;
  if (feature.alwaysVisible) return true;
  if (
    feature.network &&
    !mapInstance.uiState.active_networks.includes(feature.network)
  ) {
    return false;
  }

  if (feature.flow && feature.flow !== mapInstance.uiState.flow) {
    return false;
  }

  if (feature.baseline && !mapInstance.uiState.show_baseline) {
    return false;
  }

  if (feature.lastLeg && !mapInstance.uiState.show_last_leg) {
    return false;
  }

  if (
    feature.subtype === "unassigned-shipper" &&
    mapInstance.uiState.show_unassigned_shippers === false
  ) {
    return false;
  }

  return true;
}

export function syncVisibleLayers(mapInstance, options = {}) {
  mapInstance.layers.forEach((layer, id) => {
    const feature = mapInstance.features.get(id);
    const visible = isFeatureVisible(mapInstance, feature);
    const currentlyVisible = mapInstance.map.hasLayer(layer);

    if (visible && !currentlyVisible) {
      layer.addTo(mapInstance.map);
    } else if (!visible && currentlyVisible) {
      mapInstance.map.removeLayer(layer);
    }
  });

  if (mapInstance.searchTerm) {
  mapInstance.setSearchTerm(mapInstance.searchTerm);
}

  mapInstance.updateControls();
  window.scenarioMapState = mapInstance.getCurrentMapState();

  if (options.publish !== false) {
    mapInstance.emit("scenario-map-state-changed", {
      payload: mapInstance.getCurrentMapState(),
    });
  }
}