# Askloud GUI — Claude Reference

## What this is

A Django web GUI for the Askloud cloud inventory chat engine (parent directory).
The GUI wraps the same `CloudInventoryEngine` used by the CLI but serves queries
over HTTP and renders results in the browser.

---

## Directory layout

```
askloud_gui/              ← Django project root (this directory)
  manage.py
  requirements.txt
  claude.md               ← this file
  askloud_gui/            ← Django settings package
    settings.py
    urls.py
    wsgi.py
  chat/                   ← Django app
    apps.py               ← initialises EngineManager on startup
    engine_wrapper.py     ← THE KEY FILE: intercepts engine output
    views.py              ← HTTP endpoints
    urls.py
    templates/chat/index.html   ← single-page chat UI
    static/chat/
      app.js              ← all frontend logic
      style.css
```

Parent directory (`../`):
- `askloud/`          — the engine Python package
- `data/`             — JSON snapshot files (loaded by the engine)
- `config/`           — `.conf` files controlling display columns

---

## How to run

```bash
cd askloud_gui
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python manage.py runserver 8000
# Then open http://localhost:8000
```

`ASKLOUD_BASE_DIR` env var overrides where data/ and config/ are searched.
Default: the parent of the Django project root (`../`).

---

## Architecture — the critical design constraint

**The LLM never generates table HTML or chart code.**

Flow for every query:
1. Browser sends `POST /api/query/` with `{"query": "..."}`.
2. `views.api_query` calls `EngineManager.execute_query(session_id, query)`.
3. `engine_wrapper.py` patches `askloud.engine.print_table` with a capture
   function and redirects stdout, then calls the real engine.
4. The LLM (if called) returns only a **JSON query plan** (same as CLI).
5. The engine executes the plan against local data and calls `print_table`.
6. The patched `print_table` stores `{type, title, headers, rows, provider}`
   in a thread-local capture context instead of printing.
7. `_maybe_chart()` analyses each table and optionally generates a Plotly
   chart spec (no LLM involved).
8. The view returns `{"items": [...], "cost_info": ..., "error": ...}`.
9. `app.js` renders tables with **Tabulator.js** and charts with **Plotly.js**.
   No table HTML ever comes from the LLM.

This keeps output token cost low (the LLM sends a compact plan, not rows)
and table rendering rich (Tabulator adds sort, filter, pagination for free).

---

## Key files to edit

### `chat/engine_wrapper.py`
- **`_patched_print_table`** — the capture shim; replaces `print_table` in
  `askloud.engine` at import time.
- **`_apply_patch()`** — called at module import; patches both `askloud.engine`
  and `askloud.display` so all code paths are covered.
- **`_maybe_chart(table)`** — heuristic that picks a suitable categorical
  column and returns a Plotly chart spec dict, or `None`.  Edit
  `_CHART_COLUMNS` to change which columns trigger chart generation.
- **`EngineManager`** — singleton; holds one `CloudInventoryEngine` instance.
  `_histories` dict maps `session_id → history list` so each browser tab
  has its own conversation context.
- **`_parse_stdout(raw)`** — separates cost/token lines from informational
  messages in the captured stdout.

### `chat/views.py`
- `api_query` — the main query endpoint; returns structured JSON.
- `api_mode`  — switches snapshot/live; returns `{"mode": "..."}`.
- `api_history` (DELETE) — clears per-session conversation history.

### `chat/static/chat/app.js`
- `buildTableCard(item)` — creates a Tabulator instance from
  `{headers, rows, provider}`. **Never accepts HTML from the server.**
- `buildChartCard(item)` — calls `Plotly.newPlot` from
  `{chart_type, labels, values, provider}`.
- `pollStatus()` — GETs `/api/status/` on load and after each query to
  refresh snapshot age and resource list.

### `chat/templates/chat/index.html`
Loads Tabulator and Plotly from CDN.  No table or chart markup is hardcoded —
everything is created dynamically by `app.js`.

---

## Adding a new chart type

1. In `engine_wrapper.py → _maybe_chart()`, detect the condition and return a
   dict with `"type": "chart"`, `"chart_type": "pie"|"bar"|"scatter"`, etc.
2. In `app.js → buildChartCard()`, add a branch for the new `chart_type` and
   construct the appropriate Plotly trace.

## Adding a new API endpoint

1. Add a view function to `chat/views.py`.
2. Add a URL pattern to `chat/urls.py`.
3. If it needs the engine, call `EngineManager.get().some_method(...)`.

## Changing the Tabulator column options

Edit `buildTableCard()` in `app.js`.  The `columns` array is built from
`item.headers` — `headerFilter`, `sorter`, `formatter`, width, etc. can
all be set here without touching the server.

## Changing the Plotly chart style

Edit `buildChartCard()` in `app.js`.  `layout` controls colours and fonts.
The dark theme values (paper_bgcolor `#1a1d27`, etc.) match `style.css`.

---

## Session handling

Django sessions use the LocMemCache backend (no DB required).
`EngineManager._histories[session_id]` stores the conversation history list
for each browser session.  The engine's `self.history` is swapped in/out
around each query so multi-tab use doesn't cross-contaminate history.

---

## Environment variables

| Variable           | Default              | Purpose                                |
|--------------------|----------------------|----------------------------------------|
| ANTHROPIC_API_KEY  | —                    | Required for LLM calls                |
| ASKLOUD_BASE_DIR   | `../` (parent dir)   | Where data/ and config/ live          |
| DJANGO_SECRET_KEY  | dev default          | Change in production                  |
| DJANGO_DEBUG       | `true`               | Set `false` to disable debug mode     |

---

## Common issues

**Engine fails to initialize**
The status badge shows "Error".  Check:
- `ANTHROPIC_API_KEY` is set (needed even just to instantiate the client).
- `ASKLOUD_BASE_DIR` points to the directory containing `data/` and `config/`.
- The `askloud` Python package is importable (it lives in the parent dir and
  `EngineManager.initialize()` adds it to `sys.path`).

**Tables appear empty**
Tabulator is deferred with `requestAnimationFrame`.  The element must be in
the DOM before the Tabulator constructor runs — the current code handles this
correctly; don't move the `card.appendChild(tableDiv)` call.

**Charts don't appear**
`_maybe_chart` returns `None` when a table has fewer than 2 rows or no
column matching `_CHART_COLUMNS`.  This is intentional — not every result
needs a chart.

**`print_table` patch not working**
`askloud.engine` imports `print_table` with `from .display import print_table`,
which binds it as a module-level name in `engine.py`.  The patch in
`_apply_patch()` replaces that name directly: `_em.print_table = ...`.
This must happen before any engine instance is created.  `apps.py → ready()`
calls `initialize()` after Django's app registry is set up, which is
after all module imports, so the patch is in place in time.
