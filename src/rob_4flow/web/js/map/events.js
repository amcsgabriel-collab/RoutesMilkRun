// events.js
import { setsIntersect } from "./utils.js";

export function emit(mapInstance, type, detail) {
  const message = { type, ...detail };

  mapInstance.container.dispatchEvent(
    new CustomEvent(type, { detail: message })
  );

  if (mapInstance.options.postToParent && window.parent) {
    window.parent.postMessage(message, "*");
  }
}

export function attachFeatureEvents(mapInstance, layer, featureId) {
  layer.on("mouseover", () => {
  mapInstance.removeFocusBox(layer);

  const groupIds = mapInstance.getFeatureGroupIds(featureId);

  if (
    !setsIntersect(groupIds, mapInstance.selectedGroupIds) &&
    !setsIntersect(groupIds, mapInstance.searchHighlightedIds || new Set())
  ) {
    mapInstance.applyStyleToIds(groupIds, "hover");
  }
});

  layer.on("mouseout", () => {
  mapInstance.removeFocusBox(layer);

  const groupIds = mapInstance.getFeatureGroupIds(featureId);

  if (
    !setsIntersect(groupIds, mapInstance.selectedGroupIds) &&
    !setsIntersect(groupIds, mapInstance.searchHighlightedIds || new Set())
  ) {
    mapInstance.applyStyleToIds(groupIds, "normal");
  }
});

  layer.on("contextmenu", (event) => {
    if (event.originalEvent) {
      event.originalEvent.preventDefault();
      event.originalEvent.stopPropagation();
    }

    const feature = mapInstance.features.get(featureId);

    mapInstance.emit("scenario-map-object-right-clicked", {
      payload: feature?.payload || {},
      position: {
        x: event.originalEvent?.clientX,
        y: event.originalEvent?.clientY,
      },
    });
  });

  layer.on("click", (event) => {
    if (event.originalEvent) {
      event.originalEvent.preventDefault();
      event.originalEvent.stopPropagation();
    }

    if (document.activeElement) {
      document.activeElement.blur();
    }

    mapInstance.selectFeature(featureId);

    const feature = mapInstance.features.get(featureId);
    window.selectedObject = feature?.payload || null;

    mapInstance.emit("scenario-map-object-selected", {
      payload: feature?.payload || {},
    });

    setTimeout(() => mapInstance.removeFocusBox(layer), 0);
  });
}