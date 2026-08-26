/**
 * Askloud GUI — two-tab layout.
 *
 * Inventory tab — chat feed, inventory (DynamoDB/snapshot) mode
 * Live tab      — chat feed, live cloud-API mode
 *
 * Each tab has its own independent conversation history (separate UUID
 * session IDs are passed in the request body).
 */

"use strict";

// ── Provider colours ──────────────────────────────────────────────────────

const PROVIDER_COLORS = { aws: "#FF9900", azure: "#0078D4", gcp: "#34A853" };

// ── Per-tab session IDs (independent LLM histories) ───────────────────────

const SESSION_IDS = {
  inventory: "inv-"  + crypto.randomUUID(),
  live:      "live-" + crypto.randomUUID(),
};

// ── DOM references ────────────────────────────────────────────────────────

const queryForm    = document.getElementById("query-form");
const queryInput   = document.getElementById("query-input");
const sendBtn      = document.getElementById("send-btn");
const statusBadge  = document.getElementById("status-badge");
const clearHistBtn = document.getElementById("clear-history");
const statusBar    = document.getElementById("status-bar");
const resourcesLbl = document.getElementById("resources-label");
const ageLbl       = document.getElementById("age-label");
const inputBar     = document.getElementById("input-bar");

const inventoryPane = document.getElementById("inventory-pane");
const livePane      = document.getElementById("live-pane");
const inventoryFeed = document.getElementById("inventory-feed");
const liveFeed      = document.getElementById("live-feed");

// ── State ─────────────────────────────────────────────────────────────────

let activeTab = "inventory"; // "inventory" | "live"

// ── Utility ───────────────────────────────────────────────────────────────

function getCsrfToken() {
  for (const c of document.cookie.split(";")) {
    const [k, v] = c.trim().split("=");
    if (k === "csrftoken") return decodeURIComponent(v);
  }
  return "";
}

async function apiPost(url, data) {
  const res = await fetch(url, {
    method:  "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body:    JSON.stringify(data),
  });
  return res.json();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Feed / pane accessors ─────────────────────────────────────────────────

function activeFeedEl()    { return activeTab === "live" ? liveFeed    : inventoryFeed; }
function activePaneEl()    { return activeTab === "live" ? livePane    : inventoryPane; }
function activeSessionId() { return SESSION_IDS[activeTab]; }

function scrollPaneToBottom(pane) { pane.scrollTop = pane.scrollHeight; }

// ── Welcome state ─────────────────────────────────────────────────────────

const WELCOME_INVENTORY = `
  <div class="feed-welcome">
    <div class="feed-welcome-icon">☁</div>
    <div class="feed-welcome-title">Ask Askloud anything</div>
    <div class="feed-welcome-hint">e.g. "list running EC2 instances" or "show all Azure VMs by region"</div>
  </div>`;

const WELCOME_LIVE = `
  <div class="feed-welcome">
    <div class="feed-welcome-icon">⚡</div>
    <div class="feed-welcome-title">Live cloud queries</div>
    <div class="feed-welcome-hint">Queries run directly against your cloud provider APIs in real time.</div>
  </div>`;

function removeWelcome(feedEl) {
  const w = feedEl.querySelector(".feed-welcome");
  if (w) w.remove();
}

// ── Tab switching ─────────────────────────────────────────────────────────

async function switchTab(tab) {
  if (tab === activeTab) return;

  apiPost("/api/mode/", { mode: tab === "live" ? "live" : "snapshot" });

  inventoryPane.classList.toggle("hidden", tab !== "inventory");
  livePane.classList.toggle("hidden",      tab !== "live");

  document.querySelectorAll(".main-tab[data-tab]").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });

  document.body.classList.toggle("tab-live", tab === "live");
  activeTab = tab;
  queryInput.focus();
}

// ── Status polling ────────────────────────────────────────────────────────

