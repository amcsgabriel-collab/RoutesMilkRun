import { apiPost } from "../api.js";
import { setAppBusy } from "./overlay.js";
import { openModal, closeModal } from "./modal.js";
import { loadHtml } from '../utils.js';

export async function openSolveLogbox() {
  const html = await loadHtml("../views_html/solver_logbox.html");
  openModal(html);

  const logBox = document.getElementById("solve-task-log");
  logBox.textContent = "";

  await runSolver(logBox);
}

async function runSolver(logBox) {
  setAppBusy(true);
  logBox.textContent = "Starting solver...\n";
  try {
    const task = await apiPost("/api/solve_model");

    if (!task) {
      logBox.textContent += "Server did not return task_id\n";
      return;
    }

    await streamTaskLogs(task, logBox);
  } catch (err) {
    const msg = err?.message || "Solver failed.";
    logBox.textContent += `\nERROR:\n${msg}\n`;
    logBox.scrollTop = logBox.scrollHeight;
    alert(msg);
  } finally {
    setAppBusy(false);
  }
}

function streamTaskLogs(taskOrTaskId, logBox) {
  return new Promise((resolve, reject) => {
    const taskId =
      typeof taskOrTaskId === "string"
        ? taskOrTaskId
        : taskOrTaskId?.task_id || taskOrTaskId?.id || taskOrTaskId;

    if (!taskId) {
      reject(new Error("Missing task_id for log streaming."));
      return;
    }

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
        taskError = { message: e.data || "Solver failed." };
      }

      const msg = String(taskError.message).replace(/\\n/g, "\n");
      logBox.textContent += `ERROR:\n${msg}\n`;
      logBox.scrollTop = logBox.scrollHeight;
    });

    es.addEventListener("done", function () {
      logBox.textContent += "\n--- Solver finished ---\n";
      logBox.scrollTop = logBox.scrollHeight;
      es.close();

      if (taskError) {
        const err = new Error(taskError.message || "Solver failed.");
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
      reject(new Error("Connection to solver log stream failed."));
    };
  });
}