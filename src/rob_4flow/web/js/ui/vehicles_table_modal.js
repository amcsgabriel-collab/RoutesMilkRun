import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiPost, apiDelete } from "../api.js";

import {
  openTableModal,
  $id,
  text,
  formatNumber
} from "./table_modal.js";

export async function openVehiclesModal() {
  await openTableModal({
    htmlPath: "../views_html/vehicles_table_modal.html",
    endpoint: "/api/vehicles",
    tbodyId: "vehicles-tbody",
    closeId: "vehicles-close",

    searchKeys: ["id"],

    emptyText: () => "No vehicles",

    mapItem: v => ({
      id: v.id,
      weight: v.weight,
      volume: v.volume,
      loading_meters: v.loading_meters
    }),

    columns: [
      {
        key: "select",
        align: "center",
        render: r => `<input type="checkbox" class="vehicle-select" value="${escapeHtml(r.id || "")}" />`
      },
      { key: "id", render: r => text(r.id) },
      { key: "weight", align: "right", render: r => formatNumber(r.weight) },
      { key: "volume", align: "right", render: r => formatNumber(r.volume) },
      { key: "loading_meters", align: "right", render: r => formatNumber(r.loading_meters) }
    ],

    wireExtra: ({ loadAndRender }) => {
      $id("vehicles-add")?.addEventListener("click", openAddVehicleModal);

      $id("vehicles-delete")?.addEventListener("click", async () => {
        await deleteSelectedVehicles();
        await loadAndRender();
      });

      $id("vehicles-select-all")?.addEventListener("change", e => {
        document.querySelectorAll(".vehicle-select").forEach(cb => {
          cb.checked = e.target.checked;
        });
      });
    }
  });
}

function getSelectedVehicleIds() {
  return Array.from(document.querySelectorAll(".vehicle-select:checked"))
    .map(cb => cb.value)
    .filter(Boolean);
}

async function deleteSelectedVehicles() {
  const ids_to_delete = getSelectedVehicleIds();
  if (!ids_to_delete.length) return;

  await apiDelete("/api/vehicles", ids_to_delete);
}

async function openAddVehicleModal() {
  const html = await loadHtml("../views_html/vehicles_add_modal.html");
  openModal(html);
  wireAddVehicleModal();
}

async function addVehicle() {
  const new_vehicle = {
    id: $id("vehicle-id").value.trim(),
    weight: Number($id("vehicle-weight").value),
    volume: Number($id("vehicle-volume").value),
    loading_meters: Number($id("vehicle-loading-meters").value)
  };

  await apiPost("/api/vehicles", new_vehicle);
  await openVehiclesModal();
}

function wireAddVehicleModal() {
  $id("modal-close")?.addEventListener("click", closeModal);
  $id("vehicle-add-cancel")?.addEventListener("click", openVehiclesModal);
  $id("vehicle-add-save")?.addEventListener("click", addVehicle);
}