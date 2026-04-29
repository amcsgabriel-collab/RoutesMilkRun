import { loadHtml, escapeHtml } from "../utils.js";
import { openModal, closeModal } from "./modal.js";
import { apiGet } from "../api.js";

export function $id(id) {
  return document.getElementById(id);
}

export function text(v) {
  return escapeHtml(String(v ?? ""));
}

export function formatNumber(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatInteger(n) {
  if (n == null) return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return "—";
  return num.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

export function formatCoordinates(coords) {
  if (!coords) return "—";

  if (typeof coords === "string") return escapeHtml(coords);

  if (Array.isArray(coords) && coords.length >= 2) {
    const lat = Number(coords[0]);
    const lon = Number(coords[1]);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return "—";
    return `(${lat.toFixed(5)}, ${lon.toFixed(5)})`;
  }

  if (typeof coords === "object") {
    const lat = Number(coords.lat ?? coords.latitude);
    const lon = Number(coords.lon ?? coords.longitude);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return "—";
    return `(${lat.toFixed(5)}, ${lon.toFixed(5)})`;
  }

  return "—";
}

export async function openTableModal(config) {
  const html = await loadHtml(config.htmlPath);
  openModal(html);

  const state = {
    list: [],
    rows: [],
    columnFilters: {}
  };

  async function loadAndRender() {
    const tbody = $id(config.tbodyId);
    const err = config.errorId ? $id(config.errorId) : null;

    const flow = config.flowName
      ? document.querySelector(`input[name="${config.flowName}"]:checked`)?.value || "parts"
      : null;

    if (err) {
      err.style.display = "none";
      err.textContent = "";
    }

    tbody.innerHTML = tableMessage(config.columns.length, "Loading…");

    try {
      state.list = await apiGet(config.endpoint);
      if (!Array.isArray(state.list)) state.list = [];

      if (config.validate) {
        state.list.forEach(config.validate);
      }

      state.rows = state.list
        .map((item, i) => config.mapItem ? config.mapItem(item, flow, i) : item)
        .filter(Boolean);

      const visibleRows = state.rows.filter(row => matchesFilters(row, config, state));

      tbody.innerHTML = visibleRows.length
        ? visibleRows.map((row, i) => renderRow(row, i, config.columns)).join("")
        : tableMessage(config.columns.length, config.emptyText?.(flow) || "No rows");
    } catch (e) {
      if (err) {
        err.textContent = e.message || String(e);
        err.style.display = "block";
      }

      tbody.innerHTML = tableMessage(config.columns.length, "Error");
    }
  }

  wireCommon(config, state, loadAndRender);

  if (config.wireExtra) {
    config.wireExtra({ loadAndRender, state });
  }

  await loadAndRender();
}

function renderRow(row, i, columns) {
  return `
    <tr class="sh-row" data-idx="${i}" style="cursor:default">
      ${columns.map(col => `
        <td style="${cellStyle(col)}">
          ${col.render ? col.render(row) : text(row[col.key])}
        </td>
      `).join("")}
    </tr>
  `;
}

function cellStyle(col) {
  return [
    "padding:8px",
    "border-bottom:1px solid #f2f4f7",
    col.align === "right" ? "text-align:right;padding-right:12px" : "",
    col.align === "center" ? "text-align:center" : ""
  ].filter(Boolean).join(";");
}

function tableMessage(colspan, message) {
  return `
    <tr>
      <td colspan="${colspan}" style="padding:20px;text-align:center;color:#6b7280">
        ${escapeHtml(message)}
      </td>
    </tr>
  `;
}

function matchesFilters(row, config, state) {
  const topFilter = config.topFilterId
    ? ($id(config.topFilterId)?.value || "").trim().toLowerCase()
    : "";

  const matchesTop =
    !topFilter ||
    (config.searchKeys || []).some(key =>
      String(row[key] ?? "").toLowerCase().includes(topFilter)
    );

  const matchesColumns = Object.entries(state.columnFilters).every(([key, values]) => {
    if (!values || values.size === 0) return true;
    return values.has(String(row[key] ?? ""));
  });

  return matchesTop && matchesColumns;
}

function wireCommon(config, state, loadAndRender) {
  $id("modal-close")?.addEventListener("click", closeModal);
  $id(config.closeId)?.addEventListener("click", closeModal);

  if (config.refreshId) {
    $id(config.refreshId)?.addEventListener("click", loadAndRender);
  }

  if (config.topFilterId) {
    $id(config.topFilterId)?.addEventListener("input", debounce(loadAndRender));
  }

  if (config.flowName) {
    document.querySelectorAll(`input[name="${config.flowName}"]`).forEach(el => {
      el.addEventListener("change", loadAndRender);
    });
  }

  document.querySelectorAll(".table-filter-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      openFilterMenu(btn.dataset.field, btn, config, state, loadAndRender);
    });
  });

  document.addEventListener("click", e => {
    if (!e.target.closest(".table-filter-menu") && !e.target.closest(".table-filter-btn")) {
      document.querySelector(".table-filter-menu")?.remove();
    }
  });
}

