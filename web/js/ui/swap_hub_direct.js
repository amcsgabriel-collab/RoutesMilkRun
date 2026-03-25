import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiPost, apiGet } from "../api.js";
import { showMap } from "../views/project.js"
import { ManualSwapFlow } from "./swap_resolve_missing.js";


let swapState = {
  baseline: {
    direct: [],
    hub: []
  },
  initial: {
    direct: [],
    hub: []
  },
  current: {
    direct: [],
    hub: []
  },
  thresholds: {
    weight: null,
    volume: null,
    loading_meters: null
  },
  autoMoved: {
    directToHub: new Set(),
    hubToDirect: new Set()
  }
};


/**
 * Opens the "Hub/Direct Swap" modal
 */
export async function openSwapModal() {
  const html = await loadHtml("../views_html/swap_hub_direct.html");
  openModal(html);
  wireSwapModal();
  wireInputCheckbox();
}

/**
 * Coordinates the wiring and setup of the modal
 */
async function wireSwapModal() {

  const data = await apiGet("/api/swap_hub/load")

  swapState = {
    baseline: {
      direct: [...data.baseline_direct],
      hub: [...data.baseline_hub]
    },
    initial: {
      direct: [...data.current_direct],
      hub: [...data.current_hub]
    },
    current: {
      direct: [...data.current_direct],
      hub: [...data.current_hub]
    },
    thresholds: {
      weight: null,
      volume: null,
      loading_meters: null
    },
    moved: {
      directToHub: new Set(),
      hubToDirect: new Set()
    }
  };

  document.getElementById("btn-to-hub").addEventListener("click", 
    () => {moveSelected("direct", "hub", "direct-list")});
  document.getElementById("btn-to-direct").addEventListener("click", 
    () => {moveSelected("hub", "direct", "hub-list")});
  document.getElementById("btn-reset").addEventListener("click", resetToInitial);
  document.getElementById("btn-baseline").addEventListener("click", revertToBaseline);
  document.getElementById("btn-set-thresholds").addEventListener("click", toggleThresholdPanel);
  document.getElementById("btn-apply-thresholds").addEventListener("click", applyThresholds);
  document.getElementById("btn-close-thresholds").addEventListener("click", toggleThresholdPanel);
  document.getElementById("swap-close").addEventListener("click", closeModal);
  document.getElementById("swap-confirm").addEventListener("click", confirmSwap);
  renderLists();
};

function renderList(containerId, items, movedSet) {
  const el = document.getElementById(containerId);

  el.innerHTML = items.map(shipper => `
    <option 
      value="${escapeHtml(shipper)}"
      class="${movedSet.has(shipper) ? "swap-item-moved" : ""}"
    >
      ${escapeHtml(shipper)}
    </option>
  `).join("");
}

function renderLists() {
  // Toggle "moved" state.
  syncAllMovedState();

  renderList(
    "direct-list",
    swapState.current.direct,
    swapState.moved.hubToDirect
  );

  renderList(
    "hub-list",
    swapState.current.hub,
    swapState.moved.directToHub
  );
}

// --------------------------------------
// ------------  SWAPPING  --------------
// --------------------------------------

/**
 * Move selected element from one list to another, given the "from" and "to" lists and the selection ID.
 * 
 * @param {String} fromKey 
 * @param {String} toKey 
 * @param {String} selectId 
 * @returns 
 */
function moveSelected(fromKey, toKey, selectId) {
  const selected = getSelected(selectId);

  if (!selected.length) return;

  // Remove selection from "FROM" list
  swapState.current[fromKey] =
    swapState.current[fromKey].filter(s => !selected.includes(s));

  // Add selection to "TO" list  
  swapState.current[toKey] = [
    ...swapState.current[toKey],
    ...selected
  ];

  renderLists();
}

function syncAllMovedState() {
  swapState.moved.directToHub.clear();
  swapState.moved.hubToDirect.clear();

  const allSuppliers = new Set([
    ...swapState.initial.direct,
    ...swapState.initial.hub,
    ...swapState.current.direct,
    ...swapState.current.hub,
  ]);

  allSuppliers.forEach(syncMovedState);
}


function syncMovedState(shipper) {
  const wasDirect = swapState.initial.direct.includes(shipper);
  const wasHub = swapState.initial.hub.includes(shipper);

  const isDirect = swapState.current.direct.includes(shipper);
  const isHub = swapState.current.hub.includes(shipper);

  if (wasDirect) {
    if (isHub) {
      swapState.moved.directToHub.add(shipper);
    } else {
      swapState.moved.directToHub.delete(shipper);
    }
  }

  if (wasHub) {
    if (isDirect) {
      swapState.moved.hubToDirect.add(shipper);
    } else {
      swapState.moved.hubToDirect.delete(shipper);
    }
  }
}

