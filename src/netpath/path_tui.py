from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Select, Static

from netpath import globe, path_service

MeasureImpl = Callable[..., dict]
_MAP_WIDTH = 58
_MAP_HEIGHT = 16


class PathTui(App[None]):
    TITLE = "netpath"
    SUB_TITLE = "interactive path analyzer"
    CSS = """
    Screen { layout: vertical; background: #071017; }
    Header { background: #0b1d28; color: #d7f7ff; }
    #controls {
        height: 5;
        padding: 1 1 0 1;
        background: #0b1d28;
    }
    #mode { width: 18; margin-right: 1; }
    #source, #destination { width: 1fr; margin-right: 1; }
    #run, #globe { min-width: 12; margin-left: 1; }
    #status {
        height: 2;
        padding: 0 2;
        color: #7ddff2;
        background: #0b1d28;
    }
    #main { height: 1fr; }
    #left { width: 58%; min-width: 68; }
    #right { width: 42%; min-width: 42; }
    #summary {
        height: 5;
        padding: 1 2;
        border: round #248da3;
        background: #09151e;
    }
    #candidates { height: 1fr; }
    #route-map {
        height: 20;
        padding: 1 2;
        border: round #248da3;
        background: #09151e;
    }
    #hops { height: 1fr; }
    DataTable > .datatable--header { background: #123346; color: #8be9fd; text-style: bold; }
    DataTable:focus > .datatable--cursor { background: #164e63; }
    Button.-primary { background: #137c8f; }
    Footer { background: #0b1d28; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+r", "run_measurement", "Run"),
        ("g", "open_globe", "Globe"),
        ("m", "toggle_mode", "Mode"),
    ]

    def __init__(
        self,
        source: str = "",
        destination: str = "",
        mode: str = "city",
        token: str | None = None,
        city_impl: MeasureImpl = path_service.measure_citypath,
        asn_impl: MeasureImpl = path_service.measure_aspath,
    ) -> None:
        super().__init__()
        self.initial_source = source
        self.initial_destination = destination
        self.initial_mode = mode
        self.token = token
        self.city_impl = city_impl
        self.asn_impl = asn_impl
        self.result: dict | None = None
        self.selected_candidate = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="controls"):
            yield Select(
                [("City path", "city"), ("ASN path", "asn")],
                value=self.initial_mode,
                allow_blank=False,
                id="mode",
            )
            yield Input(value=self.initial_source, placeholder="Source city", id="source")
            yield Input(value=self.initial_destination, placeholder="Destination city", id="destination")
            yield Button("Run", id="run", variant="primary")
            yield Button("Globe", id="globe", disabled=True)
        yield Static("Enter two endpoints and run a measurement", id="status")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static(self._summary_text(), id="summary")
                yield DataTable(id="candidates", cursor_type="row", zebra_stripes=True)
            with Vertical(id="right"):
                yield Static(self._route_map([]), id="route-map")
                yield DataTable(id="hops", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        candidates = self.query_one("#candidates", DataTable)
        candidates.add_columns("#", "RTT", "Status", "Probe", "AS path")
        hops = self.query_one("#hops", DataTable)
        hops.add_columns("Hop", "RTT", "IP", "Network", "Location")
        self._update_placeholders(self.initial_mode)
        self.query_one("#source", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "mode":
            self._update_placeholders(str(event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self.action_run_measurement()
        elif event.button.id == "globe":
            self.action_open_globe()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.action_run_measurement()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "candidates" or event.cursor_row < 0:
            return
        self.selected_candidate = event.cursor_row
        self._render_selected_candidate()

    def action_toggle_mode(self) -> None:
        select = self.query_one("#mode", Select)
        select.value = "asn" if select.value == "city" else "city"

    def action_run_measurement(self) -> None:
        source = self.query_one("#source", Input).value.strip()
        destination = self.query_one("#destination", Input).value.strip()
        if not source or not destination:
            self._set_status("Source and destination are required", error=True)
            return
        self.run_measurement(str(self.query_one("#mode", Select).value), source, destination)

    def action_open_globe(self) -> None:
        if self.result:
            globe.render_aspath(self.result)
            self._set_status("Opened the best measured path in your browser")

    @work(thread=True, exclusive=True)
    def run_measurement(self, mode: str, source: str, destination: str) -> None:
        self.call_from_thread(self._set_running, True)
        impl = self.city_impl if mode == "city" else self.asn_impl
        try:
            result = impl(
                source,
                destination,
                token=self.token,
                status=lambda message: self.call_from_thread(self._set_status, message),
            )
        except Exception as exc:
            self.call_from_thread(self._measurement_failed, str(exc))
        else:
            self.call_from_thread(self._apply_result, result)
        finally:
            self.call_from_thread(self._set_running, False)

    def _set_running(self, running: bool) -> None:
        self.query_one("#run", Button).disabled = running
        self.query_one("#mode", Select).disabled = running
        if running:
            self.query_one("#globe", Button).disabled = True

    def _measurement_failed(self, message: str) -> None:
        self.result = None
        self.query_one("#candidates", DataTable).clear()
        self.query_one("#hops", DataTable).clear()
        self.query_one("#summary", Static).update(self._summary_text())
        self.query_one("#route-map", Static).update(self._route_map([]))
        self.query_one("#globe", Button).disabled = True
        self._set_status(message, error=True)

    def _apply_result(self, result: dict) -> None:
        self.result = result
        self.selected_candidate = 0
        table = self.query_one("#candidates", DataTable)
        table.clear()
        for index, candidate in enumerate(result.get("candidates") or [], 1):
            rtt = candidate.get("rtt_ms")
            table.add_row(
                str(index),
                f"{rtt:.1f} ms" if rtt is not None else "—",
                Text("complete", style="green") if candidate.get("reaches_target") else Text("partial", style="yellow"),
                candidate.get("probe") or "Globalping",
                " → ".join(candidate.get("path") or []),
            )
        self.query_one("#summary", Static).update(self._summary_text())
        self.query_one("#globe", Button).disabled = not bool(result.get("optimal_path"))
        self._render_selected_candidate()
        count = len(result.get("candidates") or [])
        self._set_status(f"Measurement complete: {count} path candidate(s) · {datetime.now():%H:%M:%S}")

    def _render_selected_candidate(self) -> None:
        candidates = (self.result or {}).get("candidates") or []
        if not candidates:
            return
        candidate = candidates[min(self.selected_candidate, len(candidates) - 1)]
        points = candidate.get("hop_points") or candidate.get("geo_points") or []
        table = self.query_one("#hops", DataTable)
        table.clear()
        for index, point in enumerate(points, 1):
            rtt = point.get("rtt_ms")
            location = ", ".join(
                value for value in (point.get("city"), point.get("country_code")) if value
            )
            table.add_row(
                str(point.get("hop", index)),
                f"{rtt:.1f} ms" if rtt is not None else "—",
                point.get("ip") or "—",
                point.get("label") or "—",
                location or "—",
            )
        self.query_one("#route-map", Static).update(self._route_map(points))

    def _summary_text(self) -> Text:
        if not self.result:
            return Text("No measurement yet\nResults will appear here.", style="dim")
        best = self.result.get("optimal_path") or {}
        ping = self.result.get("ping_rtt") or {}
        text = Text()
        text.append(f"{self.result.get('source_asn')}  →  {self.result.get('dest_asn')}\n", style="bold cyan")
        text.append(f"Target {self.result.get('target_ip', '—')}")
        if ping.get("avg") is not None:
            text.append(f"   Aggregate RTT {ping['avg']:.1f} ms")
        text.append("\nBest: ", style="dim")
        text.append(" → ".join(best.get("path") or ["No complete path"]), style="bold green")
        return text

    def _route_map(self, points: list[dict]) -> Text:
        canvas = [[" " for _ in range(_MAP_WIDTH)] for _ in range(_MAP_HEIGHT)]
        plotted: list[tuple[int, int, int]] = []
        for index, point in enumerate(points, 1):
            lat, lon = point.get("lat"), point.get("lon")
            if lat is None or lon is None:
                continue
            x = round((float(lon) + 180) / 360 * (_MAP_WIDTH - 1))
            y = round((90 - float(lat)) / 180 * (_MAP_HEIGHT - 1))
            plotted.append((x, y, index))
        for (x1, y1, _), (x2, y2, _) in zip(plotted, plotted[1:]):
            steps = max(abs(x2 - x1), abs(y2 - y1), 1)
            for step in range(steps + 1):
                x = round(x1 + (x2 - x1) * step / steps)
                y = round(y1 + (y2 - y1) * step / steps)
                canvas[y][x] = "·"
        for x, y, index in plotted:
            canvas[y][x] = str(index % 10)
        text = Text("Approximate hop route\n", style="bold cyan")
        if not plotted:
            text.append("\nNo geolocated hops to plot", style="dim")
            return text
        for row in canvas:
            text.append("".join(row), style="#39788a")
            text.append("\n")
        text.append("Numbers correspond to the hop table", style="dim")
        return text

    def _update_placeholders(self, mode: str) -> None:
        city_mode = mode == "city"
        self.query_one("#source", Input).placeholder = "Source city" if city_mode else "Source ASN"
        self.query_one("#destination", Input).placeholder = "Destination city" if city_mode else "Destination ASN"

    def _set_status(self, message: str, error: bool = False) -> None:
        style = "bold red" if error else "cyan"
        self.query_one("#status", Static).update(Text(message, style=style))


def run(
    source: str = "",
    destination: str = "",
    mode: str = "city",
    token: str | None = None,
) -> None:
    PathTui(source=source, destination=destination, mode=mode, token=token).run()
