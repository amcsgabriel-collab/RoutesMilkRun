import {
  openTableModal,
  text,
  formatNumber,
  formatInteger
} from "./table_modal.js";

export async function openRoutesModal() {
  await openTableModal({
    htmlPath: "../views_html/routes_table_modal.html",
    endpoint: "/api/routes",
    tbodyId: "routes-tbody",
    errorId: "routes-error",
    closeId: "routes-close",
    flowName: "routes-flow",

    searchKeys: ["name", "vehicle", "roundtrip_id", "shippers"],

    emptyText: flow => `No ${flow} routes`,

    mapItem: (trip, flow) => {
      const route = flow === "empties" ? trip.empties_route : trip.parts_route;
      if (!route) return null;

      return {
        name: route.name,
        vehicle: route.vehicle,
        roundtrip_id: trip.roundtrip_id,
        frequency: trip.frequency,
        base_cost: route.base_cost,
        stop_cost: route.stop_cost,
        weight_utilization: route.weight_utilization,
        volume_utilization: route.volume_utilization,
        loading_meters_utilization: route.loading_meters_utilization,
        shippers: route.shippers?.length ? route.shippers.join(", ") : "—"
      };
    },

    columns: [
      { key: "name", render: r => text(r.name) },
      { key: "vehicle", render: r => text(r.vehicle) },
      { key: "roundtrip_id", render: r => formatInteger(r.roundtrip_id) },
      { key: "frequency", align: "center", render: r => formatInteger(r.frequency) },
      { key: "base_cost", align: "right", render: r => formatNumber(r.base_cost) },
      { key: "stop_cost", align: "right", render: r => formatNumber(r.stop_cost) },
      { key: "weight_utilization", align: "right", render: r => formatNumber(r.weight_utilization) },
      { key: "volume_utilization", align: "right", render: r => formatNumber(r.volume_utilization) },
      { key: "loading_meters_utilization", align: "right", render: r => formatNumber(r.loading_meters_utilization) },
      { key: "shippers", align: "right", render: r => text(r.shippers) }
    ]
  });
}