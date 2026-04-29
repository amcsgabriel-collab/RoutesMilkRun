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

    topFilterId: "routes-filter",
    searchKeys: ["name", "vehicle", "roundtrip_id", "shippers_search"],

    emptyText: flow => `No ${flow} routes`,

    mapItem: (trip, flow, i) => {
  const route = flow === "empties" ? trip.empties_route : trip.parts_route;
  if (!route) return null;

  return {
    _rowId: `${flow}-${trip.roundtrip_id}-${route.name}-${i}`,
    name: route.name,
    roundtrip_id: trip.roundtrip_id,
    frequency: trip.frequency,
    vehicle: route.vehicle,
    base_cost: route.base_cost,
    stop_cost: route.stop_cost,
    weight_utilization: route.weight_utilization,
    volume_utilization: route.volume_utilization,
    loading_meters_utilization: route.loading_meters_utilization,
    weight: route.weight,
    volume: route.volume,
    loading_meters: route.loading_meters,

    // useful for top/global filtering
    shippers_search: route.shippers?.map(s => s.name || s.cofor || s).join(" ") || "",

    children: (route.shippers || []).map((s, idx) => ({
      shipper_cofor: s.cofor,
      weight: s.weight,
      volume: s.volume,
      loading_meters: s.loading_meters,
      allocation_percentage: s.allocation_percentage,
      stop_order: s.stop_order ?? idx + 1
    }))
  };
},

    columns: [
  {
    key: "_expand",
    align: "center",
    render: r => r.children?.length
      ? `<button class="table-expand-btn" data-expand-row="${r._rowId}">${r._expanded ? "−" : "+"}</button>`
      : ""
  },
  { key: "name", render: r => text(r.name) },
  { key: "roundtrip_id", render: r => formatInteger(r.roundtrip_id) },
  { key: "frequency", align: "center", render: r => formatInteger(r.frequency) },
  { key: "vehicle", render: r => text(r.vehicle) },
  { key: "base_cost", align: "right", render: r => formatNumber(r.base_cost) },
  { key: "stop_cost", align: "right", render: r => formatNumber(r.stop_cost) },
  { key: "weight", align: "right", render: r => formatNumber(r.weight) },
  { key: "volume", align: "right", render: r => formatNumber(r.volume) },
  { key: "loading_meters", align: "right", render: r => formatNumber(r.loading_meters) },
  { key: "weight_utilization", align: "right", render: r => formatNumber(r.weight_utilization) },
  { key: "volume_utilization", align: "right", render: r => formatNumber(r.volume_utilization) },
  { key: "loading_meters_utilization", align: "right", render: r => formatNumber(r.loading_meters_utilization) }

],

childColumns: [
  { key: "shipper_cofor", render: r => text(r.shipper_cofor) },
  { key: "weight", align: "right", render: r => formatNumber(r.weight) },
  { key: "volume", align: "right", render: r => formatNumber(r.volume) },
  { key: "loading_meters", align: "right", render: r => formatNumber(r.loading_meters) },
  { key: "allocation_percentage", align: "right", render: r => `${formatNumber(r.allocation_percentage)}%` },
  { key: "stop_order", align: "center", render: r => formatInteger(r.stop_order) }
],

childRender: {
  _expand: r => formatInteger(r.stop_order),
  name: r => text(r.shipper_cofor),
  roundtrip_id: r => `${formatNumber(r.allocation_percentage)}%`,
  weight: r => formatNumber(r.weight),
  volume: r => formatNumber(r.volume),
  loading_meters: r => formatNumber(r.loading_meters)
}

  });
}