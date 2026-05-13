import { apiGet, apiPost } from "../../api.js";
import { loadHtml, escapeHtml } from "../../utils.js";

import { openRoutesModal } from "../../ui/routes_table_modal.js";
import { openShippersModal } from "../../ui/shippers_table_modal.js";
import { openHubsModal } from "../../ui/hubs_table_modal.js";

import { openModal } from "../../ui/modal.js";
import { ManualSwapFlow } from "../../ui/swap_resolve_missing.js";

import { refreshScenarioData, getState, applyMapPatchOrRefresh } from "./scenario.js";

export function renderSelectionSummary(selectedObject) {
  const panel = document.getElementById("selection-summary");
  if (!panel || !selectedObject) return;

  if (selectedObject.type === "route") {
      const isHubRoute =
        selectedObject.subtype === "hub-linehaul" ||
        selectedObject.subtype === "hub-first-leg";

      const isLocked = Boolean(selectedObject.is_locked);
      const isBlocked = Boolean(selectedObject.is_blocked);

      const routeStatusIcon = isBlocked
        ? "🚫"
        : isLocked
          ? "🔒"
          : "🔓";

      const lockButtonText = isLocked ? "Unlock route" : "Lock route";
      const blockButtonText = isBlocked ? "Unblock route" : "Block route";

      const shippers = Array.isArray(selectedObject.shippers)
        ? selectedObject.shippers
            .map(s => `${escapeHtml(s.cofor || "")} - ${escapeHtml(s.name || "")}`)
            .join("<br>")
        : "";

      panel.innerHTML = `
        <div class="selection-card">
          <h3>${routeStatusIcon} ${escapeHtml(selectedObject.name || "Selected route")}</h3>

          <div><strong>Vehicle:</strong> ${escapeHtml(selectedObject.vehicle || "-")}</div>
          <div><strong>Frequency:</strong> ${escapeHtml(String(selectedObject.frequency ?? "-"))}</div>
          <div><strong>Utilization:</strong> ${escapeHtml(formatPercent(selectedObject.utilization))}</div>
          <div><strong>Cost:</strong> ${escapeHtml(formatCurrency(selectedObject.cost))}</div>

          <div class="selection-section">
            <strong>Shippers:</strong>
            <div>${shippers || "-"}</div>
          </div>

          <div class="selection-actions">
            <button
              id="selection-lock-route"
              ${isHubRoute || isBlocked ? "disabled" : ""}
            >
              ${lockButtonText}
            </button>

            <button
              id="selection-block-route"
              ${isHubRoute || isLocked ? "disabled" : ""}
            >
              ${blockButtonText}
            </button>

            <button id="selection-edit-route">Edit route</button>
          </div>
        </div>
      `;

      document.getElementById("selection-lock-route")?.addEventListener("click", async () => {
        await moveSelectedRouteLockBlock(
          selectedObject,
          "lock",
          selectedObject.is_locked ? "right" : "left"
        );
      });

      document.getElementById("selection-block-route")?.addEventListener("click", async () => {
        await moveSelectedRouteLockBlock(
          selectedObject,
          "block",
          selectedObject.is_blocked ? "right" : "left"
        );
      });

      document.getElementById("selection-edit-route")?.addEventListener("click", () => {
        openRoutesModal(selectedObject);
      });

      return;
    }

  if (selectedObject.type === "shipper") {
    panel.innerHTML = `
      <div class="selection-card">
        <h3>${escapeHtml(selectedObject.name || "Selected shipper")}</h3>

        <div><strong>COFOR:</strong> ${escapeHtml(selectedObject.cofor || "-")}</div>
        <div><strong>Carrier:</strong> ${escapeHtml(selectedObject.carrier || "-")}</div>
        <div><strong>Current route:</strong> ${escapeHtml(selectedObject.currentRoute || "-")}</div>

        <div class="selection-actions">
          <button id="selection-swap-network">Swap network</button>
          <button id="selection-edit-shipper">Edit shipper</button>
        </div>
      </div>
    `;

    document.getElementById("selection-swap-network")?.addEventListener("click", async () => {
  const cofor = selectedObject.cofor;
  const isCurrentlyHub = selectedObject.currentRoute === "Hub network";

  try {
    const res = await apiPost("/api/swap_hub", {
      direct_cofors_to_add: isCurrentlyHub ? [cofor] : [],
      hub_cofors_to_add: isCurrentlyHub ? [] : [cofor],
    });

    const suppliers_wo_tariffs = res.shippers_without_tariff;
    if (suppliers_wo_tariffs?.length) {
      alert(
        "Warning: Failed to move following suppliers to direct network due to missing tariffs:\n\n" +
        suppliers_wo_tariffs.join(", ")
      );
    }

    const suppliers_wo_hubs = res.shippers_without_hub;
    if (suppliers_wo_hubs?.length) {
      const html = await loadHtml("../views_html/swap_resolve_missing.html");
      openModal(html);

      const availableHubs = await apiGet("/api/swap_hub/available_hubs");
      const manualSwapFlow = new ManualSwapFlow(suppliers_wo_hubs, availableHubs);

      manualSwapFlow.init();
      await manualSwapFlow.run();

      alert("Swap resolved successfully.");
    } else {
      alert("Swap applied successfully.");
    }

    await applyMapPatchOrRefresh(res.mapPatch);
    await refreshScenarioData()

  } catch (e) {
    if (e.type === "CannotEditBaselineError" || e.type === "HubKeyNotMapped") {
      alert(e.message);
      return;
    }
    throw e;
  }
});

    document.getElementById("selection-edit-shipper")?.addEventListener("click", () => {
      openShippersModal(selectedObject);
    });

    return;
  }

  if (selectedObject.type === "hub") {
    panel.innerHTML = `
      <div class="selection-card">
        <h3>${escapeHtml(selectedObject.name || "Selected hub")}</h3>

        <div><strong>COFOR:</strong> ${escapeHtml(selectedObject.cofor || "-")}</div>
        <div><strong>Flow:</strong> ${escapeHtml(selectedObject.flow || "-")}</div>

        <div class="selection-actions">
          <button id="selection-edit-hub">Edit hub</button>
        </div>
      </div>
    `;

    document.getElementById("selection-edit-hub")?.addEventListener("click", () => {
      openHubsModal(selectedObject);
    });
  }
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }

  return `${Number(value).toFixed(2)}%`;
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }

  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
}

