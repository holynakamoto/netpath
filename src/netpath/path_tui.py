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
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from netpath import globe, investigation, local_capture, path_service, processes

MeasureImpl = Callable[..., dict]
_ENV_CAPTURE_PLANNER = os.getenv("NETPATH_CAPTURE_PLANNER", "codex").lower()
_DEFAULT_CAPTURE_PLANNER = (
    _ENV_CAPTURE_PLANNER if _ENV_CAPTURE_PLANNER in {"codex", "claude"} else "off"
)
_PATH_MODES = {"city", "aspath"}
_STRUCTURED_MODES = {"host", "explain", "dns", *_PATH_MODES}
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
    "host": ("Hostname or IP", ""),
    "explain": ("Hostname or IP", ""),
    "dns": ("Domain", ""),
    "city": ("Source city", "Destination city"),
    "aspath": ("Source ASN", "Destination ASN"),
    "asn": ("Target ASN", "Server count (optional)"),
    "country": ("Country code", "Number of ASNs (optional)"),
    "monitor": ("Target ASN", "Exact hostname or IP (optional)"),
    "target": ("Target ASN", "Preferred target IP (optional)"),
    "coverage": ("Number of countries (default 50)", ""),
    "serve": ("Optional: advertised hostname/IP", "Optional: port (default 5201)"),
    "capture": ("Describe what to capture", ""),
}

_MODE_COPY = {
    "host": (
        "Diagnose a destination",
        "Find the likely fault domain and the next defensible action.",
        "Resolve  ›  edge  ›  path  ›  corroborate  ›  verdict",
        "Diagnose",
    ),
    "explain": (
        "Compare with a saved snapshot",
        "Measure the destination now and explain what changed.",
        "Load  ›  measure  ›  compare  ›  verdict",
        "Compare",
    ),
    "dns": (
        "Check DNS propagation",
        "Compare public resolver answers and isolate stale or divergent records.",
        "Query  ›  group answers  ›  identify differences",
        "Check DNS",
    ),
    "city": (
        "Compare sampled city paths",
        "Measure representative routes from probes near one city to a target near another.",
        "Geocode  ›  select target  ›  sample  ›  rank",
        "Measure",
    ),
    "aspath": (
        "Compare sampled ASN paths",
        "Measure representative routes from one network to a discovered target in another.",
        "Coverage  ›  select target  ›  sample  ›  rank",
        "Measure",
    ),
    "asn": (
        "Test a network",
        "Run path and performance checks against a reachable target in an ASN.",
        "Discover  ›  probe  ›  diagnose",
        "Run test",
    ),
    "country": (
        "Scan a country",
        "Compare representative networks and surface the strongest anomalies.",
        "Select  ›  probe  ›  rank findings",
        "Run scan",
    ),
    "monitor": (
        "Save a diagnostic snapshot",
        "Record one measurement for future incident comparison.",
        "Measure  ›  diagnose  ›  save",
        "Save snapshot",
    ),
    "capture": (
        "Capture local traffic",
        "Describe the traffic; review the privacy-bounded capture plan before it starts.",
        "Plan  ›  review  ›  capture packet prefixes  ›  delete raw",
        "Review plan",
    ),
    "target": (
        "Find an ASN target",
        "Discover a reachable endpoint suitable for measurement.",
        "Search  ›  verify target",
        "Find target",
    ),
    "coverage": (
        "Inspect remote probe coverage",
        "See where connected Globalping probes can provide independent evidence.",
        "Fetch  ›  rank coverage",
        "Load coverage",
    ),
    "serve": (
        "Set up an iperf3 target",
        "This tool can write a local server registration; review its output before continuing.",
        "Detect  ›  preview registration  ›  print guidance",
        "Review setup",
    ),
}

_MODE_LABELS = {
    "host": ("Target", ""),
    "explain": ("Target", ""),
    "dns": ("Domain", ""),
    "city": ("From", "To"),
    "aspath": ("From ASN", "To ASN"),
    "asn": ("Target ASN", "Server count"),
    "country": ("Country", "ASN count"),
    "monitor": ("Target ASN", "Exact target"),
    "target": ("Target ASN", "Preferred IP"),
    "coverage": ("Country count", ""),
    "serve": ("Advertised host", "Port"),
    "capture": ("Capture request", ""),
}

_NAV_GROUPS = (
    ("INVESTIGATE", (("Diagnose", "host"), ("Compare snapshot", "explain"), ("DNS propagation", "dns"))),
    ("EXPLORE", (("City paths", "city"), ("ASN paths", "aspath"), ("Test ASN", "asn"), ("Country scan", "country"))),
    ("TOOLS", (("Save snapshot", "monitor"), ("Capture traffic", "capture"), ("Find target", "target"), ("Probe coverage", "coverage"), ("iperf3 setup", "serve"))),
)


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
            f"Capture prefix: first {local_capture.SNAPLEN} bytes of each matching packet\n"
            f"Maximum file size: {local_capture.MAX_CAPTURE_MIB} MiB "
            f"(rough estimate: ≤{estimate} MiB)\n"
            "Retention: delete immediately after analysis\n\n"
            "[yellow]Payload warning: packet prefixes can include application data "
            "(often tens of bytes). The raw file is deleted after local analysis and "
            "payload content is not included in the report.[/yellow]"
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
        command.extend(["serve", "--setup-only", "--no-register-local"])
        if primary:
            command.extend(["--advertise-host", primary])
        if secondary:
            command.extend(["--port", secondary])
    else:
        raise ValueError(f"Unsupported console mode: {mode}")
    return command


def build_structured_command(
    mode: str,
    primary: str,
    secondary: str = "",
    baseline: str = "",
    dns_timeout: int = 3,
) -> list[str]:
    """Build a JSON-producing command for a natively rendered investigation."""
    command = [sys.executable, "-m", "netpath"]
    if mode in {"host", "explain"}:
        command.extend(["explain", primary, "--json"])
        if baseline:
            command.extend(["--baseline", baseline])
    elif mode == "dns":
        command.extend(["dns", primary, secondary or "A", "--json"])
        if dns_timeout != 3:
            command.extend(["--timeout", str(dns_timeout)])
    elif mode == "city":
        command.extend(["citypath", primary, secondary, "--json"])
    elif mode == "aspath":
        command.extend(["aspath", primary, secondary, "--json"])
    else:
        raise ValueError(f"Unsupported structured mode: {mode}")
    return command


