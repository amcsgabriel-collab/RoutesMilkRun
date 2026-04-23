/**
 * Manual hub swap dialog flow
 *
 * Expected HTML ids:
 * - #hub-select
 * - #confirm-manual-swap-btn
 * - #revert-swap-btn
 *
 * Optional title element:
 * - #manual-swap-title
 */

import { closeModal } from "./modal.js";
import { showMap } from "../views/project.js";
import { apiPost } from "../api.js";

function onAllSuppliersHandled(decisionCache) {
  console.log("All suppliers handled:", decisionCache);
  closeModal();
  showMap();
}



export class ManualSwapFlow {
  constructor(suppliers, availableHubs) {
    this.titleEl =
      document.getElementById("manual-swap-title");
    this.hubSelectEl = document.getElementById("hub-select");
    this.confirmBtn = document.getElementById("confirm-manual-swap-btn");
    this.revertBtn = document.getElementById("revert-swap-btn");
    this.closeModal = document.getElementById("modal-close")
    this.suppliers = suppliers || [];
    this.availableHubs = availableHubs || [];
    this.currentIndex = 0;
    this.decisionCache = [];
    this.resolveCurrentAction = null;
  }

  validateDom() {
    if (!this.titleEl || !this.hubSelectEl || !this.confirmBtn || !this.revertBtn) {
      throw new Error("Manual swap dialog elements not found in DOM.");
    }
  }

  init() {
    this.validateDom();
    this.confirmBtn.onclick = () => this.handleConfirmManualSwap();
    this.revertBtn.onclick = () => this.handleRevertSwap();
    this.closeModal.onclick = async () => {await this.onClose();};
    };
  

  setSuppliers(suppliers) {
    this.suppliers = Array.isArray(suppliers) ? suppliers : [];
    this.currentIndex = 0;
    this.decisionCache = [];
  }

  async run() {
    if (!Array.isArray(this.suppliers) || this.suppliers.length === 0) {
      console.log("No unassigned suppliers to process.");
      return;
    }

    for (this.currentIndex = 0; this.currentIndex < this.suppliers.length; this.currentIndex += 1) {
      const supplier = this.suppliers[this.currentIndex];
      this.renderSupplier(supplier);

        const decision = await this.waitForUserDecision();
        if (decision) {
            this.decisionCache.push(decision);
        }
    }

    await apiPost("/api/swap_hub/resolve", { decisions: this.decisionCache });;
    onAllSuppliersHandled(this.decisionCache);
  }

  renderSupplier(supplier) {
    const zipKey = supplier.zip_key || "N/A";
    const cofor = supplier.cofor || "N/A";

    this.titleEl.textContent =
      `Couldn't assign hub to supplier ${cofor}, with Zip Key ${zipKey}`;

    this.populateHubSelect();
    this.hubSelectEl.dataset.supplierId = supplier.supplierId || "";
    this.hubSelectEl.dataset.cofor = cofor;
    this.hubSelectEl.dataset.zipKey = zipKey;
  }

  populateHubSelect() {
    this.hubSelectEl.innerHTML = "";

    const placeholderOption = document.createElement("option");
    placeholderOption.value = "";
    placeholderOption.textContent = "Choose a hub...";
    this.hubSelectEl.appendChild(placeholderOption);

    this.availableHubs.forEach((hub) => {
      const option = document.createElement("option");
      option.value = hub.cofor;
      option.textContent = `${hub.cofor} | ${hub.name}`;;
      this.hubSelectEl.appendChild(option);
    });

    this.hubSelectEl.value = "";
  }

  waitForUserDecision() {
    return new Promise((resolve) => {
      this.resolveCurrentAction = resolve;
    });
  }

  handleConfirmManualSwap() {
    const supplier = this.suppliers[this.currentIndex];
    const selectedHub = this.hubSelectEl.value;

    if (!selectedHub) {
      alert("Please select a hub before confirming the manual swap.");
      return;
    }

    const decision = {
      cofor: supplier.cofor,
      action: "confirm_manual_swap",
      selectedHub: selectedHub
    };

    this.finishCurrentDecision(decision);
  }

  handleRevertSwap() {
    const supplier = this.suppliers[this.currentIndex];

    const decision = {
      cofor: supplier.cofor,
      action: "revert_swap",
      selectedHub: null
    };

    this.finishCurrentDecision(decision);
  }

  finishCurrentDecision(decision) {
    if (typeof this.resolveCurrentAction === "function") {
      const resolve = this.resolveCurrentAction;
      this.resolveCurrentAction = null;
      resolve(decision);
    }
  }

  async onClose() {
    const confirmation = confirm("Are you sure you want to cancel the resolution? \
        This will revert all missing hub swaps made so far.");
    console.log("confirmation:", confirmation);

    if (!confirmation) return;
    const decisionCache = [];
    for (const supplier of this.suppliers) {
        decisionCache.push({
            cofor: supplier.cofor,
            action: "revert_swap",
            selectedHub: null
        });
    }
    await apiPost("/api/swap_hub/resolve", { decisions: decisionCache });
    alert("Resolution cancelled. All missing hub swaps reverted.");
    closeModal();
    showMap();
    }
}