async function moveSelectedRouteLockBlock(selectedObject, mode, fromSide = "left") {
  if (!selectedObject || selectedObject.type !== "route") return;
  if (selectedObject.subtype !== "direct") return;

  const routeKey = selectedObject.route_key
    ?? selectedObject.key?.split("|").filter(Boolean)
    ?? [];

  if (!routeKey.length) {
    alert("Could not identify selected route key.");
    return;
  }

  try {
    const res = await apiPost("/api/lock_block/move", {
      mode,
      from_side: fromSide,
      route_key: routeKey,
      flow_direction: selectedObject.flow_direction ?? selectedObject.flow,
    });

    const previousSelection = { ...selectedObject };

    await applyMapPatchOrRefresh(res.mapPatch);
    await refreshScenarioData();

    const state = getState();
    state.selectedObject = {
      ...previousSelection,
      is_locked: mode === "lock" ? fromSide === "left" : previousSelection.is_locked,
      is_blocked: mode === "block" ? fromSide === "left" : previousSelection.is_blocked,
    };

    renderSelectionSummary(state.selectedObject);

  } catch (e) {
    alert(`${mode === "lock" ? "Lock" : "Block"} route failed: ` + (e.message || e));
  }
}

function sameRouteSelection(a, b) {
  if (!a || !b) return false;
  if (a.type !== "route" || b.type !== "route") return false;

  const aKey = a.key ?? a.route_key?.join("|");
  const bKey = b.key ?? b.route_key?.join("|");

  return (
    aKey === bKey &&
    (a.flow_direction ?? a.flow) === (b.flow_direction ?? b.flow)
  );
}