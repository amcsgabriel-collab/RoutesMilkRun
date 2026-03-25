// shippersModal.js
import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

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
    err.textContent = "Failed to load vehicles: " + (e.message || e);
    err.style.display = "block";
    tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
    return;
  }

  const rows = list
    .map((v, i) => {
      return `
        <tr class="sh-row" data-idx="${i}" data-name="${escapeHtml(v.id||"")}" style="cursor:default">
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(v.id||"")}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(v.weight)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(v.volume)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(v.loading_meters)}</td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">No vehicles</td></tr>`;

    tbody.innerHTML = rows;
  }

function wireVehiclesModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal)
  document.getElementById("vehicles-close").addEventListener("click", closeModal);
}
