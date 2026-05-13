// features.js

import { clone, deepMerge } from "./utils.js";

export function clearBaseLayers(mapInstance) {
  mapInstance.baseLayers.forEach((layer) => mapInstance.map.removeLayer(layer));
  mapInstance.baseLayers.clear();
  mapInstance.baseFeatures.clear();
}

export function clearFeatureLayers(mapInstance) {
  mapInstance.layers.forEach((layer) => mapInstance.map.removeLayer(layer));
  mapInstance.layers.clear();
  mapInstance.features.clear();
  mapInstance.selectedFeatureId = null;
  mapInstance.selectedGroupIds.clear();
}

export function upsertBaseFeature(mapInstance, feature) {
  if (!feature || !feature.id) return;

  const existing = mapInstance.baseLayers.get(feature.id);
  if (existing) {
    mapInstance.map.removeLayer(existing);
  }

  const normalizedFeature = clone(feature);
  const layer = mapInstance.createLayer(normalizedFeature, { base: true });

  mapInstance.baseFeatures.set(normalizedFeature.id, normalizedFeature);
  mapInstance.baseLayers.set(normalizedFeature.id, layer);

  layer.addTo(mapInstance.map);
}

export function upsertFeature(mapInstance, feature, options = {}) {
  if (!feature || !feature.id) return;

  const existing = mapInstance.layers.get(feature.id);
  if (existing) {
    mapInstance.map.removeLayer(existing);
    mapInstance.layers.delete(feature.id);
  }

  const normalizedFeature = clone(feature);
  const layer = mapInstance.createLayer(normalizedFeature, { base: false });

  mapInstance.features.set(normalizedFeature.id, normalizedFeature);
  mapInstance.layers.set(normalizedFeature.id, layer);

  if (mapInstance.selectedGroupIds.has(normalizedFeature.id)) {
    mapInstance.applyStyleToFeature(normalizedFeature.id, "selected");
  }

  if (options.sync !== false) {
    mapInstance.syncVisibleLayers({ publish: true });
  }
}

export function patchFeature(mapInstance, featureId, changes, options = {}) {
  const current = mapInstance.features.get(featureId);
  if (!current) {
    console.warn("Cannot patch unknown scenario map feature:", featureId);
    return;
  }

  const merged = deepMerge(clone(current), changes || {});
  mapInstance.upsertFeature(merged, { sync: false });

  if (options.sync !== false) {
    mapInstance.syncVisibleLayers({ publish: true });
  }
}

export function removeFeature(mapInstance, featureId, options = {}) {
  const layer = mapInstance.layers.get(featureId);
  if (layer) {
    mapInstance.map.removeLayer(layer);
  }

  mapInstance.layers.delete(featureId);
  mapInstance.features.delete(featureId);

  if (mapInstance.selectedGroupIds.has(featureId)) {
    mapInstance.clearSelection();
  }

  if (options.sync !== false) {
    mapInstance.syncVisibleLayers({ publish: true });
  }
}