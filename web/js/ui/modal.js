import { loadHtml } from '../utils.js';
import { apiPost, apiGet } from "../api.js";
import { showProjectPage } from "../views/project.js";
import { setAppBusy } from "./overlay.js";

const backdrop = () => document.getElementById("modal-backdrop");
const body = () => document.getElementById("modal-body");

export function openModal(html, modalClass = "") {
  const mb = backdrop();
  const modal = document.getElementById("modal");

  body().innerHTML = html;

  modal.className = "modal";
  if (modalClass) {
    modal.classList.add(modalClass);
  }

  mb.classList.remove("hidden");
}

export function closeModal(){
  const mb = backdrop();
  body().innerHTML = "";
  modal.className = "modal";
  mb.classList.add("hidden");
}

