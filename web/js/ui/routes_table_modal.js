import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

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

function formatInteger(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}


async function loadAndRenderRoutes() {
  const tbody = $id("routes-tbody");
  const err = $id("routes-error");
  const flow = document.querySelector('input[name="routes-flow"]:checked')?.value || "parts";

  err.style.display = "none";
  tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#6b7280">Loading…</td></tr>`;

  let list;
  try {
    list = await apiGet("/api/routes");
    if (!Array.isArray(list)) list = [];
  } catch (e) {
    err.textContent = "Failed to load trips: " + (e.message || e);
    err.style.display = "block";
    tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
    return;
  }

  const rows = list
    .map((trip, i) => {
      const route = flow === "empties" ? trip.empties_route : trip.parts_route;
      if (!route) return "";

      return `
        <tr class="sh-row" data-idx="${i}" data-name="${escapeHtml(route.name || "")}" style="cursor:default">
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(route.name || "")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(route.vehicle || "")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${formatInteger(trip.roundtrip_id)}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #f2f4f7">${formatInteger(trip.frequency)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(route.base_cost)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(route.stop_cost)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(route.weight_utilization)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(route.volume_utilization)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(route.loading_meters_utilization)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${route.shippers?.length ? route.shippers.join(", ") : "—"}</td>
        </tr>
      `;
    })
    .filter(Boolean)
    .join("") || `<tr><td colspan="9" style="padding:20px;text-align:center;color:#6b7280">No ${flow} routes</td></tr>`;

  tbody.innerHTML = rows;
}

function wireRoutesModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("routes-close").addEventListener("click", closeModal);

  document.querySelectorAll('input[name="routes-flow"]').forEach(el => {
    el.addEventListener("change", () => loadAndRenderRoutes());
  });
}