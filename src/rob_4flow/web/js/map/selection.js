// selection.js

import { setsIntersect } from "./utils.js";

export function selectFeature(mapInstance, featureId) {
  mapInstance.clearSelection();

  mapInstance.selectedFeatureId = featureId;
  mapInstance.selectedGroupIds = getFeatureGroupIds(mapInstance, featureId);
  mapInstance.applyStyleToIds(mapInstance.selectedGroupIds, "selected");

  mapInstance.selectedGroupIds.forEach((id) => {
    const layer = mapInstance.layers.get(id);
    if (layer?.bringToFront) {
      layer.bringToFront();
    }
  });
}

export function clearSelection(mapInstance) {
  if (mapInstance.selectedGroupIds.size > 0) {
    mapInstance.applyStyleToIds(mapInstance.selectedGroupIds, "normal");
  }

  mapInstance.selectedFeatureId = null;
  mapInstance.selectedGroupIds = new Set();
}

export function getFeatureGroupIds(mapInstance, featureOrId) {
  const feature =
    typeof featureOrId === "string"
      ? mapInstance.features.get(featureOrId)
      : featureOrId;

  const ids = new Set();
  if (!feature) return ids;

  ids.add(feature.id);
  (feature.linkedFeatureIds || []).forEach((id) => ids.add(id));

  return ids;
}

export function isFeatureGroupSelected(mapInstance, featureId) {
  const groupIds = getFeatureGroupIds(mapInstance, featureId);
  return setsIntersect(groupIds, mapInstance.selectedGroupIds);
}