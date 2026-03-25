// shippersModal.js
import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

// public export
export async function openHubsModal() {
  const html = await loadHtml("../views_html/hubs_table_modal.html");
  openModal(html);
  document.getElementById("hubs-close").addEventListener("click", closeModal);
  await loadAndRenderHubs();
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

function formatCoordinates(coords) {
    if (!coords) return "—";

    // If coords is already [lat, lon]
    if (Array.isArray(coords) && coords.length >= 2) {
    const lat = Number(coords[0]).toFixed(5);
    const lon = Number(coords[1]).toFixed(5);
    return `(${lat}, ${lon})`;
    }

    // If coords is an object like {lat:..., lon:...}
    if (typeof coords === "object") {
    const lat = Number(coords.lat ?? coords.latitude).toFixed(5);
    const lon = Number(coords.lon ?? coords.longitude).toFixed(5);
    return `(${lat}, ${lon})`;
    }

    return "—";
}

async function loadAndRenderHubs() {
  const tbody = $id("hubs-tbody");
  tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Loading…</td></tr>`;

  let list;
  try {
    list = await apiGet("/api/hubs");
    if (!Array.isArray(list)) list = [];
  } catch (e) {
    err.textContent = "Failed to load hubs: " + (e.message || e);
    err.style.display = "block";
    tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
    return;
  }

  const rows = list
    .map((h, i) => {
      const coords = h.coordinates ? escapeHtml(String(h.coordinates)) : "";
      return `
        <tr class="sh-row" data-idx="${i}" data-name="${escapeHtml(h.name||"")}" style="cursor:default">
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(h.name||"")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(h.cofor||"")}</td>
           <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(h.first_leg_cost)}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(h.linehaul_frequency||"")}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(h.linehaul_cost)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(h.linehaul_weight)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(h.linehaul_volume)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(h.linehaul_loading_meters)}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #f2f4f7">${formatCoordinates(coords)}</td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="5" style="padding:20px;text-align:center;color:#6b7280">No Hubs</td></tr>`;

    tbody.innerHTML = rows;
  }
