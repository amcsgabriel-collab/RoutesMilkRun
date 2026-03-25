import { apiGet } from "../api.js";
import { loadHtml } from "../utils.js";

function getNestedValue(obj, path) {
    return path.split('.').reduce((acc, key) => acc?.[key], obj);
}

function isMissing(value) {
    return value === undefined || value === null || Number.isNaN(value);
}

function formatInteger(value) {
    return new Intl.NumberFormat('en-GB', {
        maximumFractionDigits: 0
    }).format(value);
}

function formatDecimal(value, digits = 2) {
    return new Intl.NumberFormat('en-GB', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
    }).format(value);
}

function formatCurrency(value, digits = 0) {
    return `€ ${new Intl.NumberFormat('en-GB', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
    }).format(value)}`;
}

function formatPercent(value) {
    return `${formatDecimal(value, 1)}%`;
}

function formatKg(value) {
    return `${formatDecimal(value, 0)} kg`;
}

function formatM3(value) {
    return `${formatDecimal(value, 1)} m³`;
}

function formatLm(value) {
    return `${formatDecimal(value, 1)} lm`;
}

function formatSigned(value, formatter) {
    if (isMissing(value)) {
        return '—';
    }

    if (value === 0) {
        return formatter(0);
    }

    const absValue = Math.abs(value);
    const sign = value > 0 ? '-' : '+';
    return `${sign}${formatter(absValue)}`;
}

function formatKpiValue(value, formatType) {
    if (isMissing(value)) {
        return '—';
    }

    switch (formatType) {
        case 'integer':
            return formatInteger(value);
        case 'currency':
            return formatCurrency(value, 0);
        case 'currency2':
            return formatCurrency(value, 2);
        case 'currency3':
            return formatCurrency(value, 3);
        case 'percent':
            return formatPercent(value);
        case 'kg':
            return formatKg(value);
        case 'm3':
            return formatM3(value);
        case 'lm':
            return formatLm(value);

        case 'delta-integer':
            return formatSigned(value, formatInteger);
        case 'delta-currency':
            return formatSigned(value, v => formatCurrency(v, 0));
        case 'delta-currency2':
            return formatSigned(value, v => formatCurrency(v, 2));
        case 'delta-currency3':
            return formatSigned(value, v => formatCurrency(v, 3));
        case 'delta-pp':
            return formatSigned(value, v => `${formatDecimal(v, 1)} pp`);
        case 'delta-kg':
            return formatSigned(value, v => `${formatDecimal(v, 0)} kg`);
        case 'delta-m3':
            return formatSigned(value, v => `${formatDecimal(v, 1)} m³`);
        case 'delta-lm':
            return formatSigned(value, v => `${formatDecimal(v, 1)} lm`);

        default:
            return String(value);
    }
}

function applyDeltaClass(element, deltaValue, betterWhen) {
    element.classList.remove('delta-positive', 'delta-negative', 'delta-neutral');

    const numericDelta =
        typeof deltaValue === 'number' ? deltaValue : Number(deltaValue);

    const normalizedBetterWhen = String(betterWhen ?? '')
        .trim()
        .toLowerCase()
        .replaceAll(' ', '_')
        .replaceAll('-', '_');

    if (
        isMissing(numericDelta) ||
        numericDelta === 0 ||
        !normalizedBetterWhen ||
        normalizedBetterWhen === 'neutral'
    ) {
        element.classList.add('delta-neutral');
        return;
    }

    const isImprovement =
        (normalizedBetterWhen === 'lower' && numericDelta > 0) ||
        (normalizedBetterWhen === 'higher' && numericDelta < 0);

    element.classList.add(isImprovement ? 'delta-positive' : 'delta-negative');
}

function renderScenarioKpis(kpiData) {
    console.log("renderScenarioKpis called", kpiData);
    const elements = document.querySelectorAll('[data-kpi]');

    elements.forEach((element) => {
        const path = element.dataset.kpi;
        const formatType = element.dataset.format || 'text';
        const value = getNestedValue(kpiData, path);

        element.textContent = formatKpiValue(value, formatType);

        if (path.endsWith('_vs_as_is')) {
            const betterWhenPath = path.replace('_vs_as_is', '_better_when');
            const betterWhen = getNestedValue(kpiData, betterWhenPath);
            applyDeltaClass(element, value, betterWhen);
        }
    });
}

export async function loadScenarioKpis() {
    console.log("loadScenarioKpis called");
    const html = await loadHtml("/views_html/kpi_summary.html");
    document.getElementById("kpi-placeholder").innerHTML = html;
    try {
        const kpiData = await apiGet("/api/scenario/kpis");
        renderScenarioKpis(kpiData);
    } catch(e) {
        alert(e)
    }
}

/*
Example usage:

document.getElementById("scenario-list").addEventListener("click", async (event) => {
    const scenarioItem = event.target.closest("[data-scenario-id]");
    if (!scenarioItem) return;

    const scenarioId = scenarioItem.dataset.scenarioId;

    try {
        await loadScenarioKpis(scenarioId);
    } catch (error) {
        console.error(error);
    }
});
*/