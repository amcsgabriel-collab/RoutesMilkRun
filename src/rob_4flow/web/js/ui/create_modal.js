// Configures the "Create project" modal window, where user selects a Transport Plan to start a new project.
// Streams logs of the project creation progress to a tasklog window.
// Sets application as "busy", blocking navigation and showing spinner overlay.

import { loadHtml } from '../utils.js';
import { apiPost } from "../api.js";
import { showProjectPage } from "../views/project.js";
import { setAppBusy } from "./overlay.js";
import { openModal, closeModal } from "./modal.js";


let chosenFile = null;

// Export a function to open this modal window.
export async function openCreateModal() {
    const html = await loadHtml("../views_html/create_modal.html");
    openModal(html);
    wireCreateModal()
};

// Wires modal specific buttons.
function wireCreateModal() {
  document.getElementById("search-graf-btn")
    .addEventListener("click", handleChooseGrafClick);

  document.getElementById("create-go")
    .addEventListener("click", handleCreateClick);
}

// Internal functions:
async function handleChooseGrafClick() {
  // Using a different "file picker", native to the OS.
  // The browser file picker doesn't feel as nice.
  const path = await window.pywebview.api.open_graf_file();
  if (!path) return;

  // store globally
  chosenFile = path;
  updateChosenFileUI(path);
};

function updateChosenFileUI(name) {
  const label = document.getElementById("chosen-path");
  const createBtn = document.getElementById("create-go");

  if (!name) {
    label.textContent = "No file selected";
    createBtn.disabled = true;
  } else {
    label.textContent = name;
    createBtn.disabled = false;
  }
};

async function handleCreateClick() {

  if (!chosenFile) {
    alert("Please select a GRAF TP file first.");
    return;
  }

  setAppBusy(true);

  const logBox = document.getElementById("task-log");
  logBox.textContent = "Starting...\n";

  try {
    const task = await apiPost("/api/project/create", { path: chosenFile });

    // Setting up the logger of the progress reporting box.
    if (!task) {
      logBox.textContent += "Server did not return task_id\n";
      setAppBusy(false);
      return;
    }
    await streamTaskLogs(task, logBox);
    setAppBusy(false);
    showProjectPage();
  } catch (err) {
    alert(`Project creation failed: ${err.type}`)
    setAppBusy(false);
  }
};

// Handles the streaming of logs coming from the "task" event source.
function streamTaskLogs(taskId, logBox) {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/tasks/${taskId}/events`);
    let taskError = null;

    es.addEventListener("log", function (e) {
      const msg = e.data || "";
      logBox.textContent += msg + "\n";
      logBox.scrollTop = logBox.scrollHeight;
    });

    es.addEventListener("task_error", function (e) {
      try {
        taskError = JSON.parse(e.data);
      } catch {
        taskError = {
          message: e.data || "Project creation failed."
        };
      }

      if (taskError?.message) {
        const msg = String(taskError.message).replace(/\\n/g, "\n");
        logBox.textContent += `ERROR:\n${msg}\n`;
        logBox.scrollTop = logBox.scrollHeight;
      }
    });

    es.addEventListener("done", function () {
      logBox.textContent += "\n--- Task finished ---\n";
      logBox.scrollTop = logBox.scrollHeight;
      es.close();

      if (taskError) {
        const err = new Error(taskError.message || "Project creation failed.");
        err.type = taskError.type;
        err.code = taskError.code;
        err.data = taskError;
        reject(err);
        return;
      }

      resolve();
    });

    es.onerror = function () {
      es.close();
      reject(new Error("Connection to task log stream failed."));
    };
  });
}