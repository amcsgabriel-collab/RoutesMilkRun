// Configures the route "locking" / "blocking" interface.

import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet, apiPost } from "../api.js";

// Setting 2 entry-points, with a common "denominator", only differing in mode.
export async function openLockRoutesModal() {
  await openLockBlockRoutesModal("lock");
}

export async function openBlockRoutesModal() {
  await openLockBlockRoutesModal("block");
}

async function openLockBlockRoutesModal(mode) {
  const html = await loadHtml("../views_html/lock_block_routes_modal.html");
  openModal(html, "modal-large");
  wireModal(mode);
  await refreshRoutesLists(mode);
}

function setError(msg) {
  const errorLog = document.getElementById("lbr-error");
  if (!errorLog) return;
  if (!msg) { errorLog.style.display = "none"; errorLog.textContent = ""; return; }
  errorLog.textContent = msg;
  errorLog.style.display = "block";
}

function wireModal(mode) {
  // Dynamic title labels based on mode.
  document.getElementById("lbr-title").textContent = mode === "lock" ? "ROB v0 - Lock Routes" : "ROB v0 - Block Routes";
  document.getElementById("lbr-left-title").textContent = "Current Routes";
  document.getElementById("lbr-right-title").textContent = mode === "lock" ? "Locked Routes" : "Blocked Routes";

  // shared modal close button
  document.getElementById("lbr-close")?.addEventListener("click", closeModal);
  document.getElementById("lbr-refresh")?.addEventListener("click", () => refreshRoutesLists(mode));

  // Move buttons
  document.getElementById("lbr-to-right")?.addEventListener("click", () => moveSelected(mode, "left"));
  document.getElementById("lbr-to-left")?.addEventListener("click", () => moveSelected(mode, "right"));

  // double click moves
  document.getElementById("lbr-left")?.addEventListener("dblclick", () => moveSelected(mode, "left"));
  document.getElementById("lbr-right")?.addEventListener("dblclick", () => moveSelected(mode, "right"));

  // manual add
  document.getElementById("lbr-add")?.addEventListener("click", () => openManual(mode));
  document.getElementById("lbr-manual-cancel")?.addEventListener("click", hideManualPanel);
  document.getElementById("lbr-manual-confirm")?.addEventListener("click", () => confirmManual(mode));

  hideManualPanel();
}


// ---- Route key helpers ----
// Represent a route key as an array of shipper IDs/COFORs.
// Shows "A, B, C | Freq: x | Util: y%" like format_route() :contentReference[oaicite:2]{index=2}

function routeIdToKey(id) {
  if (!id) return [];
  return id.split("|").filter(Boolean);
}

function formatRouteLabel(route) {
  const shippers = (route.sequence || []).slice().sort().join(", ");
  const freq = route.frequency ?? "—";
  const util = route.utilization;
  const direction = route.flow_direction
  return `${shippers} | ${direction} | Freq: ${freq} | Util: ${util}`;
}

// Retrieving data and rendering the lists of routes (left and right) according to mode.
async function refreshRoutesLists(mode) {
  const left = document.getElementById("lbr-left");
  const right = document.getElementById("lbr-right");

  let data;
  try {
    data = await apiGet(`/api/lock_block?mode=${encodeURIComponent(mode)}`);
  } catch (e) {
    setError("Failed to load routes: " + (e.message || e));
    return;
  }

  const current = Array.isArray(data?.current_routes) ? data.current_routes : [];
  const target = Array.isArray(data?.target_routes) ? data.target_routes : [];

  // render left
  left.innerHTML = "";
    current.forEach(route => {
      const id = route.key;
      left.appendChild(buildOption(id, formatRouteLabel(route), route.flow_direction));
    });

  // render right
right.innerHTML = "";
target.forEach(route => {
  const id = route.key;
  right.appendChild(buildOption(id, formatRouteLabel(route), route.flow_direction));
});

  setError("");
}


function buildOption(value, label, flowDirection) {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  opt.dataset.flowDirection = flowDirection;

  if (flowDirection === "parts") {
    opt.classList.add("route-parts");
  } else if (flowDirection === "empties") {
    opt.classList.add("route-empties");
  }

  return opt;
}


async function moveSelected(mode, from) {
  const left = document.getElementById("lbr-left");
  const right = document.getElementById("lbr-right");

  const source = from === "left" ? left : right;
  const selectedOption = source.selectedOptions[0];
  if (!selectedOption) return;

  const selectedId = selectedOption.value;
  const keyArray = routeIdToKey(selectedId);
  const flowDirection = selectedOption.dataset.flowDirection;

  try {
    await apiPost("/api/lock_block/move", {
      mode: mode,
      from_side: from,
      route_key: keyArray,
      flow_direction: flowDirection
    });
  } catch (e) {
    setError("Move failed: " + (e.message || e));
    return;
  }

  await refreshRoutesLists(mode);
  setError("");
}


// Manual Lock / Block actions

function hideManualPanel() {
  const panel = document.getElementById("lbr-manual");
  if (panel) panel.classList.add("hidden");
}

function showManualPanel() {
  const panel = document.getElementById("lbr-manual");
  if (panel) panel.classList.remove("hidden");
}

function setSelectOptions(sel, values, placeholder) {
  sel.innerHTML = "";
  sel.appendChild(buildOption("", placeholder || "—"));
  (values || []).forEach(v => sel.appendChild(buildOption(String(v), String(v))));
}

function getManualSelection() {
  const ids = ["lbr-s1", "lbr-s2", "lbr-s3", "lbr-s4"].map(id => document.getElementById(id)?.value || "");
  return ids.filter(Boolean);
}

async function openManual() {
  const available = await apiGet("/api/lock_block/suppliers");
  const vehicles = await apiGet("/api/lock_block/vehicles");

  // populate all 4 dropdowns
  setSelectOptions(document.getElementById("lbr-s1"), available, "Starting supplier");
  setSelectOptions(document.getElementById("lbr-s2"), available, "1st stop");
  setSelectOptions(document.getElementById("lbr-s3"), available, "2nd stop");
  setSelectOptions(document.getElementById("lbr-s4"), available, "3rd stop");
  setSelectOptions(document.getElementById("lbr-vehicles"), vehicles.id, "Vehicle");

  showManualPanel();
  setError("");
}

async function confirmManual(mode) {
  setError("");
  const chosen = getManualSelection();

  try {
    await apiPost("/api/lock_block/add_manual", {
      mode,
      route_key: chosen,
      vehicle_id: document.getElementById("lbr-vehicle")?.value || null
    });
  } catch (e) {
    setError("Add manual route failed: " + (e.message || e));
    return;
  }
  await refreshRoutesLists(mode);
}




