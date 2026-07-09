from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, RichLog, Select, Static

from netpath import globe, local_capture, path_service

MeasureImpl = Callable[..., dict]
_MAP_WIDTH = 58
_MAP_HEIGHT = 16
_PATH_MODES = {"city", "aspath"}
_OPTIONAL_PRIMARY_MODES = {"coverage", "serve"}
_MODES = [
    ("City path", "city"),
    ("ASN path", "aspath"),
    ("Host trace", "host"),
    ("ASN test", "asn"),
    ("Country analysis", "country"),
    ("DNS propagation", "dns"),
    ("Create baseline", "monitor"),
    ("Explain incident", "explain"),
    ("Find ASN target", "target"),
    ("Probe coverage", "coverage"),
    ("Set up iperf3 server", "serve"),
    ("Capture local traffic", "capture"),
]
_MODE_FIELDS = {
    "city": ("Source city", "Destination city"),
    "aspath": ("Source ASN", "Destination ASN"),
    "host": ("Hostname or IP", "Optional: throughput (yes/no)"),
    "asn": ("Target ASN", "Optional: server count"),
    "country": ("Country code", "Optional: number of ASNs"),
    "dns": ("Domain", "Optional: record type (A, AAAA, MX...)"),
    "explain": ("Hostname or IP", ""),
    "monitor": ("Target ASN", "Optional: exact hostname or IP"),
    "target": ("Target ASN", "Optional: preferred target IP"),
    "coverage": ("Optional: countries to show", ""),
    "serve": ("Optional: advertised hostname/IP", "Optional: port (default 5201)"),
    "capture": ("Describe what to capture", ""),
}


class CaptureConfirmation(ModalScreen[bool]):
    CSS = """
    CaptureConfirmation {
        align: center middle;
        background: #000000;
    }
    #capture-confirm {
        width: 72;
        height: auto;
        padding: 1 2;
        border: round #248da3;
        background: #09151e;
    }
    #capture-plan { height: auto; margin-bottom: 1; }
    #capture-actions { height: 3; align-horizontal: right; }
    #capture-actions Button { margin-left: 1; }
    """

    def __init__(self, spec: local_capture.CaptureSpec) -> None:
        super().__init__()
        self.spec = spec

    def compose(self) -> ComposeResult:
        estimate = min(
            local_capture.MAX_CAPTURE_MIB,
            max(1, round(self.spec.duration_seconds * local_capture.SNAPLEN * 100 / 1_000_000)),
        )
        text = (
            "[bold cyan]Confirm local packet capture[/bold cyan]\n\n"
            f"Interface: {self.spec.interface}\n"
            f"Match: {self.spec.filter_description}\n"
            f"Planner: {self.spec.planner}\n"
            f"Filter: {self.spec.filter_bpf}\n"
            f"Duration: {self.spec.duration_seconds} seconds\n"
            f"Privacy: headers only ({local_capture.SNAPLEN}-byte snap length)\n"
            f"Maximum file size: {local_capture.MAX_CAPTURE_MIB} MiB "
            f"(rough estimate: ≤{estimate} MiB)\n"
            "Retention: delete immediately after analysis\n\n"
            "[yellow]Header capture is best-effort: unusual extension headers may expose "
            "a few payload bytes.[/yellow]"
        )
        with Container(id="capture-confirm"):
            yield Static(text, id="capture-plan", markup=True)
            with Horizontal(id="capture-actions"):
                yield Button("Cancel", id="capture-cancel")
                yield Button("Confirm capture", id="capture-accept", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "capture-accept")


def discover_baselines(directory: Path | None = None) -> list[tuple[str, str]]:
    """Return monitor baseline files as newest-first Select options."""
    root = directory or Path("~/.netpath/monitor").expanduser()
    files = list(root.glob("*.jsonl")) + list(root.glob("*.json"))
    options: list[tuple[str, str]] = []
    for path in sorted(files, key=lambda item: item.stat().st_mtime, reverse=True):
        latest: dict = {}
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        latest = json.loads(line)
        except (OSError, json.JSONDecodeError):
            continue
        target = (
            latest.get("target_input")
            or latest.get("target_host")
            or latest.get("monitor_key")
            or path.stem
        )
        asn = latest.get("asn")
        stamp = str(latest.get("timestamp") or "")[:16].replace("T", " ")
        details = " · ".join(value for value in (asn, stamp) if value)
        label = f"{target} ({details})" if details else str(target)
        options.append((label, str(path)))
    return options


