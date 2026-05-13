const DEFAULT_VECTOR_STYLES = {
  plant: {
    radius: 8,
    weight: 1,
    opacity: 1,
    fillOpacity: 0.7,
  },
  hub: {
    radius: 6,
    weight: 2,
    opacity: 1,
    fillOpacity: 0.7,
  },
  hubPoint: {
    radius: 4,
    weight: 0.5,
    opacity: 1,
    fillOpacity: 0.7,
  },
  directStopMain: {
    radius: 5.5,
    weight: 1,
    opacity: 1,
    fillOpacity: 0.85,
  },
  directStopExtra: {
    radius: 4,
    weight: 0.5,
    opacity: 1,
    fillOpacity: 0.7,
  },
  route: {
    weight: 1.5,
    opacity: 0.5,
  },
  hubLinehaul: {
    weight: 2,
    opacity: 1,
  },
  directStatus: {
    radius: 7,
    weight: 2,
    opacity: 1,
    fillOpacity: 1,
  }
};

export function getFeatureVectorStyle(feature, styleName = "normal") {
  let style = {};

  if (feature.kind === "plant") {
    style = DEFAULT_VECTOR_STYLES.plant;
  } else if (feature.kind === "hub") {
    style = DEFAULT_VECTOR_STYLES.hub;
  } else if (feature.subtype === "hub-point") {
    style = DEFAULT_VECTOR_STYLES.hubPoint;
  } else if (feature.subtype === "direct-stop") {
    const isMain = feature.id.includes(":stop:1:");
    style = isMain
      ? DEFAULT_VECTOR_STYLES.directStopMain
      : DEFAULT_VECTOR_STYLES.directStopExtra;
  } else if (feature.subtype === "hub-linehaul") {
    style = DEFAULT_VECTOR_STYLES.hubLinehaul;
  } else if (feature.subtype === "unassigned-shipper") {
    style = DEFAULT_VECTOR_STYLES.hubPoint;
  } else if (feature.subtype === "route-status") {
    style = DEFAULT_VECTOR_STYLES.directStatus;
  } else {
    style = DEFAULT_VECTOR_STYLES.route;
  }

  style = {
    ...style,
    ...getLeafletFeatureColors(feature),
  };

  if (styleName === "hover") {
    return {
      ...style,
      weight: (style.weight || 1) + 2,
      opacity: 0.9,
    };
  }

  if (styleName === "selected") {
    return {
      ...style,
      radius: style.radius !== undefined ? style.radius + 3 : undefined,
      weight: (style.weight || 1) + 5,
      opacity: 1,
    };
  }

  return { ...style };
}

function getLeafletFeatureColors(feature) {
  if (feature.kind === "plant") {
    return {
      color: "#ce2900",
      fillColor: "#ce2900",
    };
  }

  if (feature.kind === "hub") {
    return {
      color: "black",
      fillColor: "#e27115",
    };
  }

  if (feature.subtype === "hub-linehaul") {
    return {
      color: feature.baseline
        ? "#a3990b"
        : "#e27115",
    };
  }

  if (feature.subtype === "hub-first-leg") {
      const isBaseline = feature.baseline === true || feature.payload?.baseline === true;
      const isNew = feature.payload?.is_new === true;

      return {
        color: isBaseline
          ? "#8a7f08"
          : isNew
            ? "#fffb00"
            : "#a3990b",
      };
    }

  if (feature.subtype === "direct" || feature.subtype === "direct-last-leg") {
    return {
      color: feature.payload?.is_new_pattern
        ? "#ff31ff"
        : "#00a2ff",
    };
  }

  if (feature.subtype === "unassigned-shipper") {
  return {
    color: "black",
    fillColor: feature.baseline
    ? "#6b7280"
    : "#9ca3af",
    };
  }

  if (feature.subtype === "route-status") {
  return {
    color: "black",
    fillColor: feature.payload?.status === "blocked"
      ? "#ef4444"
      : "#facc15",
  };
 }

  if (feature.subtype === "hub-point") {
  const isBaseline = feature.baseline === true || feature.payload?.baseline === true;
  const isNew = feature.payload?.is_new === true;

  return {
    color: "black",
    fillColor: isBaseline
      ? "#8a7f08"
      : isNew
        ? "#fffb00"
        : "#a3990b",
  };
}


if (feature.subtype === "direct-stop") {
  const isMain = feature.id.includes(":stop:1:");
  const isBaseline = feature.baseline === true || feature.payload?.baseline === true;
  const isNew = feature.payload?.is_new === true;

  if (isBaseline) {
    return {
      color: "black",
      fillColor: isMain ? "#1e3a8a" : "#64748b",
    };
  }

  return {
    color: "black",
    fillColor: isMain
      ? isNew ? "#4b0090" : "#0033ff"
      : isNew ? "#ff31ff" : "#00a2ff",
  };
}
}

