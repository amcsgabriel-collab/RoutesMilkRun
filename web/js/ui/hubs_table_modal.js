import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

// public export
export async function openHubsModal() {
  const html = await loadHtml("../views_html/hubs_table_modal.html");
  openModal(html);
  wireHubsModal();
  await loadAndRenderHubs();
}

function $id(id){ return document.getElementById(id); }

function formatNumber(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

function validateHubSummary(summary, flow, hubName) {
  if (!summary || typeof summary !== "object") {
    throw new Error(`Invalid hub payload for "${hubName}": missing "${flow}" summary`);
  }

  const requiredFields = [
    "first_leg_cost",
    "linehaul_frequency",
    "linehaul_cost",
    "linehaul_weight",
    "linehaul_volume",
    "linehaul_loading_meters",
  ];

  for (const field of requiredFields) {
    if (!(field in summary)) {
      throw new Error(`Invalid hub payload for "${hubName}": missing "${flow}.${field}"`);
    }
  }
}

function validateHub(h) {
  if (!h || typeof h !== "object") {
    throw new Error("Invalid hub payload: hub entry is not an object");
  }

  if (!("name" in h)) throw new Error('Invalid hub payload: missing "name"');
  if (!("cofor" in h)) throw new Error(`Invalid hub payload for "${h.name ?? "unknown"}": missing "cofor"`);
  if (!("coordinates" in h)) throw new Error(`Invalid hub payload for "${h.name ?? "unknown"}": missing "coordinates"`);

  validateHubSummary(h.parts, "parts", h.name ?? "unknown");
  validateHubSummary(h.empties, "empties", h.name ?? "unknown");
}

async function loadAndRenderHubs() {
  const tbody = $id("hubs-tbody");
  const err = $id("hubs-error");
  const flow = document.querySelector('input[name="hubs-flow"]:checked')?.value || "parts";

  if (err) {
    err.style.display = "none";
    err.textContent = "";
  }

  tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#6b7280">Loading…</td></tr>`;

  try {
    const list = await apiGet("/api/hubs");

    if (!Array.isArray(list)) {
      throw new Error("Invalid hubs payload: expected an array");
    }

    list.forEach(validateHub);

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#6b7280">No Hubs</td></tr>`;
      return;
    }

    const rows = list.map((h, i) => {
      const summary = h[flow];

      return `
        <tr class="sh-row" data-idx="${i}" data-name="${escapeHtml(h.name || "")}" style="cursor:default">
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(h.name || "")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(h.cofor || "")}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(h.carrier || "")}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(summary.first_leg_cost)}</td>
          <td style="padding:8px;border-bottom:1px solid #f2f4f7">${escapeHtml(String(summary.linehaul_frequency ?? ""))}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(summary.linehaul_cost)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(summary.linehaul_weight)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(summary.linehaul_volume)}</td>
          <td style="padding:8px;text-align:right;padding-right:12px;border-bottom:1px solid #f2f4f7">${formatNumber(summary.linehaul_loading_meters)}</td>
          <td style="padding:8px;text-align:center;border-bottom:1px solid #f2f4f7">${formatCoordinates(h.coordinates)}</td>
        </tr>
      `;
    }).join("");

    tbody.innerHTML = rows;
  } catch (e) {
    if (err) {
      err.textContent = e.message || String(e);
      err.style.display = "block";
    }

    tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#6b7280">Error</td></tr>`;
  }
}

function wireHubsModal() {
  document.getElementById("modal-close")?.addEventListener("click", closeModal);
  document.getElementById("hubs-close")?.addEventListener("click", closeModal);

  document.querySelectorAll('input[name="hubs-flow"]').forEach(el => {
    el.addEventListener("change", () => loadAndRenderHubs());
  });
}