async function pollStatus() {
  try {
    const data = await fetch("/api/status/").then(r => r.json());
    if (data.ready) {
      statusBadge.textContent  = "Ready";
      statusBadge.className    = "badge badge-ready";
      resourcesLbl.textContent = "Resources: " + (data.resources || []).join(", ");
      ageLbl.textContent       = data.snapshot_age ? `Inventory: ${data.snapshot_age}` : "";
      statusBar.classList.remove("hidden");
    } else if (data.init_error) {
      statusBadge.textContent = "Error";
      statusBadge.className   = "badge badge-error";
    } else {
      setTimeout(pollStatus, 800);
      return;
    }
  } catch {
    setTimeout(pollStatus, 1500);
  }
}

// ── Tab click handlers ────────────────────────────────────────────────────

document.querySelectorAll(".main-tab[data-tab]").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// ── Query submission ──────────────────────────────────────────────────────

queryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  queryInput.value = "";
  setInputDisabled(true);

  const feedEl = activeFeedEl();
  const paneEl = activePaneEl();

  const turnResponse = appendUserTurn(feedEl, query);
  const thinkingEl   = appendThinking(turnResponse);

  try {
    const result = await apiPost("/api/query/", { query, session_id: activeSessionId() });
    thinkingEl.remove();
    renderResult(result.items || [], turnResponse);
    if (result.error)     appendTurnMessage(turnResponse, "Error: " + result.error, "error");
    if (result.cost_info) appendCostInfo(turnResponse, result.cost_info);
  } catch (err) {
    thinkingEl.remove();
    appendTurnMessage(turnResponse, "Network error: " + err.message, "error");
  } finally {
    setInputDisabled(false);
    queryInput.focus();
    scrollPaneToBottom(paneEl);
    pollStatus();
  }
});

// ── History clear ──────────────────────────────────────────────────────────

clearHistBtn.addEventListener("click", async () => {
  const sid = activeSessionId();
  await fetch(`/api/history/?sid=${encodeURIComponent(sid)}`, {
    method: "DELETE", headers: { "X-CSRFToken": getCsrfToken() },
  });
  activeFeedEl().innerHTML = activeTab === "live" ? WELCOME_LIVE : WELCOME_INVENTORY;
});

// ── Input helpers ─────────────────────────────────────────────────────────

function setInputDisabled(disabled) {
  queryInput.disabled = disabled;
  sendBtn.disabled    = disabled;
}

// ── Feed turn helpers ─────────────────────────────────────────────────────

function appendUserTurn(feedEl, query) {
  removeWelcome(feedEl);

  const turn = document.createElement("div");
  turn.className = "turn";

  const queryEl = document.createElement("div");
  queryEl.className   = "turn-query";
  queryEl.textContent = query;

  const response = document.createElement("div");
  response.className = "turn-response";

  turn.appendChild(queryEl);
  turn.appendChild(response);
  feedEl.appendChild(turn);
  scrollPaneToBottom(activePaneEl());
  return response;
}

function appendThinking(target) {
  const el = document.createElement("div");
  el.className   = "turn-thinking";
  el.textContent = "Thinking…";
  target.appendChild(el);
  return el;
}

function appendTurnMessage(target, text, variant) {
  const el    = document.createElement("div");
  const lower = (text || "").toLowerCase();
  let   cls   = "msg-text";
  if (variant === "error" || lower.includes("error") || lower.includes("failed")) cls += " error";
  else if (variant === "warn" || lower.includes("warning") || lower.includes("no results")) cls += " warn";
  el.className   = cls;
  el.textContent = text;
  target.appendChild(el);
}

function appendCostInfo(target, text) {
  const el = document.createElement("div");
  el.className   = "turn-cost";
  el.textContent = text;
  target.appendChild(el);
}