function openFilterMenu(field, button, config, state, loadAndRender) {
  document.querySelector(".table-filter-menu")?.remove();

  const values = [...new Set(
    state.rows.map(row => String(row[field] ?? "")).filter(Boolean)
  )].sort();

  const selected = state.columnFilters[field] || new Set(values);

  const menu = document.createElement("div");
  menu.className = "table-filter-menu";
  menu.style.cssText = `
    position:absolute;
    z-index:9999;
    background:white;
    border:1px solid #d1d5db;
    border-radius:8px;
    box-shadow:0 10px 25px rgba(0,0,0,.12);
    padding:8px;
    max-height:260px;
    overflow:auto;
    min-width:220px;
  `;

  menu.innerHTML = `
  <input
    type="text"
    data-action="filter-options"
    placeholder="Search options..."
    style="width:100%;box-sizing:border-box;margin-bottom:8px;padding:6px;border:1px solid #d1d5db;border-radius:6px"
  >

  <div style="display:flex;gap:8px;margin-bottom:8px">
    <button type="button" data-action="select-all">Select all</button>
    <button type="button" data-action="clear">Clear</button>
  </div>

  <div data-role="options">
    ${values.map(v => `
      <label data-option-text="${escapeHtml(v.toLowerCase())}" style="display:block;padding:4px 2px">
        <input type="checkbox" value="${escapeHtml(v)}" ${selected.has(v) ? "checked" : ""}>
        ${escapeHtml(v)}
      </label>
    `).join("")}
  </div>

  <div style="display:flex;gap:8px;margin-top:8px;justify-content:flex-end">
    <button type="button" data-action="cancel">Cancel</button>
    <button type="button" data-action="apply">Apply</button>
  </div>
`;

  document.body.appendChild(menu);

  const optionSearch = menu.querySelector('[data-action="filter-options"]');

    optionSearch.addEventListener("input", () => {
      const q = optionSearch.value.trim().toLowerCase();

      menu.querySelectorAll("[data-option-text]").forEach(label => {
        label.style.display = label.dataset.optionText.includes(q) ? "block" : "none";
      });
    });

  const rect = button.getBoundingClientRect();
  menu.style.left = `${rect.left}px`;
  menu.style.top = `${rect.bottom + window.scrollY + 4}px`;

  menu.querySelector('[data-action="select-all"]').onclick = () => {
    menu.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
  };

  menu.querySelector('[data-action="clear"]').onclick = () => {
    menu.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
  };

  menu.querySelector('[data-action="cancel"]').onclick = () => {
    menu.remove();
  };

  menu.querySelector('[data-action="apply"]').onclick = () => {
    const checked = [...menu.querySelectorAll('input[type="checkbox"]:checked')]
      .map(cb => cb.value);

    if (checked.length === values.length) {
      delete state.columnFilters[field];
    } else {
      state.columnFilters[field] = new Set(checked);
    }

    menu.remove();
    loadAndRender();
  };
}

function debounce(fn, wait = 220) {
  let t;
  return () => {
    clearTimeout(t);
    t = setTimeout(fn, wait);
  };
}