def parse_json_output(output: str) -> dict:
    """Parse command JSON while tolerating a short diagnostic prefix."""
    stripped = output.strip()
    if not stripped:
        raise ValueError("The diagnostic command returned no output")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(stripped[-400:]) from exc
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as nested:
            raise ValueError(stripped[-400:]) from nested
    if not isinstance(payload, dict):
        raise ValueError("The diagnostic command returned an unexpected JSON shape")
    return payload


class PathTui(App[None]):
    """Diagnosis-first incident workbench backed by netpath's existing probes."""

    TITLE = "netpath"
    SUB_TITLE = "network incident investigator"
    CSS = """
    Screen { layout: vertical; background: #061017; color: #d7e7ea; }
    Header { background: #091821; color: #e6f8fb; }
    Footer { background: #091821; }

    #workspace { height: 1fr; }
    #rail {
        width: 24;
        height: 1fr;
        padding: 1 1;
        background: #08141c;
        border-right: solid #17313e;
        overflow-y: auto;
    }
    #brand { height: 2; color: #7ddff2; text-style: bold; }
    .nav-section {
        height: 1;
        margin-top: 1;
        padding-left: 1;
        color: #6d8992;
        text-style: bold;
    }
    Button.nav {
        width: 100%;
        min-width: 0;
        height: 1;
        padding: 0 1;
        border: none;
        background: transparent;
        color: #a9bdc2;
        content-align: left middle;
    }
    Button.nav:hover { background: #0d2530; color: #eefbfc; }
    Button.nav.active { background: #103242; color: #89e7f5; text-style: bold; }

    #content { width: 1fr; height: 1fr; padding: 1 2 0 2; }
    #mode { display: none; height: 3; margin-bottom: 1; }
    #form { height: 8; border-bottom: solid #17313e; }
    #form-title { height: 1; color: #f0fbfc; text-style: bold; }
    #form-help { height: 1; color: #78949c; }
    #controls { height: 3; margin-top: 1; }
    #source, #destination, #baseline, #record-type, #planner {
        width: 1fr;
        margin-right: 1;
    }
    #baseline, #record-type, #planner { height: 3; }
    #run, #stop, #globe { min-width: 11; margin-left: 1; }
    #plan { height: 1; color: #71909a; }
    #status { height: 1; padding-left: 1; color: #6fd6e7; }

    #verdict {
        height: 6;
        padding: 1 2;
        margin-bottom: 1;
        background: #0a171f;
        border-left: solid #31505b;
    }
    #verdict.severity-ok { border-left: solid #36c98f; }
    #verdict.severity-warning { border-left: solid #f0b44d; }
    #verdict.severity-critical { border-left: solid #f06b72; }
    #verdict.severity-error { border-left: solid #f06b72; }
    #verdict.severity-running { border-left: solid #55c8e0; }

    #tabs { height: 1fr; }
    TabPane { padding: 0; }
    #findings-scroll, #metrics-scroll { height: 1fr; }
    #findings, #metrics { width: 100%; padding: 1 2; }
    #candidates { height: 1fr; }
    #hops { height: 2fr; }
    #console { height: 1fr; padding: 1 2; background: #040b10; }

    .hidden { display: none; }
    DataTable > .datatable--header {
        background: #102b37;
        color: #8be9f8;
        text-style: bold;
    }
    DataTable:focus > .datatable--cursor { background: #174556; }
    Button.-primary { background: #137c8f; }
    """
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+r", "run_measurement", "Run"),
        ("f6", "export_bundle", "Export"),
        ("escape", "edit", "Edit"),
    ]

    def __init__(
        self,
        source: str = "",
        destination: str = "",
        mode: str = "host",
        token: str | None = None,
        dns_timeout: int = 3,
        city_impl: MeasureImpl = path_service.measure_citypath,
        asn_impl: MeasureImpl = path_service.measure_aspath,
    ) -> None:
        super().__init__()
        valid_modes = {value for _, value in _MODES}
        self.initial_mode = mode if mode in valid_modes else "host"
        self.initial_source = source
        self.initial_destination = destination
        self.active_mode = self.initial_mode
        self.form_values = {self.initial_mode: (source, destination)}
        self.token = token or os.getenv("NETPATH_GLOBALPING_TOKEN")
        self.dns_timeout = dns_timeout
        self.city_impl = city_impl
        self.asn_impl = asn_impl
        self.custom_path_impls = (
            city_impl is not path_service.measure_citypath
            or asn_impl is not path_service.measure_aspath
        )
        self.result: dict | None = None
        self.investigation_result: investigation.InvestigationResult | None = None
        self.selected_candidate = 0
        self.running = False
        self.cancel_requested = False
        self.run_generation = 0
        self.narrow_layout = False
        self.showing_outcome = False
        self.outcome_available = False
        self.process: subprocess.Popen[str] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="rail"):
                yield Static("NETPATH\nINCIDENT WORKBENCH", id="brand")
                for heading, items in _NAV_GROUPS:
                    yield Static(heading, classes="nav-section")
                    for label, mode in items:
                        yield Button(label, id=f"nav-{mode}", classes="nav")
            with Vertical(id="content"):
                yield Select(
                    _MODES,
                    value=self.initial_mode,
                    allow_blank=False,
                    id="mode",
                )
                with Vertical(id="form"):
                    yield Static("", id="form-title")
                    yield Static("", id="form-help")
                    with Horizontal(id="controls"):
                        yield Input(
                            value=self.initial_source,
                            placeholder="Hostname or IP",
                            id="source",
                        )
                        yield Input(
                            value=self.initial_destination,
                            placeholder="",
                            id="destination",
                            classes="hidden",
                        )
                        yield Select(
                            [
                                ("A", "A"),
                                ("AAAA", "AAAA"),
                                ("CNAME", "CNAME"),
                                ("MX", "MX"),
                                ("NS", "NS"),
                                ("TXT", "TXT"),
                                ("SOA", "SOA"),
                            ],
                            value=(
                                self.initial_destination.upper()
                                if self.initial_mode == "dns"
                                and self.initial_destination.upper()
                                in {"A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"}
                                else "A"
                            ),
                            allow_blank=False,
                            id="record-type",
                            classes="hidden",
                        )
                        yield Select(
                            [],
                            prompt="Saved snapshot (optional)",
                            allow_blank=True,
                            id="baseline",
                            classes="hidden",
                        )
                        yield Select(
                            [
                                ("Rules", "off"),
                                ("Codex", "codex"),
                                ("Claude", "claude"),
                            ],
                            value=_DEFAULT_CAPTURE_PLANNER,
                            allow_blank=False,
                            id="planner",
                            classes="hidden",
                        )
                        yield Button("Diagnose", id="run", variant="primary")
                        yield Button("Stop", id="stop", variant="error", classes="hidden")
                        yield Button("Globe", id="globe", disabled=True, classes="hidden")
                    yield Static("", id="plan")
                yield Static("Ready", id="status")
                yield Static(self._verdict_text(), id="verdict")
                with TabbedContent(initial="findings-tab", id="tabs"):
                    with TabPane("Findings", id="findings-tab"):
                        with VerticalScroll(id="findings-scroll"):
                            yield Static(self._empty_findings_text(), id="findings")
                    with TabPane("Path", id="path-tab"):
                        yield DataTable(
                            id="candidates",
                            cursor_type="row",
                            zebra_stripes=True,
                            classes="hidden",
                        )
                        yield DataTable(id="hops", cursor_type="row", zebra_stripes=True)
                    with TabPane("Measurements", id="metrics-tab"):
                        with VerticalScroll(id="metrics-scroll"):
                            yield Static("No measurements yet.", id="metrics")
                    with TabPane("Raw", id="raw-tab"):
                        yield RichLog(
                            id="console",
                            wrap=True,
                            highlight=True,
                            markup=False,
                        )
        yield Footer()

    def on_mount(self) -> None:
        candidates = self.query_one("#candidates", DataTable)
        candidates.add_columns("#", "RTT", "State", "Vantage", "AS path")
        hops = self.query_one("#hops", DataTable)
        hops.add_columns("Hop", "Latency", "Loss", "Endpoint", "Network", "Context")
        self._refresh_baselines()
        self._update_placeholders(self.initial_mode)
        self.query_one("#mode", Select).border_title = "Workspace"
        self._apply_responsive_layout(self.size.width)
        self.query_one("#source", Input).focus()

    def on_resize(self, event) -> None:
        self._apply_responsive_layout(event.size.width)

    def _apply_responsive_layout(self, width: int) -> None:
        self.narrow_layout = width < 100
        self.query_one("#rail").display = not self.narrow_layout
        self._update_result_density()

    def _update_result_density(self) -> None:
        compact_result = self.narrow_layout and self.showing_outcome
        self.query_one("#mode", Select).display = self.narrow_layout and not compact_result
        self.query_one("#form").display = not compact_result
        self.query_one("#status", Static).display = not compact_result
        candidates = (self.result or {}).get("candidates") or []
        self.query_one("#candidates", DataTable).set_class(
            not bool(candidates) or self.narrow_layout,
            "hidden",
        )
        self.query_one("#hops", DataTable).styles.height = (
            "1fr" if self.narrow_layout else "2fr"
        )

    def on_unmount(self) -> None:
        self.cancel_requested = True
        self.run_generation += 1
        process = self.process
        if process is not None:
            processes.terminate_process_tree(process)
        self.process = None
        self.workers.cancel_all()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "mode" and event.value is not Select.NULL:
            mode = str(event.value)
            if mode != self.active_mode:
                self._switch_mode(mode)
            return
        if self.outcome_available and not self.running:
            self._invalidate_outcome_for_edit()

    def on_input_changed(self, _event: Input.Changed) -> None:
        if self.outcome_available and not self.running:
            self._invalidate_outcome_for_edit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("nav-"):
            self._switch_mode(button_id.removeprefix("nav-"))
        elif button_id == "run":
            self.action_run_measurement()
        elif button_id == "stop":
            self.action_stop()
        elif button_id == "globe":
            self.action_open_globe()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        destination = self.query_one("#destination", Input)
        if (
            event.input.id == "source"
            and destination.display
            and not destination.disabled
            and not destination.value.strip()
        ):
            destination.focus()
            return
        self.action_run_measurement()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "candidates" or event.cursor_row < 0:
            return
        self.selected_candidate = event.cursor_row
        self._render_selected_candidate()

    def action_next_mode(self) -> None:
        values = [value for _, value in _MODES]
        index = values.index(self.active_mode)
        self._switch_mode(values[(index + 1) % len(values)])

    def action_edit(self) -> None:
        if not self.showing_outcome:
            return
        self.showing_outcome = False
        self._update_result_density()
        self._set_status("Edit the inputs, then run the investigation again")
        self.query_one("#source", Input).focus()

    def action_run_measurement(self) -> None:
        if self.running:
            self._set_status("An investigation is already running")
            return

        mode = self.active_mode
        source = self.query_one("#source", Input).value.strip()
        destination = self.query_one("#destination", Input).value.strip()
        baseline_value = self.query_one("#baseline", Select).value
        baseline = "" if baseline_value is Select.NULL else str(baseline_value)
        if mode == "dns":
            destination = str(self.query_one("#record-type", Select).value)

        if mode not in _OPTIONAL_PRIMARY_MODES and not source:
            self._set_status("Enter the target or scope before running", error=True)
            return
        if mode in _PATH_MODES and not destination:
            self._set_status("Enter both ends of the sampled path", error=True)
            return
        if mode == "explain" and not baseline:
            self._set_status(
                "Choose a saved snapshot, or use Diagnose for a new investigation",
                error=True,
            )
            return

        run_id = self._prepare_run()
        self._set_running(True)
        if mode in _PATH_MODES and self.custom_path_impls:
            self.run_measurement(mode, source, destination, run_id)
        elif mode in {"host", "explain", "dns", "city", "aspath"}:
            self.run_structured_command(mode, source, destination, baseline, run_id)
        elif mode == "capture":
            provider = str(self.query_one("#planner", Select).value)
            self.plan_local_capture(source, provider, run_id)
        else:
            self.run_console_command(mode, source, destination, run_id)

    def action_stop(self) -> None:
        if not self.running:
            return
        self.cancel_requested = True
        self.run_generation += 1
        process = self.process
        if process is not None:
            processes.terminate_process_tree(process)
        if self.process is process:
            self.process = None
        self.workers.cancel_all()
        self._set_running(False)
        self.showing_outcome = False
        self.outcome_available = False
        self._set_verdict(
            "Investigation stopped",
            "idle",
            "none",
            "n/a",
            "Edit the inputs or run the investigation again.",
        )
        findings = Text("CANCELLED\n", style="bold #a9c0c7")
        findings.append(
            "No conclusion was produced. Any late result will be ignored; partial command "
            "output remains available in Raw."
        )
        self.query_one("#findings", Static).update(findings)
        self._set_status("Stopped; late results will be ignored")
        self._update_result_density()

    def _capture_confirmed(self, spec: local_capture.CaptureSpec, confirmed: bool) -> None:
        if not confirmed:
            self._set_status("Capture cancelled; no packets were captured")
            return
        if not local_capture.capture_permission_cached():
            try:
                with self.suspend():
                    print("netpath needs administrator permission to capture local packets.")
                    permission = subprocess.run(["sudo", "-v"])
            except (OSError, SuspendNotSupported) as exc:
                self._set_status(
                    f"Could not open the permission prompt: {exc}. Run sudo -v and retry.",
                    error=True,
                )
                return
            if permission.returncode:
                self._set_status(
                    "Capture cancelled; administrator permission was not granted"
                )
                return
        if self.is_running:
            self.run_generation += 1
            self.cancel_requested = False
            capture_run_id = self.run_generation
            self._set_running(True)
            self.run_local_capture(spec, capture_run_id)
        else:
            self.run_local_capture(spec)

    def action_open_globe(self) -> None:
        candidate = self._selected_path_candidate()
        points = candidate.get("hop_points") or candidate.get("geo_points") or []
        geolocated = [
            point
            for point in points
            if point.get("lat") is not None and point.get("lon") is not None
        ]
        if len(geolocated) < 2:
            self._set_status("At least two geolocated hops are needed for the globe")
            return
        globe.render_aspath({**(self.result or {}), "optimal_path": candidate})
        self._set_status("Opened the selected sampled path in your browser")

    def action_export_bundle(self) -> None:
        if self.investigation_result is None:
            self._set_status("Run a structured investigation before exporting")
            return
        try:
            markdown_path, _ = investigation.save_bundle(
                self.investigation_result,
                Path("~/.netpath/reports").expanduser(),
            )
        except OSError as exc:
            self._set_status(f"Could not export the incident bundle: {exc}", error=True)
            return
        self._set_status(f"Redacted Markdown + JSON bundle saved to {markdown_path.parent}")

    @work(thread=True, exclusive=True)
    def run_measurement(
        self,
        mode: str,
        source: str,
        destination: str,
        run_id: int,
    ) -> None:
        impl = self.city_impl if mode == "city" else self.asn_impl
        try:
            result = impl(
                source,
                destination,
                token=self.token,
                status=lambda message: self._call_if_current(
                    self._set_status_if_current,
                    run_id,
                    message,
                ),
            )
        except Exception as exc:
            self._call_if_current(
                self._measurement_failed_if_current,
                run_id,
                str(exc),
            )
        else:
            self._call_if_current(self._apply_result_if_current, run_id, result)
        finally:
            self._call_if_current(self._finish_run, run_id)

    @work(thread=True, exclusive=True)
    def run_structured_command(
        self,
        mode: str,
        primary: str,
        secondary: str,
        baseline: str,
        run_id: int,
    ) -> None:
        log = self.query_one("#console", RichLog)
        process: subprocess.Popen[str] | None = None
        try:
            command = build_structured_command(
                mode,
                primary,
                secondary,
                baseline,
                dns_timeout=self.dns_timeout,
            )
            self._call_if_current(
                self._write_log_if_current,
                run_id,
                log,
                f"$ netpath {' '.join(command[3:])}",
            )
            env = {**os.environ, "NO_COLOR": "1", "PYTHONUNBUFFERED": "1"}
            if self.token:
                env["NETPATH_GLOBALPING_TOKEN"] = self.token
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                start_new_session=os.name == "posix",
            )
            self._track_process(run_id, process)
            output, _ = process.communicate()
            if not self._run_is_current(run_id):
                return
            payload = parse_json_output(output)
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            if mode in _PATH_MODES:
                self._call_if_current(self._apply_result_if_current, run_id, payload)
                return
            view = investigation.from_payload(mode, primary, payload)
            self._call_if_current(self._structured_finished_if_current, run_id, view)
        except Exception as exc:
            self._call_if_current(
                self._measurement_failed_if_current,
                run_id,
                str(exc),
            )
        finally:
            self._call_if_current(self._finish_run, run_id, process)

    @work(thread=True, exclusive=True)
    def run_console_command(
        self,
        mode: str,
        primary: str,
        secondary: str,
        run_id: int,
    ) -> None:
        log = self.query_one("#console", RichLog)
        process: subprocess.Popen[str] | None = None
        try:
            command = build_command(mode, primary, secondary)
            self._call_if_current(
                self._write_log_if_current,
                run_id,
                log,
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
                start_new_session=os.name == "posix",
            )
            self._track_process(run_id, process)
            assert process.stdout is not None
            for line in process.stdout:
                if not self._run_is_current(run_id):
                    break
                self._call_if_current(
                    self._write_log_if_current,
                    run_id,
                    log,
                    line.rstrip(),
                )
            exit_code = process.wait()
            if not self._run_is_current(run_id):
                return
            if mode == "monitor" and exit_code == 0:
                self._call_if_current(
                    self._refresh_baselines_if_current,
                    run_id,
                    True,
                )
            self._call_if_current(
                self._utility_finished_if_current,
                run_id,
                mode,
                exit_code,
            )
        except Exception as exc:
            self._call_if_current(
                self._measurement_failed_if_current,
                run_id,
                str(exc),
            )
        finally:
            self._call_if_current(self._finish_run, run_id, process)

    @work(thread=True, exclusive=True)
    def plan_local_capture(self, prompt: str, provider: str, run_id: int) -> None:
        try:
            spec = local_capture.plan_capture(
                prompt,
                planner_provider=provider,
                on_process=lambda process: self._track_process(run_id, process),
            )
        except local_capture.CapturePlanError as exc:
            self._call_if_current(
                self._measurement_failed_if_current,
                run_id,
                str(exc),
            )
        else:
            self._call_if_current(self._capture_plan_ready, run_id, spec)
        finally:
            self._call_if_current(self._finish_run, run_id)

    @work(thread=True, exclusive=True)
    def run_local_capture(
        self,
        spec: local_capture.CaptureSpec,
        run_id: int | None = None,
    ) -> None:
        run_id = self.run_generation if run_id is None else run_id
        if not self._run_is_current(run_id):
            return
        log = self.query_one("#console", RichLog)
        self._call_if_current(self._clear_log_if_current, run_id, log)
        self._call_if_current(
            self._write_log_if_current,
            run_id,
            log,
            "Capture confirmed. Waiting for local traffic…",
        )
        try:
            outcome = local_capture.execute_capture(
                spec,
                on_process=lambda process: self._track_process(run_id, process),
            )
            report = local_capture.format_report(outcome.report)
            self._call_if_current(self._write_log_if_current, run_id, log, report)
            self._call_if_current(self._capture_finished_if_current, run_id, report)
        except Exception as exc:
            self._call_if_current(
                self._write_log_if_current,
                run_id,
                log,
                f"Capture failed: {exc}",
            )
            self._call_if_current(
                self._measurement_failed_if_current,
                run_id,
                str(exc),
            )
        finally:
            self._call_if_current(self._finish_run, run_id)

    def _show_capture_confirmation(self, spec: local_capture.CaptureSpec) -> None:
        self.push_screen(
            CaptureConfirmation(spec),
            lambda confirmed: self._capture_confirmed(spec, confirmed),
        )

    def _capture_finished(self, report: str) -> None:
        self.showing_outcome = True
        self.outcome_available = True
        request = self.query_one("#source", Input).value.strip()
        self._set_verdict(
            "Capture analyzed and raw packet data deleted",
            "ok",
            "Local machine",
            "high",
            context=f"Request  {request}" if request else "",
        )
        findings = Text(report)
        findings.append(
            "\n\nNEXT ACTION\nUse these flow summaries as supporting evidence; "
            "packet payloads were not retained.",
            style="bold #8be9f8",
        )
        self.query_one("#findings", Static).update(findings)
        self.query_one("#tabs", TabbedContent).active = "findings-tab"
        self._set_status(f"Capture analyzed and deleted · {datetime.now():%H:%M:%S}")
        self._update_result_density()

    def _utility_finished(self, mode: str, exit_code: int) -> None:
        self.showing_outcome = True
        self.outcome_available = True
        scope = self.query_one("#source", Input).value.strip()
        context = f"Scope  {scope}" if scope else ""
        if exit_code:
            self._set_verdict(
                "Tool needs attention",
                "error",
                mode,
                "unknown",
                context=context,
            )
            self._set_status(
                f"{mode} finished with exit code {exit_code}; review Raw",
                error=True,
            )
        else:
            self._set_verdict("Tool completed", "ok", mode, "n/a", context=context)
            self._set_status(f"{mode} complete · {datetime.now():%H:%M:%S}")
        self.query_one("#findings", Static).update(
            "This utility still uses the expert CLI adapter. Review the Raw tab for output."
        )
        self.query_one("#tabs", TabbedContent).active = "raw-tab"
        self._update_result_density()

    def _call_if_current(
        self,
        callback: Callable[..., object],
        run_id: int,
        *args: object,
    ) -> object | None:
        if not self._run_is_current(run_id) or not self.is_running:
            return None
        try:
            return self.call_from_thread(callback, run_id, *args)
        except RuntimeError:
            return None

    def _run_is_current(self, run_id: int) -> bool:
        return run_id == self.run_generation and not self.cancel_requested

    def _track_process(
        self,
        run_id: int,
        process: subprocess.Popen[str] | None,
    ) -> bool:
        if not self._run_is_current(run_id):
            if process is not None:
                processes.terminate_process_tree(process)
            return False
        self.process = process
        return True

    def _finish_run(
        self,
        run_id: int,
        process: subprocess.Popen[str] | None = None,
    ) -> None:
        if process is not None:
            processes.terminate_process_tree(process)
        if process is not None and self.process is process:
            self.process = None
        if self._run_is_current(run_id):
            self._set_running(False)

    def _set_status_if_current(self, run_id: int, message: str) -> None:
        if self._run_is_current(run_id):
            self._set_status(message)

    def _measurement_failed_if_current(self, run_id: int, message: str) -> None:
        if self._run_is_current(run_id):
            self._measurement_failed(message)

    def _apply_result_if_current(self, run_id: int, result: dict) -> None:
        if self._run_is_current(run_id):
            self._apply_result(result)

    def _structured_finished_if_current(
        self,
        run_id: int,
        view: investigation.InvestigationResult,
    ) -> None:
        if not self._run_is_current(run_id):
            return
        self._apply_investigation(view)
        self._set_status(
            f"{view.verdict} · {view.confidence} confidence · "
            f"{datetime.now():%H:%M:%S}"
        )

    def _utility_finished_if_current(
        self,
        run_id: int,
        mode: str,
        exit_code: int,
    ) -> None:
        if self._run_is_current(run_id):
            self._utility_finished(mode, exit_code)

    def _refresh_baselines_if_current(
        self,
        run_id: int,
        select_newest: bool,
    ) -> None:
        if self._run_is_current(run_id):
            self._refresh_baselines(select_newest)

    def _capture_plan_ready(
        self,
        run_id: int,
        spec: local_capture.CaptureSpec,
    ) -> None:
        if not self._run_is_current(run_id):
            return
        self._finish_run(run_id)
        self._show_capture_confirmation(spec)

    def _capture_finished_if_current(self, run_id: int, report: str) -> None:
        if self._run_is_current(run_id):
            self._capture_finished(report)

    def _clear_log_if_current(self, run_id: int, log: RichLog) -> None:
        if self._run_is_current(run_id):
            log.clear()

    def _write_log_if_current(self, run_id: int, log: RichLog, message: str) -> None:
        if self._run_is_current(run_id):
            log.write(message)

    def _set_running(self, running: bool) -> None:
        self.running = running
        self.query_one("#run", Button).set_class(running, "hidden")
        self.query_one("#stop", Button).set_class(not running, "hidden")
        for selector in ("#source", "#destination"):
            self.query_one(selector, Input).disabled = running
        for selector in ("#baseline", "#record-type", "#planner", "#mode"):
            self.query_one(selector, Select).disabled = running
        for _, items in _NAV_GROUPS:
            for _, mode in items:
                self.query_one(f"#nav-{mode}", Button).disabled = running
        globe_button = self.query_one("#globe", Button)
        if running:
            globe_button.disabled = True
        elif self.result:
            globe_button.disabled = not self._has_globe_path()

    def _prepare_run(self) -> int:
        self.run_generation += 1
        self.cancel_requested = False
        run_id = self.run_generation
        self.showing_outcome = False
        self.outcome_available = False
        self.result = None
        self.investigation_result = None
        self.query_one("#candidates", DataTable).clear()
        self.query_one("#hops", DataTable).clear()
        self.query_one("#console", RichLog).clear()
        self.query_one("#candidates", DataTable).add_class("hidden")
        self.query_one("#globe", Button).disabled = True
        self.query_one("#findings", Static).update(
            "Running the bounded diagnostic plan. Partial failures will be kept as evidence."
        )
        self.query_one("#metrics", Static).update("Measurements will appear here.")
        title = _MODE_COPY[self.active_mode][0]
        self._set_verdict(title, "running", "collecting evidence", "pending")
        self._set_status("Collecting evidence…")
        self._update_result_density()
        return run_id

    def _measurement_failed(self, message: str) -> None:
        self.showing_outcome = True
        self.outcome_available = True
        self.result = None
        self.investigation_result = None
        self.query_one("#candidates", DataTable).clear()
        self.query_one("#hops", DataTable).clear()
        self.query_one("#globe", Button).disabled = True
        target = self.query_one("#source", Input).value.strip()
        self._set_verdict(
            "Investigation could not complete",
            "error",
            "unknown",
            "low",
            context=f"Target  {target}" if target else "",
        )
        detail = Text("WHAT HAPPENED\n", style="bold red")
        detail.append(message)
        detail.append(
            "\n\nNEXT ACTION\nCheck the target, local dependencies, and network access, then retry.",
            style="#b8cbd0",
        )
        self.query_one("#findings", Static).update(detail)
        self.query_one("#tabs", TabbedContent).active = "findings-tab"
        self._set_status(message, error=True)
        self._update_result_density()

    def _apply_result(self, result: dict) -> None:
        self.result = result
        self.selected_candidate = 0
        candidates = result.get("candidates") or []
        table = self.query_one("#candidates", DataTable)
        table.clear()
        table.set_class(not bool(candidates), "hidden")
        for index, candidate in enumerate(candidates, 1):
            rtt = candidate.get("rtt_ms")
            table.add_row(
                str(index),
                f"{rtt:.1f} ms" if rtt is not None else "—",
                Text("target ASN", style="green")
                if candidate.get("reaches_target")
                else Text("partial", style="yellow"),
                candidate.get("probe") or "Globalping",
                " → ".join(candidate.get("path") or []),
            )
        target = f"{result.get('source_asn', '—')} → {result.get('dest_asn', '—')}"
        view = investigation.from_payload(self.active_mode, target, result)
        self._apply_investigation(view)
        self._render_selected_candidate()
        self.query_one("#globe", Button).disabled = not self._has_globe_path()
        self._set_status(
            f"Measured {len(candidates)} sampled path candidate(s) · "
            f"{datetime.now():%H:%M:%S}"
        )

    def _apply_investigation(self, view: investigation.InvestigationResult) -> None:
        self.showing_outcome = True
        self.outcome_available = True
        self.investigation_result = view
        self._set_verdict(
            view.verdict,
            view.severity,
            view.culprit,
            view.confidence,
            view.recommendation,
            self._sample_context(view),
        )
        self.query_one("#findings", Static).update(self._findings_text(view))
        self.query_one("#metrics", Static).update(self._metrics_text(view))
        if self.active_mode not in _PATH_MODES:
            self._render_path_rows(list(view.path))
        log = self.query_one("#console", RichLog)
        log.clear()
        log.write(json.dumps(view.raw, indent=2, sort_keys=True, default=str))
        self.query_one("#tabs", TabbedContent).active = "findings-tab"
        self._update_result_density()

    def _render_selected_candidate(self) -> None:
        candidates = (self.result or {}).get("candidates") or []
        if not candidates:
            return
        candidate = candidates[min(self.selected_candidate, len(candidates) - 1)]
        points = candidate.get("hop_points") or candidate.get("geo_points") or []
        self._render_path_rows(points)
        selected_payload = {**(self.result or {}), "optimal_path": candidate}
        vantage = candidate.get("probe") or "The selected probe"
        networks = candidate.get("path") or []
        target_data = selected_payload.get("target")
        target_asn = target_data.get("asn") if isinstance(target_data, dict) else None
        destination_network = (
            target_asn
            or (networks[-1] if networks else None)
            or selected_payload.get("dest_asn")
            or "destination ASN"
        )
        if candidate.get("reaches_target"):
            detail = (
                "The selected MTR entered the destination ASN. This does not prove "
                "that the exact target or service was reachable."
            )
            selected_payload.update(
                verdict={
                    "severity": "ok",
                    "verdict": "Target Network Observed",
                    "detail": detail,
                    "signals": [],
                },
                severity="ok",
                confidence="medium",
                recommendation=(
                    "If the service symptom persists, diagnose the exact hostname or IP "
                    "before closing or escalating."
                ),
                evidence=[
                    f"{vantage} observed the destination network {destination_network} "
                    "in its sampled path."
                ],
                path_status="target_network_observed",
            )
        else:
            detail = (
                "The selected sampled MTR did not expose the destination ASN. A partial "
                "trace alone does not prove that the destination is unreachable."
            )
            selected_payload.update(
                verdict={
                    "severity": "warning",
                    "verdict": "Incomplete Sample",
                    "detail": detail,
                    "signals": [],
                },
                severity="warning",
                confidence="low",
                recommendation=(
                    "Compare another probe and diagnose the exact hostname or IP before "
                    "escalating."
                ),
                evidence=[
                    f"{vantage} exposed {len(points)} observed hop(s)"
                    + (f" and ended at {networks[-1]}." if networks else ".")
                ],
                path_status="incomplete",
            )
        target = (
            f"{selected_payload.get('source_asn', '—')} → "
            f"{selected_payload.get('dest_asn', '—')}"
        )
        view = investigation.from_payload(self.active_mode, target, selected_payload)
        self.investigation_result = view
        self._set_verdict(
            view.verdict,
            view.severity,
            view.culprit,
            view.confidence,
            view.recommendation,
            self._sample_context(view, candidate),
        )
        self.query_one("#metrics", Static).update(self._metrics_text(view))
        self.query_one("#findings", Static).update(self._findings_text(view))
        log = self.query_one("#console", RichLog)
        log.clear()
        log.write(json.dumps(view.raw, indent=2, sort_keys=True, default=str))

    def _selected_path_candidate(self) -> dict:
        candidates = (self.result or {}).get("candidates") or []
        if candidates:
            return candidates[min(self.selected_candidate, len(candidates) - 1)]
        return (self.result or {}).get("optimal_path") or {}

    def _has_globe_path(self) -> bool:
        candidates = (self.result or {}).get("candidates") or []
        if not candidates and (self.result or {}).get("optimal_path"):
            candidates = [(self.result or {})["optimal_path"]]
        for candidate in candidates:
            points = candidate.get("hop_points") or candidate.get("geo_points") or []
            if sum(
                point.get("lat") is not None and point.get("lon") is not None
                for point in points
            ) >= 2:
                return True
        return False

    def _render_path_rows(self, rows: list[dict]) -> None:
        table = self.query_one("#hops", DataTable)
        table.clear()
        for index, row in enumerate(rows, 1):
            latency = row.get("avg_ms")
            if latency is None:
                latency = row.get("rtt_ms")
            if latency is None:
                latency = row.get("elapsed_ms")
            loss = row.get("loss_pct")
            if loss is None:
                loss = row.get("Loss%")
            endpoint_parts = [row.get("name"), row.get("host") or row.get("ip")]
            endpoint = " · ".join(str(value) for value in endpoint_parts if value)
            network = row.get("asn") or row.get("ASN") or row.get("label") or "—"
            location = ", ".join(
                str(value)
                for value in (
                    row.get("city"),
                    row.get("country_code"),
                    row.get("location"),
                )
                if value
            )
            answers = ", ".join(str(value) for value in row.get("values") or [])
            context = " · ".join(value for value in (location, answers) if value)
            table.add_row(
                str(row.get("hop") or row.get("count") or index),
                f"{float(latency):.1f} ms" if latency is not None else "—",
                f"{float(loss):.1f}%" if loss is not None else "—",
                endpoint or row.get("label") or "—",
                str(network),
                context or str(row.get("status") or "—"),
            )

    def _switch_mode(self, mode: str) -> None:
        if self.running or mode == self.active_mode:
            return
        source = self.query_one("#source", Input)
        destination = self.query_one("#destination", Input)
        self.form_values[self.active_mode] = (source.value, destination.value)
        self.active_mode = mode
        source.value, destination.value = self.form_values.get(mode, ("", ""))
        select = self.query_one("#mode", Select)
        if str(select.value) != mode:
            select.value = mode
        self._clear_result()
        self._update_placeholders(mode)
        source.focus()

    def _clear_result(self) -> None:
        self.showing_outcome = False
        self.outcome_available = False
        self.result = None
        self.investigation_result = None
        self.selected_candidate = 0
        self.query_one("#candidates", DataTable).clear()
        self.query_one("#candidates", DataTable).add_class("hidden")
        self.query_one("#hops", DataTable).clear()
        self.query_one("#console", RichLog).clear()
        self.query_one("#globe", Button).disabled = True
        self.query_one("#verdict", Static).update(self._verdict_text())
        self._set_verdict_class("idle")
        self.query_one("#findings", Static).update(self._empty_findings_text())
        self.query_one("#metrics", Static).update("No measurements yet.")
        self.query_one("#tabs", TabbedContent).active = "findings-tab"
        self._update_result_density()

    def _invalidate_outcome_for_edit(self) -> None:
        self._clear_result()
        self._set_status("Inputs changed; run the investigation again")

    def _update_placeholders(self, mode: str) -> None:
        primary, secondary = _MODE_FIELDS.get(mode, ("Primary input", "Optional input"))
        primary_label, secondary_label = _MODE_LABELS[mode]
        title, help_text, plan, action = _MODE_COPY[mode]
        source = self.query_one("#source", Input)
        destination = self.query_one("#destination", Input)
        baseline = self.query_one("#baseline", Select)
        source.placeholder = primary
        source.border_title = primary_label
        destination.placeholder = secondary
        destination.border_title = secondary_label
        baseline.border_title = "Snapshot"
        self.query_one("#record-type", Select).border_title = "Record"
        self.query_one("#planner", Select).border_title = "Planner"
        destination.disabled = False
        destination.set_class(not bool(secondary) or mode == "dns", "hidden")
        self.query_one("#record-type", Select).set_class(mode != "dns", "hidden")
        baseline.set_class(mode != "explain", "hidden")
        self.query_one("#planner", Select).set_class(mode != "capture", "hidden")
        self.query_one("#globe", Button).set_class(mode not in _PATH_MODES, "hidden")
        self.query_one("#run", Button).label = action
        self.query_one("#form-title", Static).update(title)
        self.query_one("#form-help", Static).update(help_text)
        plan_text = Text("PLAN  ", style="bold #6fd6e7")
        plan_text.append(plan)
        self.query_one("#plan", Static).update(plan_text)
        for _, items in _NAV_GROUPS:
            for _, nav_mode in items:
                self.query_one(f"#nav-{nav_mode}", Button).set_class(
                    nav_mode == mode,
                    "active",
                )
        if mode == "explain" and not discover_baselines():
            message = "No saved snapshots found; use Save snapshot first"
        elif mode == "host":
            message = "Enter a hostname or IP to start a new investigation"
        else:
            message = help_text
        self._set_status(message)

    def _refresh_baselines(self, select_newest: bool = False) -> None:
        select = self.query_one("#baseline", Select)
        options = discover_baselines()
        select.set_options(options)
        if select_newest and options:
            select.value = options[0][1]

    def _set_verdict(
        self,
        verdict: str,
        severity: str,
        culprit: str,
        confidence: str,
        action: str = "",
        context: str = "",
    ) -> None:
        color = {
            "ok": "#48d6a0",
            "warning": "#f3ba57",
            "critical": "#ff747c",
            "error": "#ff747c",
            "running": "#69d9ed",
        }.get(severity, "#a9c0c7")
        text = Text()
        text.append(f"{verdict.upper()}\n", style=f"bold {color}")
        text.append("Likely owner  ", style="dim")
        text.append(culprit or "undetermined", style="bold")
        text.append("    Confidence  ", style="dim")
        text.append(confidence or "unknown", style="bold")
        widget = self.query_one("#verdict", Static)
        if context:
            context = " ".join(context.split())
            context_limit = max(24, widget.size.width - 8)
            if len(context) > context_limit:
                context = f"{context[: context_limit - 1].rstrip()}…"
            text.append(f"\n{context}", style="dim")
        if action:
            action = " ".join(action.split())
            limit = max(24, widget.size.width - 12)
            if len(action) > limit:
                action = f"{action[: limit - 1].rstrip()}…"
            text.append("\nNext  ", style="dim")
            text.append(action, style="bold")
        widget.update(text)
        self._set_verdict_class(severity)

    def _set_verdict_class(self, severity: str) -> None:
        widget = self.query_one("#verdict", Static)
        for value in ("ok", "warning", "critical", "error", "running"):
            widget.remove_class(f"severity-{value}")
        if severity != "idle":
            widget.add_class(f"severity-{severity}")

    def _verdict_text(self) -> Text:
        text = Text("READY TO INVESTIGATE\n", style="bold #8be9f8")
        text.append(
            "Start with a destination. Netpath will preserve the evidence behind its answer.",
            style="#91a8ae",
        )
        return text

    def _empty_findings_text(self) -> Text:
        if self.active_mode == "capture":
            text = Text("LOCAL CAPTURE\n", style="bold #6fd6e7")
            text.append(
                "Review a bounded capture plan before collection. Netpath retains flow-level "
                "evidence and deletes the raw packet file.\n\n"
            )
            text.append("PRIVACY LIMIT\n", style="bold #6fd6e7")
            text.append(
                "Packet prefixes can contain payload bytes during analysis; payloads are not "
                "included in the report. This workflow does not create an F6 incident bundle."
            )
            return text
        if self.active_mode not in _STRUCTURED_MODES:
            text = Text("EXPERT TOOL\n", style="bold #6fd6e7")
            text.append(
                "This workspace runs the existing CLI workflow and streams its output to Raw.\n\n"
            )
            text.append("OUTPUT CONTRACT\n", style="bold #6fd6e7")
            text.append(
                "It does not produce a normalized verdict or an F6 incident bundle yet."
            )
            return text
        text = Text("THE QUESTION\n", style="bold #6fd6e7")
        text.append(
            "Is the issue local, on the route, or at the destination — and who owns the next action?\n\n"
        )
        text.append("WHAT YOU'LL GET\n", style="bold #6fd6e7")
        text.append(
            "A verdict, confidence, likely owner, strongest evidence, and a redacted incident bundle."
        )
        return text

    def _findings_text(self, view: investigation.InvestigationResult) -> Text:
        text = Text()
        if view.detail:
            text.append("WHAT HAPPENED\n", style="bold #6fd6e7")
            text.append(f"{view.detail}\n\n")
        text.append("WHY WE THINK THIS\n", style="bold #6fd6e7")
        if view.evidence:
            for item in view.evidence[:5]:
                text.append("• ", style="#6fd6e7")
                text.append(f"{item}\n")
        else:
            text.append("• No anomalous evidence was reported.\n", style="dim")
        if view.baseline_changes:
            text.append("\nCHANGED FROM SNAPSHOT\n", style="bold #f3ba57")
            for change in view.baseline_changes:
                text.append(f"• {change}\n")
        text.append("\nNEXT ACTION\n", style="bold #6fd6e7")
        text.append(view.recommendation)
        return text

    def _metrics_text(self, view: investigation.InvestigationResult) -> Text:
        text = Text("MEASUREMENTS\n", style="bold #6fd6e7")
        if view.metrics:
            longest = min(max(len(label) for label, _ in view.metrics), 24)
            for label, value in view.metrics:
                text.append(f"{label[:longest]:<{longest}}  ", style="dim")
                text.append(f"{value}\n", style="bold")
        else:
            text.append("No summary metrics were produced.\n", style="dim")
        if view.mode in _PATH_MODES:
            text.append("\nPROVENANCE\n", style="bold #6fd6e7")
            text.append(
                "These are sampled remote paths to a representative discovered target, "
                "not every route between the named locations or networks.",
                style="dim",
            )
        return text

    def _sample_context(
        self,
        view: investigation.InvestigationResult,
        candidate: dict | None = None,
    ) -> str:
        if view.mode not in _PATH_MODES:
            return f"Target  {view.target}" if view.target else ""
        raw = view.raw
        candidate = candidate or raw.get("optimal_path") or next(
            iter(raw.get("candidates") or []), {}
        )
        vantage = candidate.get("probe") or raw.get("source_asn") or "remote probe"
        target = raw.get("target_ip") or "representative target"
        origin = raw.get("target_origin")
        target_label = f"{target} ({origin})" if origin else str(target)
        state = (
            "destination ASN observed"
            if candidate.get("reaches_target")
            else "partial trace"
        )
        return f"Sample  {vantage} → {target_label} · {state}"

    def _set_status(self, message: str, error: bool = False) -> None:
        style = "bold #ff747c" if error else "#6fd6e7"
        self.query_one("#status", Static).update(Text(message, style=style))


def run(
    source: str = "",
    destination: str = "",
    mode: str = "host",
    token: str | None = None,
    dns_timeout: int = 3,
) -> None:
    normalized_mode = "aspath" if mode == "asn" else mode
    PathTui(
        source=source,
        destination=destination,
        mode=normalized_mode,
        token=token,
        dns_timeout=dns_timeout,
    ).run()
