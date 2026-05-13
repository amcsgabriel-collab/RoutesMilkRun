import { installControls, updateControls, clearSearchHighlight, setSearchTerm } from "./controls.js";
import {
  DEFAULT_TILE_URL,
  DEFAULT_TILE_OPTIONS,
  DEFAULT_CENTER,
  DEFAULT_ZOOM,
  DEFAULT_FIT_PADDING,
  DEFAULT_UI_STATE,
  normalizeUiState,
  fitBounds,
} from "./defaults.js";
import { emit, attachFeatureEvents } from "./events.js";
import {
  clearBaseLayers,
  clearFeatureLayers,
  upsertBaseFeature,
  upsertFeature,
  patchFeature,
  removeFeature,
} from "./features.js";
import { createLayer, applyStyle, removeFocusBox, getFeatureVectorStyle } from "./layers.js";
import { ensurePanes } from "./panes.js";
import { renderBase, renderFull, applyPatch } from "./render.js";
import { selectFeature, clearSelection, getFeatureGroupIds } from "./selection.js";
import { isFeatureVisible, syncVisibleLayers } from "./visibility.js";

class ScenarioLeafletMap {
  constructor(container, options = {}) {
    this.container = typeof container === "string" ? document.getElementById(container) : container;
    if (!this.container) {
      throw new Error("ScenarioLeafletMap container not found.");
    }

    this.options = {
      showControls: true,
      postToParent: true,
      tileUrl: DEFAULT_TILE_URL,
      tileOptions: DEFAULT_TILE_OPTIONS,
      defaultCenter: DEFAULT_CENTER,
      defaultZoom: DEFAULT_ZOOM,
      fitPadding: DEFAULT_FIT_PADDING,
      ...options,
    };

    this.uiState = normalizeUiState(DEFAULT_UI_STATE);

    this.features = new Map();
    this.layers = new Map();
    this.baseFeatures = new Map();
    this.baseLayers = new Map();
    this.selectedFeatureId = null;
    this.selectedGroupIds = new Set();
    this.controlButtons = null;
    this.searchHighlightedIds = new Set();

    this.map = L.map(this.container, {
      zoomControl: false,
      preferCanvas: false,
    }).setView(this.options.defaultCenter, this.options.defaultZoom);

    this.tileLayer = L.tileLayer(this.options.tileUrl, this.options.tileOptions).addTo(this.map);
    L.control.scale().addTo(this.map);

    ensurePanes(this.map);

    if (this.options.showControls) {
      this.installControls();
    }

    this.container.addEventListener("contextmenu", function (event) {
      event.preventDefault();
    });
  }

  getCurrentMapState() {
    return {
      flow: this.uiState.flow,
      show_baseline: this.uiState.show_baseline,
      show_last_leg: this.uiState.show_last_leg,
      active_networks: [...this.uiState.active_networks],
    };
  }

  emit(type, detail) {
    return emit(this, type, detail);
  }

  attachFeatureEvents(layer, featureId) {
    return attachFeatureEvents(this, layer, featureId);
  }

  renderBase(basePayload) {
    return renderBase(this, basePayload);
  }

  renderFull(fullPayload) {
    return renderFull(this, fullPayload);
  }

  applyPatch(patch) {
    return applyPatch(this, patch);
  }

  createLayer(feature, options = {}) {
    return createLayer(this, feature, options);
  }

  fitBounds(bounds) {
    return fitBounds(this.map, bounds, this.options.fitPadding);
  }

  removeFocusBox(layer) {
    return removeFocusBox(layer);
  }

  clearBaseLayers() {
    return clearBaseLayers(this);
  }

  clearFeatureLayers() {
    return clearFeatureLayers(this);
  }

  upsertBaseFeature(feature) {
    return upsertBaseFeature(this, feature);
  }

  upsertFeature(feature, options = {}) {
    return upsertFeature(this, feature, options);
  }

  patchFeature(featureId, changes, options = {}) {
    return patchFeature(this, featureId, changes, options);
  }

  removeFeature(featureId, options = {}) {
    return removeFeature(this, featureId, options);
  }

  selectFeature(featureId) {
    return selectFeature(this, featureId);
  }

  clearSelection() {
    return clearSelection(this)
  }

  setSearchTerm(term) {
    setSearchTerm(this, term);
  }

  clearSearchHighlight() {
    clearSearchHighlight(this);
  }

  getFeatureGroupIds(featureOrId) {
    return getFeatureGroupIds(this, featureOrId)
  }

  applyStyleToIds(ids, styleName) {
    ids.forEach((id) => this.applyStyleToFeature(id, styleName));
  }

  applyStyleToFeature(featureId, styleName) {
    const feature = this.features.get(featureId);
    const layer = this.layers.get(featureId);
    if (!feature || !layer) return;

    applyStyle(layer, getFeatureVectorStyle(feature, styleName));
    removeFocusBox(layer);
  }

  setUiState(nextState, options = {}) {
    this.uiState = normalizeUiState({
      ...this.uiState,
      ...(nextState || {}),
    });

    if (options.sync !== false) {
      this.syncVisibleLayers({ publish: options.publish !== false });
    }
  }

  toggleNetwork(network) {
    const active = new Set(this.uiState.active_networks);
    if (active.has(network)) {
      active.delete(network);
    } else {
      active.add(network);
    }
    this.setUiState({ active_networks: [...active] });
  }

  toggleUnassignedShippers() {
    this.setUiState({
      ...this.uiState,
      show_unassigned_shippers: !this.uiState.show_unassigned_shippers,
    });
  }

  isFeatureVisible(feature) {
    return isFeatureVisible(this, feature);
  }

  syncVisibleLayers(options = {}) {
    return syncVisibleLayers(this, options);
  }

  selectFlow(flow) {
    this.setUiState({ flow });
  }

  toggleBaseline() {
    this.setUiState({ show_baseline: !this.uiState.show_baseline });
  }

  toggleLastLeg() {
    this.setUiState({ show_last_leg: !this.uiState.show_last_leg });
  }

  installControls() {
    return installControls(this);
  }

  updateControls() {
    return updateControls(this);
  }
}

export { ScenarioLeafletMap };
