// Configures the "core" of the application, which includes the main window, the project menu and some other global actions.

import { showProjectPage } from "./views/project.js";
import { showStartPage } from "./views/start.js";
import { openCreateModal } from "./ui/create_modal.js"
import { apiPost } from "./api.js"
import { closeModal } from "./ui/modal.js";
import { refreshProjectData } from "./views/project.js"

document.addEventListener("DOMContentLoaded", async ()=>{
  // wire global menu.
  document.getElementById("menu-new").addEventListener("click", openCreateModal);
  document.getElementById("menu-open").addEventListener("click", openLoadProjectWindow);
  document.getElementById("menu-save").addEventListener("click", saveProject);
  document.getElementById("menu-save-as").addEventListener("click", openSaveProjectAsWindow);
  // Wiring up a "common" button for the global modal template.
  document.getElementById("modal-close").addEventListener("click", closeModal) 

  // start at "start page".
  await showStartPage();
});

async function saveProject() {
  try {
    const res = await apiPost("/api/project/save", {});
    // Handling the "first save" scenario, where project file was not yet created.
    if (res && res.needs_save_as) {
      await openSaveProjectAsWindow();
      return;
    }
    alert("Saved");
  } catch (err) {
    alert("Save failed: " + err.message);
  }
}

export async function openLoadProjectWindow() {
  // Using a different "file picker", native to the OS.
  // The browser file picker doesn't feel as nice.
  const path = await window.pywebview.api.open_rob_file();
  if (!path) return;
  try {
    const res = await apiPost("/api/project/load", {path:path});
    showProjectPage();
  } catch (err) {
    alert("Failed to load project: " + err.message);
    showStartPage()
  }
}

async function openSaveProjectAsWindow() {
  // Using a different "file picker", native to the OS.
  // The browser file picker doesn't feel as nice.
  const path = await window.pywebview.api.save_project_as();
  if (!path) return;
  try {
    await apiPost("/api/project/save_as", {path:path});
    await refreshProjectData();
    alert("Saved");
  } catch (err) {
    alert("Save failed: " + err.message);
  }
}
