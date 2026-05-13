// Configures the main "project" window.

import { apiGet, apiPost, apiPut } from "../../api.js";
import { loadHtml, escapeHtml } from "../../utils.js";
import { openShippersModal } from "../../ui/shippers_table_modal.js";
import { openRoutesModal } from "../../ui/routes_table_modal.js";
import { openHubsModal } from "../../ui/hubs_table_modal.js";
import { openVehiclesModal } from "../../ui/vehicles_table_modal.js";
import { openTariffsModal } from "../../ui/tariffs_table_modal.js";
import { openSwapModal } from "../../ui/swap_hub_direct.js";
import { openLockRoutesModal, openBlockRoutesModal } from "../../ui/lock_block_routes_modal.js";
import { openSolveLogbox } from "../../ui/solver_logbox.js";
import { wireMapEvents, showMap } from "../../ui/map_frame.js";
import { renderSelectionSummary } from "./selection_card.js";
import {
  wireScenarioPanel,
  refreshScenarioData,
  getState,
} from "./scenario.js";

export async function showProjectPage() {
  const html = await loadHtml("/views_html/project.html");
  document.getElementById("content").innerHTML = html;
  await initializeProjectPage();
}

async function initializeProjectPage() {
  document.getElementById("region-select").addEventListener("change", onRegionChange);

  document.getElementById("shippers-table").addEventListener("click", openShippersModal);
  document.getElementById("routes-table").addEventListener("click", openRoutesModal);
  document.getElementById("hubs-table").addEventListener("click", openHubsModal);
  document.getElementById("vehicles-table").addEventListener("click", openVehiclesModal);
  document.getElementById("tariffs-table").addEventListener("click", openTariffsModal);

  document.getElementById("swap-hub-direct").addEventListener("click", openSwapModal);
  document.getElementById("solver-run").addEventListener("click", runSolver);
  document.getElementById("lock-routes")?.addEventListener("click", openLockRoutesModal);
  document.getElementById("block-routes")?.addEventListener("click", openBlockRoutesModal);
  document.getElementById("solution-export").addEventListener("click", exportSolution);

  document.getElementById("right-panel-toggle").addEventListener("click", toggleCollapseRightPanel);

  wireToggleMap();
  wireMapEvents({
    getState,
    renderSelectionSummary,
    openContextMenu,
  });

  await wireScenarioPanel();
  await refreshProjectData();
}

export async function refreshProjectData() {
  await loadProjectOverview();
  await loadRegions();
  await refreshScenarioData()
  await showMap();
}

async function loadProjectOverview() {
  try {
    const project = await apiGet("/api/project");

    document.getElementById("overview-body").innerHTML =
      `<div><strong>Project:</strong> ${escapeHtml(project.meta.name || "")}</div>`;

    document.getElementById("plant-name").innerHTML =
      `${escapeHtml(project.context.plant_name || "")}`;

    document.getElementById("vehicles-kpi").innerHTML =
      `${escapeHtml(project.context.vehicles_count || "-")}`;
  } catch (e) {
    document.getElementById("overview-body").textContent = "Failed to load";
  }
}

async function loadRegions() {
  const select = document.getElementById("region-select");
  if (!select) return;

  const regions = await apiGet("/api/regions");

  select.innerHTML = regions
    .map(region => `<option value="${escapeHtml(region)}">${escapeHtml(region)}</option>`)
    .join("");

  const project = await apiGet("/api/project");
  const currentRegion = project.meta.current_region;

  if (currentRegion) {
    select.value = currentRegion;
  }
}

async function onRegionChange() {
  const select = document.getElementById("region-select");
  if (!select) return;

  await apiPut("/api/region", { region: select.value });
  await refreshProjectData();
}

function toggleCollapseRightPanel() {
  const grid = document.querySelector(".project-grid");
  const toggleBtn = document.getElementById("right-panel-toggle");

  const collapsed = grid.classList.toggle("right-collapsed");

  toggleBtn.textContent = collapsed ? "›" : "‹";
  toggleBtn.setAttribute("aria-expanded", String(!collapsed));
  toggleBtn.title = collapsed ? "Expand panel" : "Collapse panel";
}

function wireToggleMap() {
  const tabButtons = document.querySelectorAll(".panel-tab");

  tabButtons.forEach(button => {
    button.addEventListener("click", () => {
      const selectedTab = button.dataset.tab;

      document.querySelectorAll(".panel-tab").forEach(btn => {
        btn.classList.remove("active");
      });

      document.querySelectorAll(".tab-pane").forEach(pane => {
        pane.classList.remove("active");
      });

      button.classList.add("active");
      document.getElementById(`tab-${selectedTab}`).classList.add("active");
    });
  });
}

async function runSolver() {
  try {
    await openSolveLogbox();
  } catch (e) {
    alert(e.message || "Unexpected error during solving.");
  }
}

async function exportSolution() {
  try {
    await apiPost("/api/export_solution/validate");
    const path = await window.pywebview.api.export_solution();
    await apiPost("/api/export_solution", { path });
    alert("Solution exported successfully.");
  } catch (e) {
    alert(e.message || "Unexpected error.");
  }
}

export function openContextMenu(position, payload) {
  console.log("Open menu at:", position, payload);
}