def build_command(mode: str, primary: str, secondary: str = "") -> list[str]:
    """Build a safe one-shot netpath command for a non-path TUI operation."""
    command = [sys.executable, "-m", "netpath"]
    if mode == "host":
        command.extend(["host", primary])
        if secondary.lower() in {"yes", "y", "true", "1", "throughput"}:
            command.append("--throughput")
    elif mode == "asn":
        command.extend(["asn", primary])
        if secondary:
            command.extend(["--count", secondary])
    elif mode == "country":
        command.extend(["country", primary])
        if secondary:
            command.extend(["--top", secondary])
    elif mode == "dns":
        command.extend(["dns", primary, secondary or "A", "--once"])
    elif mode == "explain":
        command.extend(["explain", primary])
        if secondary:
            command.extend(["--baseline", secondary])
    elif mode == "monitor":
        command.extend(["monitor", primary, "--runs", "1"])
        if secondary:
            command.extend(["--target", secondary])
    elif mode == "target":
        command.extend(["target", primary])
        if secondary:
            command.extend(["--target", secondary])
    elif mode == "coverage":
        command.extend(["coverage", "--top", primary or "50"])
    elif mode == "serve":
        command.extend(["serve", "--setup-only"])
        if primary:
            command.extend(["--advertise-host", primary])
        if secondary:
            command.extend(["--port", secondary])
    else:
        raise ValueError(f"Unsupported console mode: {mode}")
    return command


