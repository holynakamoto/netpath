from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from netpath import dns as dns_mod

_RECORD_TYPES = tuple(dns_mod.SUPPORTED_RECORD_TYPES)
_MAP_WIDTH = 72
_MAP_HEIGHT = 22
_WORLD_MAP = (
    "        ░░░░░░░░░░░░░░░                ░░░░░░░░░░░░░░░░░░░░       ",
    "     ░░░░░░░░░░░░░░░░░░░░            ░░░░░░░░░░░░░░░░░░░░░░░░     ",
    "   ░░░░░░░░░░░░░░░░░░░░░░░         ░░░░░░░░░░░░░░░░░░░░░░░░░░░    ",
    "  ░░░░░░░░░░░░░░░░░░░░░░░░░       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ░░ ",
    "   ░░░░░░░░░░░░░░░░░░░░░░░        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ",
    "     ░░░░░░░░░░░░░░░░░░            ░░░░░░░░░░░░░░░░░░░░░░░░░░░    ",
    "       ░░░░░░░░░░░░░                ░░░░░░░░░░░░░░░░░░░░░░░░     ",
    "         ░░░░░░░░░                   ░░░░░░░░░░░░░░░░░░░        ",
    "          ░░░░░░░                    ░░░░░░░░░░░░░░░            ",
    "           ░░░░░                      ░░░░░░░░░░░         ░░░░  ",
    "            ░░░░                      ░░░░░░░░░         ░░░░░░  ",
    "            ░░░░                       ░░░░░░░        ░░░░░░░░  ",
    "             ░░░                       ░░░░░░        ░░░░░░░░░  ",
    "              ░░                       ░░░░░        ░░░░░░░░░   ",
    "                                       ░░░░         ░░░░░░░░    ",
    "                                        ░░          ░░░░░░      ",
    "                                                    ░░░░        ",
    "                                                                ",
    "                                                                ",
    "                                                                ",
    "                                                                ",
    "                                                                ",
)


