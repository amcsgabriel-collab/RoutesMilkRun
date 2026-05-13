export const DEFAULT_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

export const DEFAULT_TILE_OPTIONS = {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
};

export const DEFAULT_CENTER = [0, 0];

export const DEFAULT_ZOOM = 2;

export const DEFAULT_FIT_PADDING = [30, 30];

export const DEFAULT_ACTIVE_NETWORKS = ["Direct", "Hubs"];

export const ALLOWED_NETWORKS = new Set(["Direct", "Hubs"]);

export const DEFAULT_UI_STATE = {
  flow: "parts",
  show_baseline: false,
  show_last_leg: false,
  show_unassigned_shippers: true,
  active_networks: [...DEFAULT_ACTIVE_NETWORKS],
};

export function normalizeUiState(input = {}) {
  const flow = input.flow === "empties" ? "empties" : "parts";

  let activeNetworks =
    input.active_networks ||
    input.activeNetworks ||
    [...DEFAULT_ACTIVE_NETWORKS];

  if (!Array.isArray(activeNetworks)) {
    activeNetworks = Array.from(activeNetworks || []);
  }

  activeNetworks = activeNetworks.filter((network) =>
    ALLOWED_NETWORKS.has(network)
  );

  if (activeNetworks.length === 0) {
    activeNetworks = [...DEFAULT_ACTIVE_NETWORKS];
  }

  return {
    flow,
    show_baseline: Boolean(
      input.show_baseline ?? input.showBaseline ?? false
    ),
    show_last_leg: Boolean(
      input.show_last_leg ?? input.showLastLeg ?? false
    ),
    show_unassigned_shippers: Boolean(
      input.show_unassigned_shippers ?? input.showUnassignedShippers ?? true
    ),
    active_networks: activeNetworks,
  };
}


export function fitBounds(map, bounds, padding) {
  if (!Array.isArray(bounds) || bounds.length === 0) return;

  if (bounds.length === 1) {
    map.setView(bounds[0], 10);
    return;
  }

  map.fitBounds(bounds, { padding });
}