class PathTui(App[None]):
    TITLE = "netpath"
    SUB_TITLE = "interactive network analysis console"
    CSS = """
    Screen { layout: vertical; background: #071017; }
    Header { background: #0b1d28; color: #d7f7ff; }
    #controls {
        height: 5;
        padding: 1 1 0 1;
        background: #0b1d28;
    }
    #mode { width: 22; margin-right: 1; }
    #planner { width: 18; margin-right: 1; }
    #source, #destination { width: 1fr; margin-right: 1; }
    #baseline { width: 1fr; margin-right: 1; }
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
    #console-view {
        height: 1fr;
        padding: 0 1;
    }
    #console {
        height: 1fr;
        border: round #248da3;
        background: #050c11;
        padding: 1 2;
    }
    .hidden { display: none; }
    DataTable > .datatable--header { background: #123346; color: #8be9fd; text-style: bold; }
    DataTable:focus > .datatable--cursor { background: #164e63; }
    Button.-primary { background: #137c8f; }
    Footer { background: #0b1d28; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+r", "run_measurement", "Run"),
        ("g", "open_globe", "Globe"),
        ("m", "next_mode", "Mode"),
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
                _MODES,
                value=self.initial_mode,
                allow_blank=False,
                id="mode",
            )
            yield Input(value=self.initial_source, placeholder="Source city", id="source")
            yield Input(value=self.initial_destination, placeholder="Destination city", id="destination")
            yield Select(
                [
                    ("Rules only", "off"),
                    ("Use Codex account", "codex"),
                    ("Use Claude account", "claude"),
                ],
                value="off",
                allow_blank=False,
                id="planner",
                classes="hidden",
            )
            yield Select(
                [],
                prompt="Optional baseline JSON/JSONL",
                allow_blank=True,
                id="baseline",
                classes="hidden",
            )
            yield Button("Run", id="run", variant="primary")
            yield Button("Globe", id="globe", disabled=True)
        yield Static("Enter two endpoints and run a measurement", id="status")
        with Horizontal(id="main"):
            with Horizontal(id="path-view"):
                with Vertical(id="left"):
                    yield Static(self._summary_text(), id="summary")
                    yield DataTable(id="candidates", cursor_type="row", zebra_stripes=True)
                with Vertical(id="right"):
                    yield Static(self._route_map([]), id="route-map")
                    yield DataTable(id="hops", cursor_type="row", zebra_stripes=True)
            with Vertical(id="console-view", classes="hidden"):
                yield RichLog(id="console", wrap=True, highlight=True, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        candidates = self.query_one("#candidates", DataTable)
        candidates.add_columns("#", "RTT", "Status", "Probe", "AS path")
        hops = self.query_one("#hops", DataTable)
        hops.add_columns("Hop", "RTT", "IP", "Network", "Location")
        self._update_placeholders(self.initial_mode)
        self._refresh_baselines()
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

    def action_next_mode(self) -> None:
        select = self.query_one("#mode", Select)
        values = [value for _, value in _MODES]
        index = values.index(str(select.value))
        select.value = values[(index + 1) % len(values)]

    def action_run_measurement(self) -> None:
        source = self.query_one("#source", Input).value.strip()
        mode = str(self.query_one("#mode", Select).value)
        if mode == "explain":
            selected = self.query_one("#baseline", Select).value
            destination = "" if selected is Select.BLANK else str(selected)
        else:
            destination = self.query_one("#destination", Input).value.strip()
        if mode not in _OPTIONAL_PRIMARY_MODES and not source:
            self._set_status("The primary input is required", error=True)
            return
        if mode in _PATH_MODES and not destination:
            self._set_status("Source and destination are required", error=True)
            return
        if mode in _PATH_MODES:
            self.run_measurement(mode, source, destination)
        elif mode == "capture":
            try:
                provider = str(self.query_one("#planner", Select).value)
                spec = local_capture.plan_capture(source, planner_provider=provider)
            except local_capture.CapturePlanError as exc:
                self._set_status(str(exc), error=True)
                return
            self.push_screen(
                CaptureConfirmation(spec),
                lambda confirmed: self._capture_confirmed(spec, confirmed),
            )
        else:
            self.run_console_command(mode, source, destination)

    def _capture_confirmed(self, spec: local_capture.CaptureSpec, confirmed: bool) -> None:
        if not confirmed:
            self._set_status("Capture cancelled; no packets were captured")
            return
        self.run_local_capture(spec)

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

    @work(thread=True, exclusive=True)
    def run_console_command(self, mode: str, primary: str, secondary: str) -> None:
        self.call_from_thread(self._set_running, True)
        log = self.query_one("#console", RichLog)
        self.call_from_thread(log.clear)
        try:
            command = build_command(mode, primary, secondary)
            self.call_from_thread(
                log.write,
                f"$ netpath {' '.join(command[3:])}\n",
            )
            env = {**os.environ, "NO_COLOR": "1", "PYTHONUNBUFFERED": "1"}
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.call_from_thread(log.write, line.rstrip())
            exit_code = process.wait()
            if exit_code:
                self.call_from_thread(
                    self._set_status,
                    f"{mode} finished with exit code {exit_code}",
                    True,
                )
            else:
                if mode == "monitor":
                    self.call_from_thread(self._refresh_baselines, True)
                self.call_from_thread(
                    self._set_status,
                    f"{mode} complete · {datetime.now():%H:%M:%S}",
                )
        except Exception as exc:
            self.call_from_thread(self._set_status, str(exc), True)
        finally:
            self.call_from_thread(self._set_running, False)

    @work(thread=True, exclusive=True)
    def run_local_capture(self, spec: local_capture.CaptureSpec) -> None:
        self.call_from_thread(self._set_running, True)
        log = self.query_one("#console", RichLog)
        self.call_from_thread(log.clear)
        self.call_from_thread(log.write, "Capture confirmed. Waiting for local traffic…")
        try:
            outcome = local_capture.execute_capture(spec)
            self.call_from_thread(log.write, local_capture.format_report(outcome.report))
            self.call_from_thread(
                self._set_status,
                f"Capture analyzed and deleted · {datetime.now():%H:%M:%S}",
            )
        except Exception as exc:
            self.call_from_thread(log.write, f"Capture failed: {exc}")
            self.call_from_thread(self._set_status, str(exc), True)
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
        primary, secondary = _MODE_FIELDS.get(mode, ("Primary input", "Optional input"))
        source = self.query_one("#source", Input)
        destination = self.query_one("#destination", Input)
        baseline = self.query_one("#baseline", Select)
        source.placeholder = primary
        destination.placeholder = secondary
        source.disabled = mode == "coverage"
        destination.disabled = not bool(secondary)
        destination.set_class(mode in {"explain", "capture"}, "hidden")
        self.query_one("#planner", Select).set_class(mode != "capture", "hidden")
        baseline.set_class(mode != "explain", "hidden")
        path_mode = mode in _PATH_MODES
        self.query_one("#path-view").set_class(not path_mode, "hidden")
        self.query_one("#console-view").set_class(path_mode, "hidden")
        self.query_one("#globe", Button).display = path_mode
        if path_mode:
            message = "Enter source and destination"
        elif mode == "monitor":
            message = "Create a reusable baseline JSON/JSONL for incident comparisons"
        elif mode == "explain" and not discover_baselines():
            message = "Enter a destination, or create a baseline first for comparison"
        elif mode == "capture":
            message = "Describe local traffic to capture; you will review the plan before it starts"
        else:
            message = f"Configure and run {mode}"
        self._set_status(message)

    def _refresh_baselines(self, select_newest: bool = False) -> None:
        select = self.query_one("#baseline", Select)
        options = discover_baselines()
        select.set_options(options)
        if select_newest and options:
            select.value = options[0][1]

    def _set_status(self, message: str, error: bool = False) -> None:
        style = "bold red" if error else "cyan"
        self.query_one("#status", Static).update(Text(message, style=style))


def run(
    source: str = "",
    destination: str = "",
    mode: str = "city",
    token: str | None = None,
) -> None:
    normalized_mode = "aspath" if mode == "asn" else mode
    PathTui(source=source, destination=destination, mode=normalized_mode, token=token).run()