class DnsTui(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #top {
        height: 3;
        padding: 0 1;
    }

    #body {
        height: 1fr;
    }

    #table-pane {
        width: 60%;
        min-width: 86;
    }

    #map-pane {
        width: 40%;
        min-width: 46;
        border: round cyan;
        padding: 0 1;
    }

    #status {
        height: 1;
        color: cyan;
    }

    #domain {
        width: 1fr;
    }

    #record-types {
        height: 1;
    }

    #majority {
        height: auto;
        padding-top: 1;
    }

    DataTable {
        height: 1fr;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("tab", "next_record_type", "Type"),
    ]

    def __init__(
        self,
        domain: str,
        record_type: str = "A",
        timeout: int = 3,
        query_impl: Callable[[str, str, int], list[dict]] | None = None,
    ) -> None:
        super().__init__()
        self.domain = domain
        self.record_type = record_type.upper()
        self.timeout = timeout
        self.query_impl = query_impl or dns_mod.query_public_resolvers
        self.rows: list[dict] = []
        self.summary: dict = dns_mod.summarize_public_resolver_rows([])

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="top"):
            yield Input(value=self.domain, placeholder="Domain", id="domain")
            yield Static(self._record_type_line(), id="record-types")
            yield Static("ready", id="status")
        with Horizontal(id="body"):
            with Vertical(id="table-pane"):
                yield DataTable(id="resolver-table", cursor_type="row")
            with Vertical(id="map-pane"):
                yield Static(self._map_text(), id="resolver-map")
                yield Static("", id="majority")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#resolver-table", DataTable)
        table.add_columns("Resolver", "Loc", "IP", "Time", "TTL", "Status", "Answer")
        self.refresh_results()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.domain = event.value.strip()
        if self.domain:
            self.refresh_results()

    def action_refresh(self) -> None:
        domain = self.query_one("#domain", Input).value.strip()
        if domain:
            self.domain = domain
        self.refresh_results()

    def action_next_record_type(self) -> None:
        index = _RECORD_TYPES.index(self.record_type)
        self.record_type = _RECORD_TYPES[(index + 1) % len(_RECORD_TYPES)]
        self.query_one("#record-types", Static).update(self._record_type_line())
        self.refresh_results()

    @work(thread=True, exclusive=True)
    def refresh_results(self) -> None:
        self.call_from_thread(self._set_status, f"querying {self.domain} {self.record_type}…")
        rows = self.query_impl(self.domain, self.record_type, timeout=self.timeout)
        self.call_from_thread(self._apply_results, rows)

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _apply_results(self, rows: list[dict]) -> None:
        self.rows = rows
        self.summary = dns_mod.summarize_public_resolver_rows(rows)
        self._render_table()
        self.query_one("#resolver-map", Static).update(self._map_text())
        self.query_one("#majority", Static).update(self._majority_text())
        self._set_status(
            f"usable answers {self.summary['agree']}/{self.summary['usable']} agree "
            f"({self.summary['percentage']}%) · {self.summary['errors']} unreachable · "
            f"{self.summary['none'] + self.summary['servfail']} empty/failed · "
            f"{self.summary['groups']} record group(s) · refreshed {datetime.now().strftime('%H:%M:%S')}"
        )

    def _render_table(self) -> None:
        table = self.query_one("#resolver-table", DataTable)
        table.clear()
        majority_rows = self.summary.get("majority_rows") or []
        for i, row in enumerate(self.rows):
            agrees = i < len(majority_rows) and majority_rows[i]
            table.add_row(
                row["name"],
                row["location"],
                row["ip"],
                f"{row.get('elapsed_ms', 0)}ms",
                str(row.get("min_ttl") or "—"),
                self._status_label(row, agrees),
                self._answer_label(row),
            )

    def _record_type_line(self) -> Text:
        line = Text("Type: ")
        for rtype in _RECORD_TYPES:
            if rtype == self.record_type:
                line.append(f" {rtype} ", style="black on cyan bold")
            else:
                line.append(f" {rtype} ", style="dim")
            line.append(" ")
        return line

    def _status_label(self, row: dict, agrees: bool) -> Text:
        status = row.get("status")
        if status == "error":
            return Text("✗ ERR", style="bold red")
        if status == "servfail":
            return Text("! SERVFAIL", style="bold red")
        if status == "none":
            return Text("∅ NONE", style="yellow")
        if agrees:
            return Text("✓ OK", style="bold green")
        return Text("≠ DIFFERS", style="bold magenta")

    def _answer_label(self, row: dict) -> Text:
        if row.get("status") == "error":
            return Text(row.get("error") or "error", style="red")
        if row.get("status") == "servfail":
            return Text("SERVFAIL", style="red")
        values = row.get("values") or []
        if not values:
            return Text("—", style="dim")
        return Text(", ".join(values))

    def _map_text(self) -> Text:
        cells = [list(line[:_MAP_WIDTH].ljust(_MAP_WIDTH)) for line in _WORLD_MAP[:_MAP_HEIGHT]]
        styles: dict[tuple[int, int], str] = {}
        for y, line in enumerate(cells):
            for x, char in enumerate(line):
                if char != " ":
                    styles[(y, x)] = "dark_green"

        majority_rows = self.summary.get("majority_rows") or []
        for i, row in enumerate(self.rows):
            lon = row.get("lon")
            lat = row.get("lat")
            if lon is None or lat is None:
                continue
            x = round(((float(lon) + 180.0) / 360.0) * (_MAP_WIDTH - 1))
            y = round(((90.0 - float(lat)) / 180.0) * (_MAP_HEIGHT - 1))
            x = max(0, min(_MAP_WIDTH - 1, x))
            y = max(0, min(_MAP_HEIGHT - 1, y))
            cells[y][x] = "●"
            if row.get("status") == "error":
                styles[(y, x)] = "bold red"
            elif row.get("status") in {"none", "servfail"}:
                styles[(y, x)] = "bold yellow"
            elif i < len(majority_rows) and majority_rows[i]:
                styles[(y, x)] = "bold green"
            else:
                styles[(y, x)] = "bold magenta"

        rendered = Text("Resolver Map\n", style="bold cyan")
        for y, line in enumerate(cells):
            for x, char in enumerate(line):
                rendered.append(char, style=styles.get((y, x), "dim"))
            rendered.append("\n")
        rendered.append("● agrees  ", style="green")
        rendered.append("● differs  ", style="magenta")
        rendered.append("● none/servfail  ", style="yellow")
        rendered.append("● error", style="red")
        return rendered

    def _majority_text(self) -> Text:
        values = self.summary.get("majority_values") or []
        text = Text(f"Majority answer ({self.summary['agree']}/{self.summary['responding']}):\n", style="bold")
        if values:
            for value in values:
                text.append(f"  • {value}\n")
        else:
            text.append("  —\n", style="dim")
        return text


def run(domain: str, record_type: str = "A", timeout: int = 3) -> None:
    DnsTui(domain=domain, record_type=record_type, timeout=timeout).run()