function appendSystemMessage(feedEl, text, variant) {
  const wrapper = document.createElement("div");
  wrapper.className = "sys-message";
  const el = document.createElement("div");
  el.className   = "sys-message-text" + (variant ? " " + variant : "");
  el.textContent = text;
  wrapper.appendChild(el);
  feedEl.appendChild(wrapper);
}

// ── Result rendering ──────────────────────────────────────────────────────

function renderResult(items, turnResponse) {
  items.filter(i => i.type === "message").forEach(i => appendTurnMessage(turnResponse, i.text));

  const groups = [];
  for (const item of items) {
    if (item.type === "table")                       groups.push({ table: item, chart: null });
    else if (item.type === "chart" && groups.length) groups[groups.length - 1].chart = item;
  }
  if (groups.length === 0) return;

  if (groups.length === 1) {
    turnResponse.appendChild(buildTableCard(groups[0].table));
    if (groups[0].chart) turnResponse.appendChild(buildChartCard(groups[0].chart));
  } else {
    turnResponse.appendChild(buildTabbedResult(groups));
  }
  scrollPaneToBottom(activePaneEl());
}

// ── Tabbed multi-result ───────────────────────────────────────────────────

function buildTabbedResult(groups) {
  const wrapper  = document.createElement("div");
  wrapper.className = "tabs-wrapper";
  const tabsBar  = document.createElement("div");
  tabsBar.className = "tabs-bar";
  const tabsBody = document.createElement("div");
  tabsBody.className = "tabs-body";

  groups.forEach((group, idx) => {
    const color    = PROVIDER_COLORS[group.table.provider] || PROVIDER_COLORS.aws;
    const rowCount = (group.table.rows || []).length;
    const label    = tabLabel(group.table.title);

    const btn = document.createElement("button");
    btn.className = "tab-btn" + (idx === 0 ? " active" : "");
    btn.style.setProperty("--tab-accent", color);
    btn.innerHTML = `
      <span class="tab-dot" style="background:${color}"></span>
      <span>${escapeHtml(label)}</span>
      <span class="tab-count">${rowCount}</span>
    `;

    const panel = document.createElement("div");
    panel.className = "tab-panel" + (idx === 0 ? " active" : "");
    panel.appendChild(buildTableCard(group.table));
    if (group.chart) panel.appendChild(buildChartCard(group.chart));

    btn.addEventListener("click", () => {
      tabsBar.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      tabsBody.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      panel.classList.add("active");
    });

    tabsBar.appendChild(btn);
    tabsBody.appendChild(panel);
  });

  wrapper.appendChild(tabsBar);
  wrapper.appendChild(tabsBody);
  return wrapper;
}

function tabLabel(title) {
  if (!title) return "Results";
  const bracket = title.match(/^\[([^\]]+)\]/);
  if (bracket) return bracket[1].toUpperCase();
  return title.length > 22 ? title.slice(0, 22) + "…" : title;
}

// ── Table card (Tabulator) ────────────────────────────────────────────────

function buildTableCard(item) {
  const color    = PROVIDER_COLORS[item.provider] || PROVIDER_COLORS.aws;
  const rowCount = (item.rows || []).length;

  const card = document.createElement("div");
  card.className = "result-card";

  const hdr = document.createElement("div");
  hdr.className = "result-card-header";
  hdr.innerHTML = `
    <span>
      <span class="provider-dot" style="background:${color}"></span>
      ${escapeHtml(item.title || "")}
    </span>
    <span class="row-count">${rowCount} row${rowCount !== 1 ? "s" : ""}</span>
  `;
  card.appendChild(hdr);

  const tableDiv = document.createElement("div");
  tableDiv.style.width = "100%";
  card.appendChild(tableDiv);

  requestAnimationFrame(() => {
    const columns = (item.headers || []).map(h => ({
      title: h, field: h, headerFilter: "input", formatter: "plaintext", minWidth: 80,
    }));
    const tableData = (item.rows || []).map(row => {
      const obj = {};
      (item.headers || []).forEach((h, i) => { obj[h] = row[i] ?? ""; });
      return obj;
    });

    const tbl = new Tabulator(tableDiv, {
      data:            tableData,
      columns,
      layout:          "fitDataFill",
      maxHeight:       "52vh",
      pagination:      true,
      paginationMode:  "local",
      paginationSize:  20,
      paginationSizeSelector: [10, 20, 50, 100],
      movableColumns:  true,
      resizableRows:   false,
      selectable:      false,
      headerFilterLiveFilterDelay: 200,
      placeholder:     "No results",
    });
    tbl.on("tableBuilt", () => {
      tableDiv.querySelectorAll(".tabulator-header-filter input").forEach(_wrapWithMagnifier);
    });
  });

  return card;
}

