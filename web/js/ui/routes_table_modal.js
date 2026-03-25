// shippersModal.js
import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

// public export
export async function openRoutesModal() {
  const html = await loadHtml("../views_html/routes_table_modal.html");
  openModal(html);
  wireRoutesModal();
  await loadAndRenderRoutes();
}

function $id(id){ return document.getElementById(id); }

function formatNumber(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPercentage(n) {
  if (n == null) return "—";
  const num = Number(n) * 100;
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function loadAndRenderRoutes() {
  const tbody = $id("routes-tbody");
  tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Loading…</td></tr>`;

  let list;
  try {
    list = await apiGet("/api/routes");
    if (!Array.isArray(list)) list = [];
  } catch (e) {
    err.textContent = "Failed to load routes: " + (e.message || e);
    err.style.display = "block";
    tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
    return;
  }

  const rows = list
    .map((r, i) => {
      return `
        <tr class="sh-row" data-idx="${i}" data-name="${escapeHtml(r.name||"")}" style="cursor:default">
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(r.name||"")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(r.vehicle||"")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(r.frequency||"")}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(r.base_cost)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(r.stop_cost)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatPercentage(r.weight_utilization)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatPercentage(r.volume_utilization)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatPercentage(r.loading_meters_utilization)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${r.shippers && r.shippers.length? r.shippers.join(", "): "—"}</td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">No routes</td></tr>`;

    tbody.innerHTML = rows;
  }


function wireRoutesModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal)
  document.getElementById("routes-close").addEventListener("click", closeModal);
}