export function createLayer(mapInstance, feature, options = {}) {
  const geometry = feature.geometry || {};
  const normalStyle = getFeatureVectorStyle(feature, "normal");

  const cssClassName = getFeatureClass(feature);
  const fullClassName = feature.lastLeg
    ? `${cssClassName} scenario-map-last-leg`
    : cssClassName;

  const layerOptions = {
  ...(feature.options || {}),
  ...normalStyle,
  className: fullClassName,
  interactive: feature.interactive !== false,
};

  if (feature.pane) {
    layerOptions.pane = feature.pane;
  }

  let layer;

  if (geometry.type === "Point") {
    if (feature.iconHtml || feature.markerType === "divIcon") {
      const icon = L.divIcon({
        html: feature.iconHtml || "",
        className: feature.iconClassName || `scenario-map-div-icon ${fullClassName}`,
        iconSize: feature.iconSize || [16, 16],
        iconAnchor: feature.iconAnchor || [8, 16],
      });

      layer = L.marker(geometry.coordinates, {
        icon,
        interactive: feature.interactive !== false,
        keyboard: false,
        pane: feature.pane || "iconPane",
        ...(feature.options || {}),
      });
    } else {
      layer = L.circleMarker(geometry.coordinates, layerOptions);
    }
  } else if (geometry.type === "LineString") {
    layer = L.polyline(geometry.coordinates || [], layerOptions);
  } else {
    throw new Error(`Unsupported scenario map geometry type: ${geometry.type}`);
  }

  layer.__scenarioFeatureId = feature.id;

  if (feature.tooltipHtml) {
    layer.bindTooltip(feature.tooltipHtml, {
      sticky: true,
      ...(feature.tooltipOptions || {}),
    });
  }

  layer.on("add", () => {
    removeFocusBox(layer);
    applyFeatureCssClass(layer, feature);
  });

  if (!options.base && feature.interactive !== false) {
    mapInstance.attachFeatureEvents(layer, feature.id);
  }

  return layer;
}

export function applyStyle(layer, style) {
  if (!layer || !style) return;

  if (layer.setStyle) {
    const vectorStyle = { ...style };
    delete vectorStyle.radius;
    layer.setStyle(vectorStyle);
  }

  if (layer.setRadius && style.radius !== undefined) {
    layer.setRadius(style.radius);
  }
}

export function removeFocusBox(layer) {
  const element = layer?.getElement?.();
  if (!element) return;

  if (element.blur) element.blur();
  element.removeAttribute("tabindex");
  element.style.outline = "none";
}

function getFeatureClass(feature) {
  if (feature.kind === "plant") return "scenario-map-plant";
  if (feature.kind === "hub") return "scenario-map-hub";

  if (feature.subtype === "hub-linehaul") {
    return feature.baseline
      ? "scenario-map-hub-linehaul-baseline"
      : "scenario-map-hub-linehaul";
  }

  if (feature.subtype === "hub-first-leg") {
    return feature.payload?.shippers?.[0]?.original_network === "direct"
      ? "scenario-map-hub-first-leg-new"
      : "scenario-map-hub-first-leg";
  }

  if (feature.subtype === "hub-point") {
  const isBaseline = feature.baseline === true || feature.payload?.baseline === true;
  const isNew = feature.payload?.is_new === true;

  if (isBaseline) return "scenario-map-hub-shipper-baseline";

  return isNew
    ? "scenario-map-hub-shipper-new"
    : "scenario-map-hub-shipper-original";
}

  if (feature.subtype === "direct" || feature.subtype === "direct-last-leg") {
    return feature.payload?.is_new_pattern
      ? "scenario-map-direct-route-new"
      : "scenario-map-direct-route-original";
  }

  if (feature.subtype === "unassigned-shipper") {
  return feature.baseline
    ? "scenario-map-shipper-unassigned-baseline"
    : "scenario-map-shipper-unassigned";
  }

  if (feature.subtype === "route-status") {
  return feature.payload?.status === "blocked"
    ? "scenario-map-route-status-blocked"
    : "scenario-map-route-status-locked";
  }

  if (feature.subtype === "direct-stop") {
      const isMain = feature.id.includes(":stop:1:");
      const isBaseline = feature.baseline === true || feature.payload?.baseline === true;
      const isNew = feature.payload?.is_new === true;

      if (isBaseline && isMain) return "scenario-map-direct-stop-main-baseline";
      if (isBaseline) return "scenario-map-direct-stop-baseline";

      if (isMain && isNew) return "scenario-map-direct-stop-main-new";
      if (isMain) return "scenario-map-direct-stop-main-original";
      if (isNew) return "scenario-map-direct-stop-new";

      return "scenario-map-direct-stop-original";
    }
  return "";
}

export function applyFeatureCssClass(layer, feature) {
  const element = layer?.getElement?.();
  if (!element) return;

  const cssClassName = getFeatureClass(feature);
  const fullClassName = feature.lastLeg
    ? `${cssClassName} scenario-map-last-leg`
    : cssClassName;

  element.classList.add(...fullClassName.split(" ").filter(Boolean));
}