function getSelected(containerId) {
  const select = document.getElementById(containerId);

  return Array.from(select.selectedOptions)
    .map(opt => opt.value);
}

function resetToInitial() {
  swapState.current.direct = [...swapState.initial.direct];
  swapState.current.hub = [...swapState.initial.hub];
  swapState.thresholds = {
    weight: null,
    volume: null,
    loading_meters: null
  };
  renderLists();
  resetThresholdInputs();
}

function revertToBaseline() {
  swapState.current.direct = [...swapState.baseline.direct];
  swapState.current.hub = [...swapState.baseline.hub];
  swapState.thresholds = {
    weight: null,
    volume: null,
    loading_meters: null
  };
  renderLists();
  resetThresholdInputs();
}


// --------------------------------------
// ------------  THRESHOLDS  ------------
// --------------------------------------

function toggleThresholdPanel() {
  const panel = document.getElementById("swap-threshold-panel");
  if (!panel) return;
  panel.classList.toggle("hidden");
}

function wireInputCheckbox() {
  const chkWeight = document.getElementById("chk-weight");
  const chkVolume = document.getElementById("chk-volume");
  const chkLoading = document.getElementById("chk-loading");

  const inpWeight = document.getElementById("inp-weight");
  const inpVolume = document.getElementById("inp-volume");
  const inpLoading = document.getElementById("inp-loading");

  toggleThresholdInput(chkWeight, inpWeight);
  toggleThresholdInput(chkVolume, inpVolume);
  toggleThresholdInput(chkLoading, inpLoading);
}

function toggleThresholdInput(chk, inp) {
  if (!chk || !inp) return;

  const sync = () => {
    inp.disabled = !chk.checked;
    if (!chk.checked) inp.value = "";
  };

  chk.addEventListener("change", sync);
  sync();
}

function getActiveThresholds() {
  const thresholds = {
    weight: null,
    volume: null,
    loading_meters: null
  };

  addThresholdIfChecked(thresholds, "chk-weight", "inp-weight", "weight");
  addThresholdIfChecked(thresholds, "chk-volume", "inp-volume", "volume");
  addThresholdIfChecked(thresholds, "chk-loading", "inp-loading", "loading_meters");

  return thresholds;
}

function addThresholdIfChecked(thresholds, chkId, inputId, key) {
  const chk = document.getElementById(chkId);
  const inp = document.getElementById(inputId);

  if (!chk || !inp || !chk.checked) return;

  const value = Number(inp.value);

  if (!Number.isFinite(value) || value <= 0) {
    thresholds[key] = "invalid";
    return;
  }

  thresholds[key] = value;
}

function validate_thresholds(thresholds) {
  for (const key in thresholds) {
    if (thresholds[key] === "invalid") {
      alert("Please enter positive numbers.");
      return false;
    }
  }
  return true;
}

async function applyThresholds() {
    const thresholds = getActiveThresholds()
    if (!validate_thresholds(thresholds)) return;
    try{
        const data = await apiPost("/api/swap_hub/apply_thresholds_preview", {thresholds });
        swapState.thresholds = thresholds;
        swapState.current.direct = [...data.direct];
        swapState.current.hub = [...data.hub];
        renderLists();
        toggleThresholdPanel();
        alert("Thresholds successfully applied.")
    } catch(e) {
        if (e.type === 'CannotEditBaselineError') {
            alert(e.message);
            return;
        }
        throw e;
    }
}

// --------------------------------------
// ------------  CONFIRM  ---------------
// --------------------------------------

async function confirmSwap() {
    try {
        const suppliers = await apiPost("/api/swap_hub", {
            direct_cofors_to_add: Array.from(swapState.moved.hubToDirect),
            hub_cofors_to_add: Array.from(swapState.moved.directToHub),
        });
        if (suppliers && suppliers.length > 0) {
          const html = await loadHtml("../views_html/swap_resolve_missing.html");
          openModal(html);
          const availableHubs = await apiGet("/api/swap_hub/available_hubs");
          const manualSwapFlow = new ManualSwapFlow(suppliers, availableHubs);
          manualSwapFlow.init();
          await manualSwapFlow.run();
          alert("Swap resolved successfully.");
          showMap();
        } else {
          alert("Swap applied successfully.");
          closeModal();
          showMap();
        }
        
    } catch(e) {
        if (e.type === 'CannotEditBaselineError') {
            alert(e.message);
            return;
        }
        if (e.type === "HubKeyNotMapped") {
            alert(e.message);
            return;
        } else {
            throw e;
        }
    }
}