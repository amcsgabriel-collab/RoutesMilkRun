import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet, apiPost, apiDelete } from "../api.js";

// public export
export async function openVehiclesModal() {
  const html = await loadHtml("../views_html/vehicles_table_modal.html");
  openModal(html);
  wireVehiclesModal();
  await loadAndRenderVehicles();
}

function $id(id){ return document.getElementById(id); }

function formatNumber(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function loadAndRenderVehicles() {
  const tbody = $id("vehicles-tbody");
  tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Loading…</td></tr>`;

  let list;
  try {
    list = await apiGet("/api/vehicles");
    if (!Array.isArray(list)) list = [];
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
    return;
  }

  const rows = list.map((v, i) => {
    const id = escapeHtml(v.id || "");
    return `
      <tr class="sh-row" data-idx="${i}" data-name="${id}" style="cursor:default">
        <td style="padding:8px;text-align:center;border-bottom:1px solid #f2f4f7">
          <input type="checkbox" class="vehicle-select" value="${id}" />
        </td>
        <td style="padding:8px;border-bottom:1px solid #f2f4f7">${id}</td>
        <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(v.weight)}</td>
        <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(v.volume)}</td>
        <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(v.loading_meters)}</td>
      </tr>
    `;
  }).join("") || `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">No vehicles</td></tr>`;

  tbody.innerHTML = rows;
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
  await loadAndRenderVehicles();
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

function wireVehiclesModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("vehicles-close").addEventListener("click", closeModal);

  document.getElementById("vehicles-add").addEventListener("click", openAddVehicleModal);
  document.getElementById("vehicles-delete").addEventListener("click", deleteSelectedVehicles);

  document.getElementById("vehicles-select-all").addEventListener("change", (e) => {
    document.querySelectorAll(".vehicle-select").forEach(cb => {
      cb.checked = e.target.checked;
    });
  });
}

function wireAddVehicleModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("vehicle-add-cancel").addEventListener("click", openVehiclesModal);
  document.getElementById("vehicle-add-save").addEventListener("click", addVehicle);
}