// ── Chart card (Plotly) ───────────────────────────────────────────────────

function buildChartCard(item) {
  const color = PROVIDER_COLORS[item.provider] || PROVIDER_COLORS.aws;
  const card  = document.createElement("div");
  card.className = "chart-card";

  const hdr = document.createElement("div");
  hdr.className   = "chart-header";
  hdr.textContent = item.title || "Chart";
  card.appendChild(hdr);

  const container = document.createElement("div");
  container.className = "chart-container";
  const plotDiv = document.createElement("div");
  plotDiv.style.height = "260px";
  container.appendChild(plotDiv);
  card.appendChild(container);

  requestAnimationFrame(() => {
    const layout = {
      paper_bgcolor: "#1a1d27",
      plot_bgcolor:  "#1a1d27",
      font:   { color: "#e2e8f0", family: "Segoe UI, system-ui, sans-serif", size: 12 },
      margin: { t: 10, b: 40, l: 40, r: 10 },
      legend: { orientation: "v", x: 1, xanchor: "right", y: 1 },
      showlegend: item.chart_type === "pie",
    };
    let trace;
    if (item.chart_type === "pie") {
      trace = {
        type: "pie", labels: item.labels, values: item.values, hole: 0.35,
        marker: { line: { color: "#0f1117", width: 1.5 } },
        textinfo: "label+percent", textposition: "auto",
        insidetextfont: { color: "#fff" },
      };
    } else {
      trace = {
        type: "bar", x: item.labels, y: item.values,
        marker: { color, opacity: 0.85 }, text: item.values, textposition: "auto",
      };
      layout.xaxis = { tickangle: -30, color: "#8892a4", gridcolor: "#2e3250" };
      layout.yaxis = { color: "#8892a4", gridcolor: "#2e3250" };
    }
    Plotly.newPlot(plotDiv, [trace], layout, { responsive: true, displayModeBar: false });
  });

  return card;
}

// ── Magnifier header filter ───────────────────────────────────────────────

function _wrapWithMagnifier(inp) {
  const btn = document.createElement("button");
  btn.type      = "button";
  btn.className = "hf-icon";
  btn.title     = "Filter column";
  btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';

  inp.classList.add("hf-input");

  function open()  { inp.classList.add("hf-open"); btn.classList.add("hf-open"); inp.focus(); }
  function close() {
    inp.value = "";
    inp.dispatchEvent(new Event("input", { bubbles: true }));
    inp.classList.remove("hf-open");
    btn.classList.remove("hf-open", "hf-active");
  }

  btn.addEventListener("click",   e => { e.stopPropagation(); inp.classList.contains("hf-open") ? close() : open(); });
  inp.addEventListener("input",   () => btn.classList.toggle("hf-active", !!inp.value));
  inp.addEventListener("blur",    () => { if (!inp.value) { inp.classList.remove("hf-open"); btn.classList.remove("hf-open"); } });
  inp.addEventListener("keydown", e => { if (e.key === "Escape") { e.stopPropagation(); close(); } });

  inp.parentElement.insertBefore(btn, inp);
}

// ── Boot ──────────────────────────────────────────────────────────────────

pollStatus();
