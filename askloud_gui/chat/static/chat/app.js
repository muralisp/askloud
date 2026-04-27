/**
 * Askloud GUI — frontend app.
 *
 * Layout:
 *   Left  (data-panel)  — tables and charts from the latest query
 *   Right (chat-panel)  — conversation history and query input
 */

"use strict";

// ── Provider colours ──────────────────────────────────────────────────────

const PROVIDER_COLORS = {
  aws:   "#FF9900",
  azure: "#0078D4",
  gcp:   "#34A853",
};

// ── DOM references ────────────────────────────────────────────────────────

const queryForm     = document.getElementById("query-form");
const queryInput    = document.getElementById("query-input");
const sendBtn       = document.getElementById("send-btn");
const messagesEl    = document.getElementById("messages");      // chat panel
const dataArea      = document.getElementById("data-area");     // data panel
const statusBadge   = document.getElementById("status-badge");
const modeBadge     = document.getElementById("mode-badge");
const toggleModeBtn = document.getElementById("toggle-mode");
const clearHistBtn  = document.getElementById("clear-history");
const statusBar     = document.getElementById("status-bar");
const resourcesLbl  = document.getElementById("resources-label");
const ageLbl        = document.getElementById("age-label");
const costBar       = document.getElementById("cost-bar");

// ── State ─────────────────────────────────────────────────────────────────

let currentMode = "snapshot";

// ── Utility ───────────────────────────────────────────────────────────────

function getCsrfToken() {
  for (const c of document.cookie.split(";")) {
    const [k, v] = c.trim().split("=");
    if (k === "csrftoken") return decodeURIComponent(v);
  }
  return "";
}

async function apiPost(url, data, method = "POST") {
  const res = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken":  getCsrfToken(),
    },
    body: method !== "DELETE" ? JSON.stringify(data) : undefined,
  });
  return res.json();
}

function scrollChatToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Data panel helpers ────────────────────────────────────────────────────

/** Replace data panel content with the empty-state placeholder. */
function clearDataPanel() {
  dataArea.innerHTML = `
    <div class="data-empty">
      <div class="data-empty-icon">☁</div>
      <div class="data-empty-title">Thinking…</div>
    </div>`;
}

/** Remove any empty-state placeholder before appending real content. */
function removeEmptyState() {
  const empty = dataArea.querySelector(".data-empty");
  if (empty) empty.remove();
}

// ── Status polling ────────────────────────────────────────────────────────

async function pollStatus() {
  try {
    const data = await fetch("/api/status/").then(r => r.json());

    if (data.ready) {
      statusBadge.textContent = "Ready";
      statusBadge.className   = "badge badge-ready";
      resourcesLbl.textContent = "Resources: " + (data.resources || []).join(", ");
      ageLbl.textContent = data.snapshot_age ? `Snapshot: ${data.snapshot_age} old` : "";
      statusBar.classList.remove("hidden");
    } else if (data.init_error) {
      statusBadge.textContent = "Error";
      statusBadge.className   = "badge badge-error";
      appendTextToChat("Engine init error: " + data.init_error, "error");
    } else {
      setTimeout(pollStatus, 800);
      return;
    }

    updateModeBadge(data.mode || "snapshot");
  } catch {
    setTimeout(pollStatus, 1500);
  }
}

function updateModeBadge(mode) {
  currentMode           = mode;
  modeBadge.textContent = mode;
  modeBadge.className   = mode === "live" ? "badge badge-live" : "badge badge-snapshot";
  toggleModeBtn.textContent = mode === "live" ? "Switch to snapshot" : "Switch to live";
}

// ── Query submission ──────────────────────────────────────────────────────

queryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  queryInput.value = "";
  setInputDisabled(true);
  appendUserMessage(query);
  clearDataPanel();

  // Client-side slash commands
  if (query === "/live" || query === "/snapshot" || query === "/snap") {
    const mode = query.startsWith("/live") ? "live" : "snapshot";
    const res  = await apiPost("/api/mode/", { mode });
    updateModeBadge(res.mode);
    appendTextToChat(`Switched to ${res.mode} mode.`);
    restoreDataPanelIdle();
    setInputDisabled(false);
    return;
  }

  const thinkingEl = appendThinking();

  try {
    const result = await apiPost("/api/query/", { query });
    thinkingEl.remove();

    renderResult(result.items || []);

    if (result.error) {
      appendTextToChat("Error: " + result.error, "error");
    }

    if (result.cost_info) {
      costBar.textContent = result.cost_info;
      costBar.classList.remove("hidden");
    }
  } catch (err) {
    thinkingEl.remove();
    appendTextToChat("Network error: " + err.message, "error");
    restoreDataPanelIdle();
  } finally {
    setInputDisabled(false);
    queryInput.focus();
    pollStatus();
  }
});

// ── Mode toggle ────────────────────────────────────────────────────────────

toggleModeBtn.addEventListener("click", async () => {
  const newMode = currentMode === "live" ? "snapshot" : "live";
  const res     = await apiPost("/api/mode/", { mode: newMode });
  updateModeBadge(res.mode);
  appendTextToChat(`Switched to ${res.mode} mode.`);
});

// ── History clear ──────────────────────────────────────────────────────────

clearHistBtn.addEventListener("click", async () => {
  await fetch("/api/history/", {
    method: "DELETE",
    headers: { "X-CSRFToken": getCsrfToken() },
  });
  messagesEl.innerHTML = "";
  costBar.classList.add("hidden");
  restoreDataPanelIdle();
  appendTextToChat("Conversation history cleared.");
});

// ── Result rendering ──────────────────────────────────────────────────────

/**
 * Route result items:
 *   tables + charts  → data panel (left)
 *   text messages    → chat panel (right)
 */
