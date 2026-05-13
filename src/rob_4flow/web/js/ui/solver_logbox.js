import { apiPost } from "../api.js";
import { setAppBusy } from "./overlay.js";
import { openModal } from "./modal.js";
import { loadHtml } from '../utils.js';
import { refreshScenarioData } from "../views/project/scenario.js";
import { showMap } from "../ui/map_frame.js";


export async function openSolveLogbox() {
  const html = await loadHtml("../views_html/solver_logbox.html");
  openModal(html);

  const logBox = document.getElementById("solve-task-log");
  const runButton = document.getElementById("solve-run");
  const solveHubsCheckbox = document.getElementById("solve-hubs");
  const MaxStopsInput = document.getElementById("max-stops");


  const overutil1 = document.getElementById("overutil-1");
  const overutil3 = document.getElementById("overutil-3");
  const overutil5 = document.getElementById("overutil-5");

  logBox.textContent = "";

  runButton?.addEventListener("click", async () => {
    runButton.disabled = true;

    try {
          const maxStops = Number(MaxStopsInput?.value);
              await runSolver(logBox, {
          solve_hubs: Boolean(solveHubsCheckbox?.checked),
          overutilization: {
            one_truck: percentInputToDecimal(overutil1?.value, 0.10),
            three_plus_trucks: percentInputToDecimal(overutil3?.value, 0.30),
            five_plus_trucks: percentInputToDecimal(overutil5?.value, 0.50),
          },
          max_stops: Number.isFinite(maxStops) ? maxStops : null,
        });
    } finally {
      runButton.disabled = false;
      await refreshScenarioData();
      await showMap();
    }
  });
}

async function runSolver(logBox, payload = {}) {
  setAppBusy(true);
  logBox.textContent = "Starting solver...\n";

  try {
    const task = await apiPost("/api/solve_model", payload);

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

function percentInputToDecimal(value, fallback) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return fallback;
  }

  return number / 100;
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