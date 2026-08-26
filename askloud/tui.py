"""
Textual TUI: tab-based viewer for multi-resource query results in the CLI.

Launched automatically when a query returns 2+ tables and stdout is a tty.
Press q or Escape to return to the prompt.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, TabbedContent, TabPane

_PROVIDER_COLORS = {
    "aws":   "#FF9900",
    "azure": "#0078D4",
    "gcp":   "#34A853",
}

_BASE_CSS = """
Screen {
    background: #0f1117;
}
TabbedContent {
    height: 1fr;
}
TabbedContent ContentSwitcher {
    height: 1fr;
}
TabPane {
    padding: 0;
    background: #0f1117;
}
Tabs {
    background: #1a1d27;
    border-bottom: tall #2a3040;
}
Tab {
    color: #8892a4;
}
Tab.-active {
    color: #e2e8f0;
    background: #0f1117;
}
DataTable {
    height: 1fr;
    background: #0f1117;
}
DataTable > .datatable--header {
    background: #1a1d27;
    color: #6c8ebf;
    text-style: bold;
}
DataTable > .datatable--cursor {
    background: #1e2535;
}
DataTable > .datatable--highlight {
    background: #171c28;
}
DataTable > .datatable--odd-row {
    background: #0d1015;
}
Footer {
    background: #1a1d27;
    color: #8892a4;
}
"""


class ResultsApp(App[None]):
    """Full-screen tabbed results viewer."""

    DARK = True
    CSS  = _BASE_CSS

    BINDINGS = [
        Binding("q",      "quit", "Quit"),
        Binding("escape", "quit", "Quit", show=False),
        Binding("/",      "focus_search", "Search", show=True),
    ]

    def __init__(self, tables: list[dict]) -> None:
        super().__init__()
        self._tables = tables  # [{tab, title, headers, rows, provider}]

    def compose(self) -> ComposeResult:
        with TabbedContent():
            for tbl in self._tables:
                n     = len(tbl["rows"])
                label = f"{tbl['tab']}({n})"
                with TabPane(label):
                    yield DataTable(zebra_stripes=True, cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        tables    = list(self._tables)
        data_tbls = list(self.query(DataTable))
        for tbl, dt in zip(tables, data_tbls):
            dt.add_columns(*tbl["headers"])
            for row in tbl["rows"]:
                dt.add_row(*row)

        # Apply provider accent to the active table's header via inline style
        self._tint_active_header()

    def on_tabbed_content_tab_activated(self, _event) -> None:
        self._tint_active_header()

    def _tint_active_header(self) -> None:
        try:
            tc  = self.query_one(TabbedContent)
            idx = list(tc.query(TabPane)).index(tc.active_pane)
            tbl = self._tables[idx]
            color = _PROVIDER_COLORS.get(tbl.get("provider", "aws"), "#6c8ebf")
            dt  = list(self.query(DataTable))[idx]
            dt.styles.color = color
        except Exception:
            pass

    def action_focus_search(self) -> None:
        # focus the active DataTable so / enters filter via Textual's built-in search
        try:
            tc  = self.query_one(TabbedContent)
            idx = list(tc.query(TabPane)).index(tc.active_pane)
            list(self.query(DataTable))[idx].focus()
        except Exception:
            pass


def show_tabbed_results(tables: list[dict]) -> None:
    """Launch the TUI and block until the user presses q / Escape."""
    ResultsApp(tables).run()
