import {
  openTableModal,
  text,
  formatNumber,
  formatCoordinates
} from "./table_modal.js";

export async function openHubsModal() {
  await openTableModal({
    htmlPath: "../views_html/hubs_table_modal.html",
    endpoint: "/api/hubs",
    tbodyId: "hubs-tbody",
    errorId: "hubs-error",
    closeId: "hubs-close",
    flowName: "hubs-flow",

    searchKeys: ["name", "cofor", "carrier"],

    emptyText: () => "No Hubs",

    validate: validateHub,

    mapItem: (h, flow) => {
      const summary = h[flow];

      return {
        name: h.name,
        cofor: h.cofor,
        carrier: h.carrier,
        first_leg_cost: summary.first_leg_cost,
        linehaul_frequency: summary.linehaul_frequency,
        linehaul_cost: summary.linehaul_cost,
        linehaul_weight: summary.linehaul_weight,
        linehaul_volume: summary.linehaul_volume,
        linehaul_loading_meters: summary.linehaul_loading_meters,
        coordinates: h.coordinates
      };
    },

    columns: [
      { key: "name", render: r => text(r.name) },
      { key: "cofor", render: r => text(r.cofor) },
      { key: "carrier", render: r => text(r.carrier) },
      { key: "first_leg_cost", align: "right", render: r => formatNumber(r.first_leg_cost) },
      { key: "linehaul_frequency", render: r => text(r.linehaul_frequency) },
      { key: "linehaul_cost", align: "right", render: r => formatNumber(r.linehaul_cost) },
      { key: "linehaul_weight", align: "right", render: r => formatNumber(r.linehaul_weight) },
      { key: "linehaul_volume", align: "right", render: r => formatNumber(r.linehaul_volume) },
      { key: "linehaul_loading_meters", align: "right", render: r => formatNumber(r.linehaul_loading_meters) },
      { key: "coordinates", align: "center", render: r => formatCoordinates(r.coordinates) }
    ]
  });
}

function validateHubSummary(summary, flow, hubName) {
  if (!summary || typeof summary !== "object") {
    throw new Error(`Invalid hub payload for "${hubName}": missing "${flow}" summary`);
  }

  const requiredFields = [
    "first_leg_cost",
    "linehaul_frequency",
    "linehaul_cost",
    "linehaul_weight",
    "linehaul_volume",
    "linehaul_loading_meters",
  ];

  for (const field of requiredFields) {
    if (!(field in summary)) {
      throw new Error(`Invalid hub payload for "${hubName}": missing "${flow}.${field}"`);
    }
  }
}

function validateHub(h) {
  if (!h || typeof h !== "object") {
    throw new Error("Invalid hub payload: hub entry is not an object");
  }

  if (!("name" in h)) throw new Error('Invalid hub payload: missing "name"');
  if (!("cofor" in h)) throw new Error(`Invalid hub payload for "${h.name ?? "unknown"}": missing "cofor"`);
  if (!("coordinates" in h)) throw new Error(`Invalid hub payload for "${h.name ?? "unknown"}": missing "coordinates"`);

  validateHubSummary(h.parts, "parts", h.name ?? "unknown");
  validateHubSummary(h.empties, "empties", h.name ?? "unknown");
}