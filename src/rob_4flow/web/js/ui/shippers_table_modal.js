import {
  openTableModal,
  text,
  formatNumber,
  formatCoordinates
} from "./table_modal.js";

export async function openShippersModal() {
  await openTableModal({
    htmlPath: "../views_html/shippers_table_modal.html",
    endpoint: "/api/shippers",
    tbodyId: "shippers-tbody",
    errorId: "shippers-error",
    closeId: "shippers-close",
    refreshId: "shippers-refresh",
    flowName: "shippers-flow",
    topFilterId: "shippers-filter",

    searchKeys: ["name", "cofor"],

    emptyText: () => "No shippers",

    mapItem: (s, flow) => {
      const demand = flow === "empties" ? s.empties_demand : s.parts_demand;

      return {
        name: s.name,
        cofor: s.cofor,
        weight: demand?.weight,
        volume: demand?.volume,
        loading_meters: demand?.loading_meters,
        allocation_name: s.allocation?.[flow]?.name,
        allocation_type: s.allocation?.[flow]?.type,
        coordinates: s.coordinates,
        original_network: s.original_network
      };
    },

    columns: [
      { key: "name", render: r => text(r.name) },
      { key: "cofor", render: r => text(r.cofor) },
      { key: "weight", align: "right", render: r => formatNumber(r.weight) },
      { key: "volume", align: "right", render: r => formatNumber(r.volume) },
      { key: "loading_meters", align: "right", render: r => formatNumber(r.loading_meters) },
      { key: "allocation_name", render: r => text(r.allocation_name) },
      { key: "allocation_type", render: r => text(r.allocation_type) },
      { key: "original_network", render: r => text(r.original_network) },
      { key: "coordinates", align: "center", render: r => formatCoordinates(r.coordinates) }
    ]
  });
}