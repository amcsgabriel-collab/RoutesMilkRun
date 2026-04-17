// shippersModal.js
import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

// public export
export async function openShippersModal() {
  const html = await loadHtml("../views_html/shippers_table_modal.html");
  openModal(html);
  wireShippersModal();
  await loadAndRenderShippers();
}

function $id(id){ return document.getElementById(id); }

function formatNumber(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function loadAndRenderShippers() {
  const tbody = $id("shippers-tbody");
  const err = $id("shippers-error");
  const flow = document.querySelector('input[name="shippers-flow"]:checked')?.value || "parts";

  err.style.display = "none";
  tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:#6b7280">Loading…</td></tr>`;

  let list;
  try {
    list = await apiGet("/api/shippers");
    if (!Array.isArray(list)) list = [];
  } catch (e) {
    err.textContent = "Failed to load shippers: " + (e.message || e);
    err.style.display = "block";
    tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
    return;
  }

  const filter = ($id("shippers-filter")?.value || "").trim().toLowerCase();

  const rows = list
    .filter(s =>
      !filter ||
      (s.name || "").toLowerCase().includes(filter) ||
      (s.cofor || "").toLowerCase().includes(filter)
    )
    .map((s, i) => {
      const demand = flow === "empties" ? s.empties_demand : s.parts_demand;

      return `
        <tr class="sh-row" data-idx="${i}" data-name="${escapeHtml(s.name || "")}" style="cursor:default">
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(s.name || "")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(s.cofor || "")}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(demand?.weight)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(demand?.volume)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(demand?.loading_meters)}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #f2f4f7">${formatCoordinates(s.coordinates)}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(s.original_network || "")}</td>
        </tr>
      `;
    }).join("") || `<tr><td colspan="7" style="padding:20px;text-align:center;color:#6b7280">No shippers</td></tr>`;

  tbody.innerHTML = rows;
}

function formatCoordinates(coords) {
  if (!coords) return "—";

  if (typeof coords === "string") {
    return coords;
  }

  if (Array.isArray(coords) && coords.length >= 2) {
    const lat = Number(coords[0]).toFixed(5);
    const lon = Number(coords[1]).toFixed(5);
    return `(${lat}, ${lon})`;
  }

  if (typeof coords === "object") {
    const lat = Number(coords.lat ?? coords.latitude).toFixed(5);
    const lon = Number(coords.lon ?? coords.longitude).toFixed(5);
    return `(${lat}, ${lon})`;
  }

  return "—";
}

function wireShippersModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("shippers-close").addEventListener("click", closeModal);
  $id("shippers-refresh")?.addEventListener("click", () => loadAndRenderShippers());

  const filter = $id("shippers-filter");
  if (filter) {
    filter.addEventListener("input", () => {
      if (filter._t) clearTimeout(filter._t);
      filter._t = setTimeout(() => loadAndRenderShippers(), 220);
    });
  }

  document.querySelectorAll('input[name="shippers-flow"]').forEach(el => {
    el.addEventListener("change", () => loadAndRenderShippers());
  });
}