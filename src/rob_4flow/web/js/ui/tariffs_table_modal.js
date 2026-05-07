import { apiPost, apiPut } from "../api.js";

import {
  openTableModal,
  $id,
  text
} from "./table_modal.js";

let tariffMode = "ftl";

const tariffQueries = {
  ftl: "",
  ltl: ""
};

const tariffColumnFilters = {
  ftl: {},
  ltl: {}
};

export async function openTariffsModal() {
  tariffMode = "ftl";
  tariffQueries.ftl = "";
  tariffQueries.ltl = "";
  tariffColumnFilters.ftl = {};
  tariffColumnFilters.ltl = {};

  await openTableModal({
    htmlPath: "../views_html/tariffs_table_modal.html",

    endpoint: state => {
      state.columnFilters = tariffColumnFilters[tariffMode];

      const params = new URLSearchParams({
        tariff_type: tariffMode === "ftl" ? "ftl_mr" : "ltl_hub",
        q: tariffQueries[tariffMode] || "",
        limit: 500,
        offset: 0
      });

      Object.entries(state.columnFilters || {}).forEach(([key, values]) => {
        if (!values || values.size === 0) return;
        params.append(key, [...values].join(","));
      });

      return `/api/tariffs?${params.toString()}`;
    },

    tbodyId: "tariffs-tbody",
    closeId: "tariffs-close",
    refreshId: "tariffs-refresh",
    topFilterId: "tariffs-filter",
    errorId: "tariffs-error",

    searchKeys: () =>
      tariffMode === "ftl"
        ? [
            "tariff_type",
            "carrier_short_name",
            "origin_code",
            "destination_code",
            "means_of_transport",
            "deviation_bucket"
          ]
        : [
            "tariff_type",
            "carrier_short_name",
            "origin_code",
            "destination_code",
            "chargeable_weight_bracket"
          ],

    emptyText: () =>
      tariffMode === "ftl"
        ? "No FTL / MR tariffs"
        : "No LTL / Hub tariffs",

    mapItem: tariff => tariff,

    columns: state =>
      tariffMode === "ftl"
        ? ftlColumns(state)
        : ltlHubColumns(state),

    onBeforeRender: ({ columns }) => {
      renderTariffHeader(columns);
      updateTariffTabs();
    },

    wireExtra: ({ loadAndRender, state }) => {
      $id("tariffs-tab-ftl")?.addEventListener("click", async () => {
        if (tariffMode === "ftl") return;

        tariffQueries[tariffMode] = $id("tariffs-filter")?.value || "";
        tariffColumnFilters[tariffMode] = state.columnFilters;

        tariffMode = "ftl";
        state.columnFilters = tariffColumnFilters.ftl;
        $id("tariffs-filter").value = tariffQueries.ftl || "";

        await loadAndRender();
      });

      $id("tariffs-tab-ltl")?.addEventListener("click", async () => {
        if (tariffMode === "ltl") return;

        tariffQueries[tariffMode] = $id("tariffs-filter")?.value || "";
        tariffColumnFilters[tariffMode] = state.columnFilters;

        tariffMode = "ltl";
        state.columnFilters = tariffColumnFilters.ltl;
        $id("tariffs-filter").value = tariffQueries.ltl || "";

        await loadAndRender();
      });

      $id("tariffs-filter")?.addEventListener("input", e => {
        tariffQueries[tariffMode] = e.target.value || "";
      });

      $id("tariffs-add")?.addEventListener("click", () => {
        addEmptyTariffRow(state);
      });

      document.addEventListener("click", async e => {
        const saveBtn = e.target.closest(".tariff-save");
        if (saveBtn) {
          await saveTariff(saveBtn.closest("tr"));
          await loadAndRender();
          return;
        }

        const createBtn = e.target.closest(".tariff-create");
        if (createBtn) {
          await createTariff(createBtn.closest("tr"));
          await loadAndRender();
        }
      });
    }
  });
}

function ftlColumns(state) {
  return [
    {
      key: "tariff_type",
      label: "Type",
      render: r => tariffTypeSelect(r.tariff_type, ["FTL"])
    },
    {
      key: "carrier_short_name",
      label: "Carrier",
      render: r => selectInput(r, "carrier_short_name", optionsFromState(state, "carrier_short_name"))
    },
    {
      key: "origin_code",
      label: "Origin",
      render: r => input(r, "origin_code")
    },
    {
      key: "destination_code",
      label: "Destination",
      render: r => input(r, "destination_code")
    },
    {
      key: "means_of_transport",
      label: "Means of Transport",
      render: r => selectInput(r, "means_of_transport", optionsFromState(state, "means_of_transport"))
    },
    {
      key: "deviation_bucket",
      label: "Deviation Bucket",
      render: r => selectInput(r, "deviation_bucket", optionsFromState(state, "deviation_bucket"))
    },
    {
      key: "base_cost",
      label: "Base Cost",
      align: "right",
      render: r => numberInput(r, "base_cost")
    },
    {
      key: "roundtrip_base_cost",
      label: "Roundtrip Base Cost",
      align: "right",
      render: r => numberInput(r, "roundtrip_base_cost")
    },
    {
      key: "stop_cost",
      label: "Stop Cost",
      align: "right",
      render: r => numberInput(r, "stop_cost")
    },
    {
      key: "actions",
      label: "Actions",
      align: "center",
      render: () => `<button type="button" class="tariff-save">Save</button>`
    }
  ];
}