function renderResult(items) {
  let hasData = false;

  for (const item of items) {
    if (item.type === "table") {
      removeEmptyState();
      dataArea.appendChild(buildTableCard(item));
      hasData = true;
    } else if (item.type === "chart") {
      removeEmptyState();
      dataArea.appendChild(buildChartCard(item));
      hasData = true;
    } else if (item.type === "message") {
      appendTextToChat(item.text);
    }
  }

  if (!hasData) {
    // No table/chart returned — show idle state
    restoreDataPanelIdle();
  }
}

function restoreDataPanelIdle() {
  if (!dataArea.querySelector(".result-card, .chart-card")) {
    dataArea.innerHTML = `
      <div class="data-empty">
        <div class="data-empty-icon">☁</div>
        <div class="data-empty-title">Ask Askloud anything</div>
        <div class="data-empty-hint">e.g. "list running EC2 instances" or "show all Azure VMs by region"</div>
      </div>`;
  }
}

// ── Chat panel helpers ────────────────────────────────────────────────────

function setInputDisabled(disabled) {
  queryInput.disabled = disabled;
  sendBtn.disabled    = disabled;
}

function appendUserMessage(text) {
  const el = document.createElement("div");
  el.className   = "msg-user";
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollChatToBottom();
}

function appendThinking() {
  const el = document.createElement("div");
  el.className   = "msg-thinking";
  el.textContent = "Thinking…";
  messagesEl.appendChild(el);
  scrollChatToBottom();
  return el;
}

function appendTextToChat(text, variant) {
  const wrapper = document.createElement("div");
  wrapper.className = "msg-assistant";

  const el = document.createElement("div");
  let cls = "msg-text";
  if (variant === "error" || text.toLowerCase().includes("error") || text.toLowerCase().includes("failed")) {
    cls += " error";
  } else if (variant === "warn" || text.toLowerCase().includes("warning") || text.toLowerCase().includes("no results")) {
    cls += " warn";
  }
  el.className   = cls;
  el.textContent = text;

  wrapper.appendChild(el);
  messagesEl.appendChild(wrapper);
  scrollChatToBottom();
}

// ── Table card (Tabulator) ────────────────────────────────────────────────

function buildTableCard(item) {
  const color    = PROVIDER_COLORS[item.provider] || PROVIDER_COLORS.aws;
  const rowCount = (item.rows || []).length;

  const card = document.createElement("div");
  card.className = "result-card";

  const header = document.createElement("div");
  header.className = "result-card-header";
  header.innerHTML = `
    <span>
      <span class="provider-dot" style="background:${color}"></span>
      ${escapeHtml(item.title || "")}
    </span>
    <span class="row-count">${rowCount} row${rowCount !== 1 ? "s" : ""}</span>
  `;
  card.appendChild(header);

  const tableDiv = document.createElement("div");
  tableDiv.style.width = "100%";
  card.appendChild(tableDiv);

  requestAnimationFrame(() => {
    const columns = (item.headers || []).map(h => ({
      title:        h,
      field:        h,
      headerFilter: "input",
      formatter:    "plaintext",
      minWidth:      80,
    }));

    const tableData = (item.rows || []).map(row => {
      const obj = {};
      (item.headers || []).forEach((h, i) => { obj[h] = row[i] ?? ""; });
      return obj;
    });

    new Tabulator(tableDiv, {
      data:            tableData,
      columns,
      layout:          "fitDataFill",
      maxHeight:       "calc(100vh - 160px)",
      pagination:      true,
      paginationMode:  "local",
      paginationSize:  25,
      paginationSizeSelector: [10, 25, 50, 100],
      movableColumns:  true,
      resizableRows:   false,
      selectable:      false,
      headerFilterLiveFilterDelay: 200,
      placeholder:     "No results",
    });
  });

  return card;
}

// ── Chart card (Plotly) ───────────────────────────────────────────────────

function buildChartCard(item) {
  const color = PROVIDER_COLORS[item.provider] || PROVIDER_COLORS.aws;

  const card = document.createElement("div");
  card.className = "chart-card";

  const header = document.createElement("div");
  header.className = "chart-header";
  header.textContent = item.title || "Chart";
  card.appendChild(header);

  const container = document.createElement("div");
  container.className = "chart-container";
  const plotDiv = document.createElement("div");
  plotDiv.style.height = "280px";
  container.appendChild(plotDiv);
  card.appendChild(container);

  requestAnimationFrame(() => {
    const layout = {
      paper_bgcolor: "#1a1d27",
      plot_bgcolor:  "#1a1d27",
      font:  { color: "#e2e8f0", family: "Segoe UI, system-ui, sans-serif", size: 12 },
      margin: { t: 10, b: 40, l: 40, r: 10 },
      legend: { orientation: "v", x: 1, xanchor: "right", y: 1 },
      showlegend: item.chart_type === "pie",
    };

    let trace;
    if (item.chart_type === "pie") {
      trace = {
        type:           "pie",
        labels:         item.labels,
        values:         item.values,
        hole:           0.35,
        marker:         { line: { color: "#0f1117", width: 1.5 } },
        textinfo:       "label+percent",
        textposition:   "auto",
        insidetextfont: { color: "#fff" },
      };
    } else {
      trace = {
        type:    "bar",
        x:       item.labels,
        y:       item.values,
        marker:  { color, opacity: 0.85 },
        text:    item.values,
        textposition: "auto",
      };
      layout.xaxis = { tickangle: -30, color: "#8892a4", gridcolor: "#2e3250" };
      layout.yaxis = { color: "#8892a4", gridcolor: "#2e3250" };
    }

    Plotly.newPlot(plotDiv, [trace], layout, { responsive: true, displayModeBar: false });
  });

  return card;
}

// ── Boot ──────────────────────────────────────────────────────────────────

pollStatus();
