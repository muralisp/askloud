"""
Engine wrapper for the Askloud Django GUI.

Intercepts CloudInventoryEngine's print_table calls and stdout so that
query results are returned as structured JSON instead of terminal output.
The LLM only ever produces a JSON query plan; the server executes that plan
and builds the table/chart data entirely server-side.

Thread-safety: a single engine instance is shared (appropriate for a local
single-user tool). A per-session history dict swaps conversation state
in/out around each request so multi-tab use works correctly.
"""

import io
import os
import re
import sys
import contextlib
import threading
from typing import Any, Dict, List, Optional


# ── Provider colours for the frontend ──────────────────────────────────────
PROVIDER_COLORS = {
    "aws":   "#FF9900",
    "azure": "#0078D4",
    "gcp":   "#34A853",
}

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ── Chart generation ────────────────────────────────────────────────────────

# Categorical columns, in priority order, that are worth charting.
_CHART_COLUMNS = [
    "State", "InstanceState", "Status", "InstanceType", "Type",
    "Region", "Account", "Zone", "Provider",
]


def _maybe_chart(table: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Analyse table data and return a Plotly-compatible chart spec when the
    data has a suitable categorical breakdown.  Returns None otherwise.
    Minimum 2 distinct values and at least 2 rows required.
    """
    headers = table.get("headers", [])
    rows    = table.get("rows", [])
    if len(rows) < 2:
        return None

    for col in _CHART_COLUMNS:
        if col not in headers:
            continue
        idx = headers.index(col)
        counts: Dict[str, int] = {}
        for row in rows:
            val = row[idx] if idx < len(row) else "N/A"
            counts[val or "N/A"] = counts.get(val or "N/A", 0) + 1
        if len(counts) < 2 or len(counts) > 20:
            continue

        labels = list(counts.keys())
        values = [counts[l] for l in labels]
        chart_type = "pie" if len(counts) <= 8 else "bar"
        title = f"{table['title']} — by {col}" if table.get("title") else f"By {col}"
        return {
            "type":       "chart",
            "chart_type": chart_type,
            "title":      title,
            "labels":     labels,
            "values":     values,
            "column":     col,
            "provider":   table.get("provider", "aws"),
        }
    return None


# ── Capture context (thread-local) ─────────────────────────────────────────

class _CaptureContext:
    def __init__(self):
        self.tables: List[Dict[str, Any]] = []
        self.buf = io.StringIO()


_tl = threading.local()


def _patched_print_table(
    title: str, headers: list, rows: list, provider: str = None
):
    """
    Replaces askloud.engine.print_table during a query.
    Stores structured table data instead of printing to stdout.
    """
    ctx: Optional[_CaptureContext] = getattr(_tl, "ctx", None)
    if ctx is None:
        return   # No active capture; discard (shouldn't happen in practice)
    ctx.tables.append({
        "type":     "table",
        "title":    title or "",
        "headers":  list(headers),
        "rows":     [list(r) for r in rows],
        "provider": provider or "aws",
    })


# Patch the engine module's print_table reference so both snapshot and live
# paths go through our capture function.
def _apply_patch():
    try:
        import askloud.engine as _em
        import askloud.display as _dm
        _em.print_table = _patched_print_table
        _dm.print_table = _patched_print_table
    except ImportError:
        pass


# ── EngineManager ───────────────────────────────────────────────────────────

class EngineManager:
    """
    Singleton that owns a CloudInventoryEngine for the web process.
    Provides thread-safe query execution with per-session history.
    """

    _instance: Optional["EngineManager"] = None
    _cls_lock = threading.Lock()

    def __init__(self):
        self._engine       = None
        self._init_error:  Optional[str] = None
        self._histories:   Dict[str, list] = {}
        self._query_lock   = threading.Lock()   # serialise queries (one engine)

    # ── Singleton accessor ──────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "EngineManager":
        if cls._instance is None:
            with cls._cls_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Initialisation ──────────────────────────────────────────────────────

    def initialize(self, base_dir: str) -> None:
        """
        Must be called once at startup (e.g. from AppConfig.ready()).
        base_dir is the directory that contains data/ and config/.
        """
        if self._engine is not None or self._init_error:
            return
        try:
            # The engine resolves data/ and config/ relative to cwd.
            old_cwd = os.getcwd()
            os.chdir(base_dir)
            # Put base_dir on sys.path so the askloud package is importable.
            if base_dir not in sys.path:
                sys.path.insert(0, base_dir)

            from askloud import CloudInventoryEngine

            # Patch must happen after askloud is importable (i.e. after sys.path is set).
            _apply_patch()

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self._engine = CloudInventoryEngine(mode="snapshot")

            os.chdir(old_cwd)
        except Exception as exc:
            self._init_error = str(exc)

    # ── Status helpers ──────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._engine is not None

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    @property
    def mode(self) -> str:
        return self._engine.mode if self._engine else "snapshot"

    @property
    def resource_types(self) -> List[str]:
        if self._engine:
            return sorted(self._engine._loader.data.keys())
        return []

    @property
    def snapshot_age(self) -> str:
        if self._engine:
            return self._engine._snapshot_age_str()
        return ""

    # ── Mode switching ──────────────────────────────────────────────────────

    def switch_mode(self, mode: str) -> str:
        """Switch between 'snapshot' and 'live'. Returns the active mode."""
        if not self._engine:
            return "snapshot"
        if mode not in ("snapshot", "live"):
            return self._engine.mode
        self._engine._switch_mode(mode)
        return self._engine.mode

    def clear_history(self, session_id: str) -> None:
        self._histories.pop(session_id, None)

    # ── Query execution ─────────────────────────────────────────────────────

    def execute_query(self, session_id: str, user_query: str) -> Dict[str, Any]:
        """
        Execute user_query and return a structured result dict:

        {
          "items": [
            {"type": "table", "title": ..., "headers": [...], "rows": [[...]], "provider": ...},
            {"type": "chart", "chart_type": "pie"|"bar", "title": ..., "labels": [...], "values": [...], ...},
            {"type": "message", "text": ...},
          ],
          "cost_info": "...",   # token/cost line from the engine, or null
          "error": null         # error string or null
        }
        """
        if not self._engine:
            return {"items": [], "cost_info": None,
                    "error": self._init_error or "Engine not initialised"}

        with self._query_lock:
            return self._run_query(session_id, user_query)

    def _run_query(self, session_id: str, user_query: str) -> Dict[str, Any]:
        # Swap in this session's conversation history
        self._engine.history = list(self._histories.get(session_id, []))

        ctx = _CaptureContext()
        _tl.ctx = ctx
        error: Optional[str] = None

        try:
            with contextlib.redirect_stdout(ctx.buf):
                from askloud.filters import is_direct_search
                if self._engine.mode == "snapshot" and is_direct_search(user_query):
                    self._engine.direct_search(user_query)
                else:
                    self._engine.process_query(user_query)
        except Exception as exc:
            error = str(exc)
        finally:
            _tl.ctx = None

        # Persist updated history
        self._histories[session_id] = list(self._engine.history)

        # Parse captured stdout
        raw_text = ctx.buf.getvalue()
        cost_info, messages = _parse_stdout(raw_text)

        # Build items list: tables with auto-generated charts interleaved
        items: List[Dict[str, Any]] = []
        for tbl in ctx.tables:
            items.append(tbl)
            chart = _maybe_chart(tbl)
            if chart:
                items.append(chart)
        for msg in messages:
            items.append({"type": "message", "text": msg})

        return {"items": items, "cost_info": cost_info, "error": error}


def _parse_stdout(raw: str):
    """
    Split captured stdout into (cost_info_str, [message_str, ...]).
    Cost/token lines are separated from informational messages.
    """
    cost_lines    = []
    message_lines = []
    in_summary    = False

    for line in raw.splitlines():
        clean = _strip_ansi(line).strip()
        if not clean:
            continue
        if "── session summary ──" in clean.lower():
            in_summary = True
        if in_summary or clean.startswith("[tokens"):
            cost_lines.append(clean)
        else:
            message_lines.append(clean)

    return ("\n".join(cost_lines) or None), message_lines