function ltlHubColumns(state) {
  return [
    {
      key: "tariff_type",
      label: "Type",
      render: r => tariffTypeSelect(r.tariff_type, ["LTL", "HUB"])
    },
    {
      key: "carrier_short_name",
      label: "Carrier",
      render: r => selectInput(r, "carrier_short_name", optionsFromState(state, "carrier_short_name"))
    },
    {
      key: "origin_code",
      label: "Origin",
      render: r => input(r, "origin_code")
    },
    {
      key: "destination_code",
      label: "Destination",
      render: r => input(r, "destination_code")
    },
    {
      key: "chargeable_weight_bracket",
      label: "Chargeable Weight Bracket",
      render: r => selectInput(r, "chargeable_weight_bracket", optionsFromState(state, "chargeable_weight_bracket"))
    },
    {
      key: "cost_per_100kg",
      label: "Cost per 100kg",
      align: "right",
      render: r => numberInput(r, "cost_per_100kg")
    },
    {
      key: "min_price",
      label: "Min Price",
      align: "right",
      render: r => numberInput(r, "min_price")
    },
    {
      key: "max_price",
      label: "Max Price",
      align: "right",
      render: r => numberInput(r, "max_price")
    },
    {
      key: "actions",
      label: "Actions",
      align: "center",
      render: () => `<button type="button" class="tariff-save">Save</button>`
    }
  ];
}

function renderTariffHeader(columns) {
  const thead = $id("tariffs-thead");

  thead.innerHTML = `
    <tr>
      ${columns.map(col => `
        <th>
          <div class="th-content ${col.align === "center" ? "center" : ""}">
            <span>${text(col.label)}</span>
            ${col.key !== "actions"
              ? `<button class="table-filter-btn" data-field="${text(col.key)}" type="button">▼</button>`
              : ""}
          </div>
        </th>
      `).join("")}
    </tr>
  `;
}

function updateTariffTabs() {
  const isFtl = tariffMode === "ftl";

  $id("tariffs-tab-ftl")?.classList.toggle("active", isFtl);
  $id("tariffs-tab-ltl")?.classList.toggle("active", !isFtl);

  $id("tariffs-title").textContent = isFtl
    ? "Tariffs - FTL / MR"
    : "Tariffs - LTL / Hub";
}

function addEmptyTariffRow(state) {
  const tbody = $id("tariffs-tbody");
  const row = document.createElement("tr");

  row.innerHTML = tariffMode === "ftl"
    ? emptyFtlRowHtml(state)
    : emptyLtlHubRowHtml(state);

  tbody.prepend(row);
}

function emptyFtlRowHtml(state) {
  return `
    <td>${tariffTypeSelect("FTL", ["FTL"])}</td>
    <td>${selectInput({}, "carrier_short_name", optionsFromState(state, "carrier_short_name"))}</td>
    <td>${input({}, "origin_code")}</td>
    <td>${input({}, "destination_code")}</td>
    <td>${selectInput({}, "means_of_transport", optionsFromState(state, "means_of_transport"))}</td>
    <td>${selectInput({}, "deviation_bucket", optionsFromState(state, "deviation_bucket"))}</td>
    <td>${numberInput({}, "base_cost")}</td>
    <td>${numberInput({}, "roundtrip_base_cost")}</td>
    <td>${numberInput({}, "stop_cost")}</td>
    <td><button type="button" class="tariff-create">Create</button></td>
  `;
}

function emptyLtlHubRowHtml(state) {
  return `
    <td>${tariffTypeSelect("LTL", ["LTL", "HUB"])}</td>
    <td>${selectInput({}, "carrier_short_name", optionsFromState(state, "carrier_short_name"))}</td>
    <td>${input({}, "origin_code")}</td>
    <td>${input({}, "destination_code")}</td>
    <td>${selectInput({}, "chargeable_weight_bracket", optionsFromState(state, "chargeable_weight_bracket"))}</td>
    <td>${numberInput({}, "cost_per_100kg")}</td>
    <td>${numberInput({}, "min_price")}</td>
    <td>${numberInput({}, "max_price")}</td>
    <td><button type="button" class="tariff-create">Create</button></td>
  `;
}

function optionsFromState(state, field) {
  return state.options?.[field] || [];
}

function tariffTypeSelect(selected, values) {
  return `
    <select class="table-cell-control" data-field="tariff_type">
      ${values.map(v => option(v, selected)).join("")}
    </select>
  `;
}

function input(row, field) {
  return `
    <input
      class="table-cell-control"
      data-field="${field}"
      value="${text(row[field])}"
    />
  `;
}

function numberInput(row, field) {
  return `
    <input
      class="table-cell-control number"
      data-field="${field}"
      type="number"
      step="0.01"
      value="${row[field] ?? ""}"
    />
  `;
}

function selectInput(row, field, values) {
  const current = row[field] ?? "";

  return `
    <select class="table-cell-control" data-field="${field}">
      <option value=""></option>
      ${values.map(v => option(v, current)).join("")}
    </select>
  `;
}

function option(value, selected) {
  const v = String(value ?? "");
  const s = String(selected ?? "");

  return `<option value="${text(v)}" ${v === s ? "selected" : ""}>${text(v)}</option>`;
}

async function createTariff(row) {
  const tariffType = row.querySelector('[data-field="tariff_type"]')?.value;

  await apiPost("/api/tariffs", {
    tariff: collectTariff(row, tariffType)
  });
}

async function saveTariff(row) {
  const tariffType = row.querySelector('[data-field="tariff_type"]')?.value;

  await apiPut("/api/tariffs", {
    tariff: collectTariff(row, tariffType)
  });
}

function collectTariff(row, tariff_type) {
  const data = { tariff_type };

  row.querySelectorAll("[data-field]").forEach(input => {
    const field = input.dataset.field;
    data[field] = input.type === "number" ? Number(input.value) : input.value.trim();
  });

  return data;
}

