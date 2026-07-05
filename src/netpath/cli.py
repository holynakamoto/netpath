from __future__ import annotations

import json
import sys
import time
from typing import Optional

import requests
import typer
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from netpath import __version__
from netpath import country as country_mod
from netpath import cli_json as _cli_json_mod, cli_measurement as _cli_measurement_mod
from netpath import display, globalping as globalping_mod, globe as globe_mod
from netpath import explain as explain_mod
from netpath import monitor as monitor_mod
from netpath import iperf as iperf_mod, mtr as mtr, paris as paris, servers, speedtest, targets as targets_mod
from netpath.asn import normalize_asn
from netpath.cli_json import _apply_path_json_contract, _worst_exit_code
from netpath.cli_measurement import _fetch_rum, _merge_globalping_path_results
from netpath.cli_monitor import _display_monitor_result, _parse_interval_seconds
from netpath.diagnosis import diagnose

app = typer.Typer(
    help="netpath — probe throughput, latency, and packet loss to an ASN.",
    add_completion=False,
    no_args_is_help=True,
)

# ── shared options ────────────────────────────────────────────────────────────

_COUNT   = typer.Option(3,     "--count",    "-n",  help="Max servers / endpoints to test")
_DUR     = typer.Option(5,     "--duration", "-d",  help="iperf3 seconds per direction")
_CYCLES  = typer.Option(10,    "--cycles",   "-c",  help="Probe cycles (mtr) / probes (traceroute)")
_NO_TPUT = typer.Option(False, "--no-throughput",   help="Skip throughput test")
_CF_TOK  = typer.Option(None,  "--cf-token",
                         envvar="NETPATH_CF_TOKEN",
                         help="Cloudflare API token with radar:read (or set NETPATH_CF_TOKEN)")
_GP_TOK  = typer.Option(None,  "--gp-token",
                         envvar="NETPATH_GLOBALPING_TOKEN",
                         help="Globalping token for a higher rate limit (or set NETPATH_GLOBALPING_TOKEN); optional")
_TRACE_FUSION = typer.Option(
    False,
    "--trace-fusion",
    help="Fuse mtr, Paris traceroute, UDP traceroute, and TCP traceroute observations by hop",
)



def _set_globalping_error(rows: list[dict], asn: str, msg: str) -> None:
    """Record a Globalping error on the summary row matching asn."""
    for row in rows:
        if row["asn"] == asn:
            row.setdefault("probe_errors", {})["globalping"] = msg
            return


_fallback_trace = _cli_measurement_mod._fallback_trace
_measure = _cli_measurement_mod._measure


def _check_deps(no_throughput: bool) -> bool:
    _cli_measurement_mod.mtr = mtr
    _cli_measurement_mod.paris = paris
    return _cli_measurement_mod._check_deps(no_throughput)


def _trace(host: str, cycles: int, prefer_tcp: bool = False) -> tuple[list[dict], str]:
    original = _cli_measurement_mod._fallback_trace
    _cli_measurement_mod.mtr = mtr
    _cli_measurement_mod.paris = paris
    _cli_measurement_mod._fallback_trace = _fallback_trace
    try:
        return _cli_measurement_mod._trace(host, cycles, prefer_tcp=prefer_tcp)
    finally:
        _cli_measurement_mod._fallback_trace = original


def _run_test(*args, **kwargs) -> dict:
    kwargs.setdefault("_measure_impl", _measure)
    return _cli_measurement_mod._run_test(*args, **kwargs)


def _collect_asn_json(*args, **kwargs) -> dict:
    kwargs.setdefault("_run_test_impl", _run_test)
    return _cli_json_mod._collect_asn_json(*args, **kwargs)


def _collect_endpoint_json(*args, **kwargs) -> dict:
    kwargs.setdefault("_run_test_impl", _run_test)
    return _cli_json_mod._collect_endpoint_json(*args, **kwargs)


# ── asn subcommand ────────────────────────────────────────────────────────────

@app.command()
def asn(
    target:        str  = typer.Argument(..., help="Target ASN, e.g. AS15169 or 15169"),
    count:         int  = _COUNT,
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    no_throughput: bool = _NO_TPUT,
    cf_token:      Optional[str] = _CF_TOK,
    output_json:   bool = typer.Option(False, "--json", help="Output results as JSON to stdout; suppresses terminal display"),
    globe:         bool = typer.Option(False, "--globe", "-g", help="Open interactive 3D globe visualization after probe"),
    ecmp_passes:   int  = typer.Option(1, "--ecmp-passes", help="Number of mtr passes for ECMP path divergence detection"),
    compare_v6:    bool = typer.Option(False, "--compare-v6", help="Run parallel IPv4/IPv6 traces and display side-by-side"),
    trace_fusion:  bool = _TRACE_FUSION,
):
    """Test latency, packet loss, and throughput to servers in a specific ASN."""
    asn_norm = normalize_asn(target)
    if globe and output_json:
        print("Warning: --globe is ignored when --json is set", file=sys.stderr)
        globe = False
    if not output_json:
        display.header(__version__)
    skip_throughput = _check_deps(no_throughput)

    if not output_json:
        display.console.print(f"[dim]Scanning iperf3 servers in [bold]{asn_norm}[/bold]…[/dim]\n")
    if not output_json:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=display.console, transient=True) as progress:
            progress.add_task("Resolving hostnames + bulk ASN lookup via Cymru…", total=None)
            found = servers.find_servers_in_asn(asn_norm, max_count=count)
    else:
        found = servers.find_servers_in_asn(asn_norm, max_count=count)

    if not found:
        if output_json:
            print(json.dumps({"error": f"No public iperf3 servers found in {asn_norm}"}, indent=2))
        else:
            display.error(
                f"No public iperf3 servers found in {asn_norm}.\n"
                "  Try: https://github.com/R0GGER/public-iperf3-servers"
            )
        raise typer.Exit(1)

    if not output_json:
        display.console.print(f"[green]✓[/green] Found [bold]{len(found)}[/bold] server(s) in {asn_norm}\n")

    if output_json:
        output = _collect_asn_json(
            asn_norm,
            count=count,
            duration=duration,
            cycles=cycles,
            skip_throughput=skip_throughput,
            cf_token=cf_token,
            ecmp_passes=ecmp_passes,
            compare_v6=compare_v6,
            trace_fusion=trace_fusion,
            candidates=found,
        )
        print(json.dumps(output, indent=2))
        code = _worst_exit_code([output.get("verdict", {})])
        if code:
            raise typer.Exit(code)
    else:
        last_hubs: list[dict] = []
        verdicts: list[dict] = []
        for server in found:
            r = _run_test(
                host=server["HOST"], port=server["port"],
                server_meta=server, target_asn=asn_norm,
                cycles=cycles, duration=duration,
                skip_throughput=skip_throughput, cf_token=cf_token,
                ecmp_passes=ecmp_passes, compare_v6=compare_v6,
                trace_fusion=trace_fusion,
            )
            last_hubs = r["hubs"]
            if r.get("verdict"):
                verdicts.append(r["verdict"])
        if globe and last_hubs:
            globe_mod.render({asn_norm: last_hubs})
        code = _worst_exit_code(verdicts)
        if code:
            raise typer.Exit(code)


# ── host subcommand ───────────────────────────────────────────────────────────

@app.command("host")
def host(
    destination:   str  = typer.Argument(..., help="Destination hostname or IP, e.g. zoom.us or 170.114.52.2"),
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    throughput:    bool = typer.Option(False, "--throughput", help="Try iperf3 throughput to the destination on port 5201"),
    cf_token:      Optional[str] = _CF_TOK,
    output_json:   bool = typer.Option(False, "--json", help="Output results as JSON to stdout; suppresses terminal display"),
    globe:         bool = typer.Option(False, "--globe", "-g", help="Open interactive 3D globe visualization after probe"),
    ecmp_passes:   int  = typer.Option(1, "--ecmp-passes", help="Number of mtr passes for ECMP path divergence detection"),
    compare_v6:    bool = typer.Option(False, "--compare-v6", help="Run parallel IPv4/IPv6 traces and display side-by-side"),
    trace_fusion:  bool = _TRACE_FUSION,
):
    """Trace and diagnose the path to an exact hostname or IP endpoint."""
    if globe and output_json:
        print("Warning: --globe is ignored when --json is set", file=sys.stderr)
        globe = False
    endpoint = targets_mod.resolve_endpoint(destination)
    if endpoint is None:
        msg = f"Could not resolve destination {destination!r}"
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    skip_throughput = _check_deps(not throughput)
    if not output_json:
        display.header(__version__)
        display.console.print(
            f"[dim]Tracing exact endpoint [bold]{endpoint['input']}[/bold] "
            f"→ [bold]{endpoint['ip']}[/bold]…[/dim]"
        )
        if endpoint.get("asn"):
            name = f" · {endpoint['name']}" if endpoint.get("name") else ""
            display.console.print(f"[dim]Cymru: {endpoint['asn']}{name}[/dim]\n")
        else:
            display.console.print("[dim]Cymru: no public ASN attribution found[/dim]\n")

    result = _collect_endpoint_json(
        endpoint,
        duration=duration,
        cycles=cycles,
        skip_throughput=skip_throughput,
        cf_token=cf_token,
        ecmp_passes=ecmp_passes,
        compare_v6=compare_v6,
        trace_fusion=trace_fusion,
        json_mode=output_json,
    )
    if output_json:
        print(json.dumps(result, indent=2))
    else:
        display.console.print(
            "[dim]Endpoint mode uses the resolved service address directly; "
            "ASN/city representative target selection is bypassed.[/dim]"
        )
        if globe and result.get("path"):
            target_asn = endpoint.get("asn") or endpoint["input"]
            hubs = [
                {
                    "count": hop.get("hop"),
                    "host": hop.get("host"),
                    "ASN": hop.get("asn"),
                    "Loss%": hop.get("loss_pct"),
                    "Avg": hop.get("avg_ms"),
                }
                for hop in result["path"]
            ]
            globe_mod.render({target_asn: hubs})

    code = _worst_exit_code([result.get("verdict", {})])
    if code:
        raise typer.Exit(code)


# ── explain subcommand ─────────────────────────────────────────────────────────

@app.command("explain")
def explain(
    destination:   str  = typer.Argument(..., help="Destination hostname or IP, e.g. zoom.us or 170.114.52.2"),
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    throughput:    bool = typer.Option(False, "--throughput", help="Try iperf3 throughput to the destination on port 5201"),
    cf_token:      Optional[str] = _CF_TOK,
    baseline:      Optional[str] = typer.Option(None, "--baseline", help="JSON/JSONL monitor history to compare against"),
    output_json:   bool = typer.Option(False, "--json", help="Output explanation as JSON to stdout; suppresses terminal display"),
    trace_fusion:  bool = _TRACE_FUSION,
):
    """Trace an endpoint and turn the measurements into an escalation-ready incident report."""
    endpoint = targets_mod.resolve_endpoint(destination)
    if endpoint is None:
        msg = f"Could not resolve destination {destination!r}"
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    baseline_snapshot = None
    if baseline:
        try:
            baseline_snapshot = explain_mod.load_baseline(baseline)
        except FileNotFoundError:
            msg = f"Baseline file not found: {baseline}"
            if output_json:
                print(json.dumps({"error": msg}, indent=2))
            else:
                display.error(msg)
            raise typer.Exit(1)
        except json.JSONDecodeError:
            msg = f"Baseline file is not valid JSON/JSONL: {baseline}"
            if output_json:
                print(json.dumps({"error": msg}, indent=2))
            else:
                display.error(msg)
            raise typer.Exit(1)

    skip_throughput = _check_deps(not throughput)
    if not output_json:
        display.header(__version__)
        display.console.print(
            f"[dim]Explaining path to [bold]{endpoint['input']}[/bold] "
            f"→ [bold]{endpoint['ip']}[/bold]…[/dim]"
        )
        if endpoint.get("asn"):
            name = f" · {endpoint['name']}" if endpoint.get("name") else ""
            display.console.print(f"[dim]Cymru: {endpoint['asn']}{name}[/dim]\n")
        else:
            display.console.print("[dim]Cymru: no public ASN attribution found[/dim]\n")

    result = _collect_endpoint_json(
        endpoint,
        duration=duration,
        cycles=cycles,
        skip_throughput=skip_throughput,
        cf_token=cf_token,
        trace_fusion=trace_fusion,
        json_mode=output_json,
    )
    report = explain_mod.build_report(
        destination=destination,
        result=result,
        baseline=baseline_snapshot,
    )

    if output_json:
        print(json.dumps(report, indent=2))
    else:
        display.explain_report(report)

    code = _worst_exit_code([result.get("verdict", {})])
    if code:
        raise typer.Exit(code)


# ── monitor subcommand ──────────────────────────────────────────────────────────

@app.command()
def monitor(
    target:        str  = typer.Argument(..., help="Target ASN, e.g. AS15169 or 15169"),
    count:         int  = _COUNT,
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    no_throughput: bool = _NO_TPUT,
    cf_token:      Optional[str] = _CF_TOK,
    every:         Optional[str] = typer.Option(None, "--every", help="Repeat interval, e.g. 30s, 10m, 2h"),
    runs:          int = typer.Option(1, "--runs", help="Number of snapshots to collect; ignored with --forever"),
    forever:       bool = typer.Option(False, "--forever", help="Run until interrupted; requires --every"),
    store:         Optional[str] = typer.Option(None, "--store", help="History directory (default: ~/.netpath/monitor)"),
    endpoint_target: Optional[str] = typer.Option(None, "--target", help="Monitor this exact hostname/IP instead of an auto-selected ASN endpoint"),
    webhook:       Optional[str] = typer.Option(None, "--webhook", help="POST regressions to this webhook URL"),
    fail_on_regression: bool = typer.Option(False, "--fail-on-regression", help="Exit 2 when a regression is detected"),
    rtt_threshold: float = typer.Option(25.0, "--rtt-threshold-ms", help="Minimum RTT increase to report"),
    loss_threshold: float = typer.Option(1.0, "--loss-threshold-pct", help="Minimum loss increase to report"),
    throughput_drop: float = typer.Option(30.0, "--throughput-drop-pct", help="Minimum download drop to report"),
    trace_fusion:  bool = _TRACE_FUSION,
):
    """Persist ASN probe snapshots and report path or performance regressions."""
    asn_norm = normalize_asn(target)
    if forever and every is None:
        raise typer.BadParameter("--forever requires --every")
    if runs < 1:
        raise typer.BadParameter("--runs must be at least 1")

    interval_seconds = _parse_interval_seconds(every) if every else None
    skip_throughput = _check_deps(no_throughput)
    endpoint = None
    monitor_key = asn_norm
    if endpoint_target:
        endpoint = targets_mod.resolve_endpoint(endpoint_target)
        if endpoint is None:
            display.error(f"Could not resolve destination {endpoint_target!r}")
            raise typer.Exit(1)
        monitor_key = f"{asn_norm}:{endpoint['input']}->{endpoint['ip']}"
    display.header(__version__)
    iterations = None if forever else runs
    run_index = 0
    regression_seen = False

    while iterations is None or run_index < iterations:
        run_index += 1
        if endpoint is None:
            display.console.print(f"[dim]Collecting monitor snapshot for [bold]{asn_norm}[/bold]…[/dim]\n")
        else:
            display.console.print(
                f"[dim]Collecting monitor snapshot for [bold]{asn_norm}[/bold] "
                f"via exact endpoint [bold]{endpoint['input']}[/bold] → [bold]{endpoint['ip']}[/bold]…[/dim]\n"
            )
        try:
            if endpoint is None:
                result = _collect_asn_json(
                    asn_norm,
                    count=count,
                    duration=duration,
                    cycles=cycles,
                    skip_throughput=skip_throughput,
                    cf_token=cf_token,
                    trace_fusion=trace_fusion,
                )
            else:
                result = _collect_endpoint_json(
                    endpoint,
                    duration=duration,
                    cycles=cycles,
                    skip_throughput=skip_throughput,
                    cf_token=cf_token,
                    trace_fusion=trace_fusion,
                )
        except RuntimeError as e:
            display.error(str(e))
            raise typer.Exit(1)

        monitor_key_for_history = monitor_key
        history = monitor_mod.load_history(monitor_key_for_history, store)
        result["route_stability"] = monitor_mod.summarize_history(
            history + [
                monitor_mod.snapshot_from_result(
                    result,
                    asn=asn_norm,
                    target_host=result["target_host"],
                    monitor_key=monitor_key_for_history,
                )
            ]
        )
        snapshot = monitor_mod.snapshot_from_result(
            result,
            asn=asn_norm,
            target_host=result["target_host"],
            monitor_key=monitor_key,
        )
        previous = monitor_mod.load_latest(monitor_key, store)
        changes = monitor_mod.compare_snapshots(
            previous,
            snapshot,
            rtt_threshold_ms=rtt_threshold,
            loss_threshold_pct=loss_threshold,
            throughput_drop_pct=throughput_drop,
        )
        history_file = monitor_mod.append_snapshot(snapshot, store)
        _display_monitor_result(snapshot, changes, str(history_file))

        regressions = [c for c in changes if c != "No regression detected." and not c.startswith("No previous")]
        if regressions:
            regression_seen = True
            if webhook:
                try:
                    requests.post(
                        webhook,
                        json={"asn": asn_norm, "snapshot": snapshot, "changes": regressions},
                        timeout=10,
                    ).raise_for_status()
                except Exception as e:
                    display.warn(f"webhook failed: {e}")
            if fail_on_regression:
                raise typer.Exit(2)

        if interval_seconds is not None and (iterations is None or run_index < iterations):
            display.console.print(f"[dim]Sleeping {interval_seconds}s before next snapshot…[/dim]\n")
            time.sleep(interval_seconds)

    if fail_on_regression and regression_seen:
        raise typer.Exit(2)


# ── country subcommand ────────────────────────────────────────────────────────

@app.command()
def country(
    code:          str  = typer.Argument(..., help="ISO country code, e.g. US, GB, IL"),
    top:           int  = typer.Option(10,    "--top",  "-t", help="Number of top ASNs to test"),
    count:         int  = _COUNT,
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    no_throughput: bool = _NO_TPUT,
    cf_token:      Optional[str] = _CF_TOK,
    globe:         bool = typer.Option(False, "--globe", "-g", help="Open interactive 3D globe visualization after probes"),
    gp_token:      Optional[str] = _GP_TOK,
    no_remote:     bool = typer.Option(False, "--no-remote", help="Skip Globalping in-network measurements"),
    compare_v6:    bool = typer.Option(False, "--compare-v6", help="Run parallel IPv4/IPv6 traces in country mode"),
    ecmp_passes:   int  = typer.Option(1, "--ecmp-passes", help="Number of mtr passes for ECMP path divergence detection"),
    trace_fusion:  bool = _TRACE_FUSION,
    show_ids:      bool = typer.Option(False, "--show-ids", help="Show Globalping measurement IDs while scheduling"),
):
    """Test the top N ASNs (by allocated IPv4 address space) for a country."""
    code = code.upper()
    display.header(__version__)
    skip_throughput = _check_deps(no_throughput)

    display.console.print(
        f"[dim]Ranking top {top} ASNs for [bold]{code}[/bold] "
        f"via RIPE allocation data + Cymru…[/dim]\n"
    )
    try:
        top_asns = country_mod.get_top_asns(code, top_n=top)
    except Exception as e:
        display.error(f"ASN lookup failed: {e}")
        raise typer.Exit(1)

    display.console.print(f"[green]✓[/green] Top {len(top_asns)} ASNs for [bold]{code}[/bold]:\n")
    for i, a in enumerate(top_asns, 1):
        name = display.clean_asn_name(a["name"])
        meta_parts = []
        if a.get("addresses"):
            meta_parts.append(f"{a['addresses']:,} IPs")
        if a.get("prefix_count"):
            n = a["prefix_count"]
            meta_parts.append(f"{n} prefix{'es' if n != 1 else ''}")
        meta = f"  [dim]{' · '.join(meta_parts)}[/dim]" if meta_parts else ""
        display.console.print(f"  {i:>2}.  [bold yellow]{a['asn']}[/bold yellow]  {name}{meta}")
    display.console.print()

    # Run HTTP speedtest ONCE as the user's own baseline before per-ISP tests
    if not skip_throughput:
        display.console.print("[dim]Measuring your connection baseline (speed.cloudflare.com)…[/dim]")
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=display.console, transient=True) as p:
            p.add_task("speed.cloudflare.com ↑↓", total=None)
            st_result = speedtest.run(duration=duration)
        ul, dl = speedtest.extract_stats(st_result)
        errors = st_result.get("errors", {})
        if ul is None and dl is None:
            # Both directions failed — preserve the original warning behavior.
            msg = "; ".join(f"{d}: {e}" for d, e in errors.items()) or "unknown error"
            display.warn(f"Baseline speedtest failed: {msg}")
        else:
            display.baseline_panel(ul, dl, errors=errors)

    # Warm the server cache once — all subsequent find_servers_in_asn calls are free
    display.console.print("[dim]Fetching + resolving iperf3 server list…[/dim]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=display.console, transient=True) as progress:
        progress.add_task("DNS + bulk ASN lookup via Cymru…", total=None)
        servers._fetch_and_resolve()
    display.console.print()

    # Globalping: probe inventory (single request) before the regular sweep
    _gp_covered_asns: set[str] = set()          # ASNs with at least one connected probe
    _gp_test_ips: dict[str, str] = {}           # asn → test IP for ping target
    _user_public_ip: Optional[str] = None
    _gp_auth_failed = False

    if not no_remote:
        display.console.print("[dim]Discovering Globalping probes…[/dim]")
        try:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=display.console, transient=True) as p:
                p.add_task("Fetching Globalping probe inventory…", total=None)
                _gp_probes = globalping_mod.fetch_probes(gp_token)
        except globalping_mod.GlobalpingAuthError:
            if gp_token:
                display.error(
                    "Globalping rejected the token from --gp-token / "
                    "NETPATH_GLOBALPING_TOKEN — skipping remote measurements"
                )
            else:
                display.error(
                    "Globalping rejected the probe inventory request as unauthorized "
                    "— skipping remote measurements"
                )
            _gp_probes = []
            _gp_auth_failed = True
        _gp_asn_counts = globalping_mod.count_probes_by_asn(_gp_probes)
        for _ai in top_asns:
            if _gp_asn_counts.get(int(normalize_asn(_ai["asn"])[2:])):
                _gp_covered_asns.add(_ai["asn"])

        if _gp_covered_asns:
            _user_public_ip = globalping_mod.get_public_ip()
            if _user_public_ip is None:
                display.warn("Could not determine your public IP — Globalping measurements will be skipped")
                _gp_covered_asns = set()
            else:
                display.console.print(
                    f"[green]✓[/green] Globalping probes found in "
                    f"{len(_gp_covered_asns)}/{len(top_asns)} ASNs\n"
                )
        elif not _gp_auth_failed:
            display.console.print(
                "[dim]No Globalping probes found in any target ASN — skipping remote measurements[/dim]\n"
            )

    summary_rows: list[dict] = []
    hubs_for_globe: dict[str, list[dict]] = {}

    for i, asn_info in enumerate(top_asns, 1):
        asn_str  = asn_info["asn"]
        isp_name = asn_info["name"]

        display.isp_section(i, asn_str, isp_name,
                            asn_info.get("addresses", 0),
                            asn_info.get("prefix_count", 0))

        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=display.console, transient=True) as p:
            p.add_task(f"Searching iperf3 servers in {asn_str}…", total=None)
            asn_servers = servers.find_servers_in_asn(asn_str, max_count=count)

        if asn_servers:
            server = asn_servers[0]
            if not no_remote:
                _gp_test_ips[asn_str] = server["HOST"]
            can_test_throughput = not no_throughput and iperf_mod.available()
            r = _run_test(
                host=server["HOST"], port=server["port"],
                server_meta=server, target_asn=asn_str,
                cycles=cycles, duration=duration,
                skip_throughput=not can_test_throughput,
                show_server_heading=True,
                cf_token=cf_token,
                ecmp_passes=ecmp_passes,
                compare_v6=compare_v6,
                trace_fusion=trace_fusion,
            )
        else:
            test_ip, target_origin = country_mod.get_test_target_for_asn(asn_str)
            if test_ip:
                if not no_remote:
                    _gp_test_ips[asn_str] = test_ip
                origin_label = (
                    "PeeringDB IXP trace target"
                    if target_origin == "peeringdb"
                    else "Atlas probe trace target"
                )
                display.console.print(
                    f"  [dim]→ {test_ip}  ({origin_label} — no iperf3 server in {asn_str})[/dim]\n"
                )
                meta = {"HOST": test_ip, "SITE": isp_name, "COUNTRY": code,
                        "asn": asn_str, "port": 5201}
                r = _run_test(
                    host=test_ip, port=5201,
                    server_meta=meta, target_asn=asn_str,
                    cycles=cycles, duration=duration,
                    skip_throughput=True,
                    show_server_heading=False,
                    cf_token=cf_token,
                    prefer_tcp=True,
                    ecmp_passes=ecmp_passes,
                    compare_v6=compare_v6,
                    trace_fusion=trace_fusion,
                )
            elif asn_str in _gp_covered_asns:
                # No live local target, but Globalping probes exist inside the
                # ASN — measure remotely (ISP → tester) instead of tracing a
                # dead address. The scheduling block below targets the
                # tester's public IP for these rows.
                display.console.print(
                    f"  [dim]→ remote-only — no live trace target in {asn_str}; "
                    f"Globalping probes will measure toward your public IP[/dim]\n"
                )
                _rum = _fetch_rum(asn_str, cf_token)
                if _rum:
                    display.rum_only_panel(_rum, asn_str)
                summary_rows.append({
                    "asn": asn_str,
                    "name": display.clean_asn_name(isp_name),
                    "remote_only": True,
                    "rum": _rum,
                })
                continue
            else:
                if no_remote:
                    reason = "no iperf3 server or Atlas probe; remote measurement disabled (--no-remote)"
                else:
                    reason = "no iperf3 server, Atlas probe, or usable Globalping coverage"
                display.console.print(f"  [dim]→ no coverage — {reason}[/dim]\n")
                _rum = _fetch_rum(asn_str, cf_token)
                if _rum:
                    display.rum_only_panel(_rum, asn_str)
                summary_rows.append({
                    "asn": asn_str,
                    "name": display.clean_asn_name(isp_name),
                    "skip_reason": reason,
                    "rum": _rum,
                })
                continue

        summary_rows.append({
            "asn":  asn_str,
            "name": display.clean_asn_name(isp_name),
            **r,
        })
        if globe:
            hubs_for_globe[asn_str] = r.get("hubs", [])

    # Globalping: schedule, poll, and merge results after all regular measurements
    if not no_remote and _gp_covered_asns and _user_public_ip:
        display.console.print("[dim]Scheduling Globalping measurements…[/dim]")
        _gp_mids: dict[str, dict[str, str]] = {}

        _pending_asns = [_ai["asn"] for _ai in top_asns if _ai["asn"] in _gp_covered_asns]
        _scheduled_count = 0
        for _idx, _asn_str in enumerate(_pending_asns):
            # Remote-only ISPs have no local target — point Globalping at the
            # tester's public IP so the ISP → tester path is measured instead.
            _tip = _gp_test_ips.get(_asn_str) or _user_public_ip
            try:
                _mids = globalping_mod.schedule_measurements(
                    _asn_str, _tip, _user_public_ip, gp_token
                )
                _gp_mids[_asn_str] = _mids
                _scheduled_count += 1
                if show_ids:
                    display.console.print(
                        f"  [dim]{_asn_str}: ping {_mids['ping']}  "
                        f"mtr {_mids['mtr']}[/dim]"
                    )
            except requests.HTTPError as _e:
                _status = _e.response.status_code if _e.response is not None else None
                if _status == 422:
                    _set_globalping_error(summary_rows, _asn_str, "no Globalping coverage")
                elif _status == 429:
                    _set_globalping_error(
                        summary_rows, _asn_str,
                        "rate limit reached — pass --gp-token for higher limits",
                    )
                elif _status == 401:
                    display.error(
                        "Globalping rejected the token from --gp-token / "
                        "NETPATH_GLOBALPING_TOKEN — skipping remote measurements"
                    )
                    for _rest in _pending_asns[_idx:]:
                        _set_globalping_error(summary_rows, _rest, "invalid Globalping token")
                    break
                else:
                    _set_globalping_error(summary_rows, _asn_str, str(_e))
            except Exception as _e:
                _set_globalping_error(summary_rows, _asn_str, str(_e))

        # Record no-probe ASNs
        if _scheduled_count and not show_ids:
            display.console.print(
                f"  [dim]Scheduled {_scheduled_count} Globalping measurement "
                f"pair{'s' if _scheduled_count != 1 else ''}[/dim]"
            )
        for _ai in top_asns:
            if _ai["asn"] not in _gp_covered_asns:
                _set_globalping_error(summary_rows, _ai["asn"], "no Globalping coverage")

        _all_mids = [_m for _ms in _gp_mids.values() for _m in _ms.values()]
        if _all_mids:
            display.console.print(
                f"\n[dim]Waiting for {len(_all_mids)} Globalping measurements "
                f"(up to 60 s)…[/dim]"
            )
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=display.console, transient=True) as _p:
                _p.add_task("Polling Globalping API…", total=None)
                _statuses = globalping_mod.poll_until_done(_all_mids, gp_token)

            for _asn_str, _mids in _gp_mids.items():
                _ping_id = _mids["ping"]
                _mtr_id = _mids["mtr"]
                _gp_data: dict = {"measurement_ids": _mids}

                if _statuses.get(_ping_id) == "finished":
                    _ping_results = globalping_mod.fetch_results(_ping_id, gp_token)
                    _rtt = globalping_mod.parse_ping_rtt(_ping_results)
                    if _rtt:
                        _gp_data["ping_rtt"] = _rtt
                    _stats = globalping_mod.parse_ping_stats(_ping_results)
                    if _stats:
                        if "loss_pct" in _stats:
                            _gp_data["ping_loss_pct"] = _stats["loss_pct"]
                        if "jitter_ms" in _stats:
                            _gp_data["ping_jitter_ms"] = _stats["jitter_ms"]
                        _gp_data["ping_packets"] = _stats["packets"]
                elif _statuses.get(_ping_id) == "timed_out":
                    _set_globalping_error(summary_rows, _asn_str, "timed out")

                if _statuses.get(_mtr_id) == "finished":
                    _path = globalping_mod.parse_mtr_as_path(
                        globalping_mod.fetch_results(_mtr_id, gp_token)
                    )
                    if _path:
                        _gp_data["outbound_as_path"] = _path
                elif _statuses.get(_mtr_id) == "timed_out":
                    _set_globalping_error(summary_rows, _asn_str, "timed out")

                _row = next((r for r in summary_rows if r["asn"] == _asn_str), None)
                if _row is not None:
                    _row["globalping"] = _gp_data

    elif not no_remote:
        # No probes found, auth failure, or public IP unavailable — record for all ASNs
        if _gp_auth_failed:
            _gp_msg = "invalid Globalping token" if gp_token else "Globalping authentication failed"
        else:
            _gp_msg = "no Globalping coverage"
        for _ai in top_asns:
            _set_globalping_error(summary_rows, _ai["asn"], _gp_msg)

    # Re-derive verdicts for rows that gained near-target figures — diagnose()
    # already ran inside _measure() before the Globalping merge (and never ran
    # at all for remote-only rows), so the summary table and exit code would
    # otherwise ignore the remote data.
    for _row in summary_rows:
        _gp = _row.get("globalping") or {}
        if (
            _gp.get("ping_loss_pct") is not None
            or _gp.get("ping_jitter_ms") is not None
        ):
            _row["verdict"] = diagnose(_row)

    country_answer = explain_mod.build_country_operator_answer(code, summary_rows)
    if country_answer:
        display.operator_answer(country_answer)
    display.country_summary(code, summary_rows)
    if globe and hubs_for_globe:
        globe_mod.render(hubs_for_globe)

    verdicts = [row["verdict"] for row in summary_rows if row.get("verdict")]
    exit_code = _worst_exit_code(verdicts)
    if exit_code:
        raise typer.Exit(exit_code)


@app.command("aspath")
def aspath(
    source:      str = typer.Argument(..., help="Source ASN, e.g. AS7922 or 7922"),
    dest:        str = typer.Argument(..., help="Destination ASN, e.g. AS7018 or 7018"),
    gp_token:    Optional[str] = _GP_TOK,
    target_ip:   Optional[str] = typer.Option(None, "--target", help="Use this destination IP instead of automatic target discovery"),
    globe:       bool = typer.Option(False, "--globe", "-g", help="Open interactive globe visualization for the measured AS path"),
    output_json: bool = typer.Option(False, "--json", help="Output results as JSON to stdout"),
):
    """Rank measured AS paths from probes inside one ASN toward another ASN."""
    source_asn = normalize_asn(source)
    dest_asn = normalize_asn(dest)
    if not output_json:
        display.header(__version__)
        display.console.print(
            f"[dim]Finding Globalping probes in [bold]{source_asn}[/bold] "
            f"and a live target in [bold]{dest_asn}[/bold]…[/dim]\n"
        )

    try:
        probes = globalping_mod.fetch_probes(gp_token)
    except globalping_mod.GlobalpingAuthError:
        if output_json:
            print(json.dumps({"error": "Globalping authentication failed"}, indent=2))
        else:
            display.error("Globalping rejected the token from --gp-token / NETPATH_GLOBALPING_TOKEN")
        raise typer.Exit(1)

    probe_counts = globalping_mod.count_probes_by_asn(probes)
    if not probe_counts.get(int(source_asn[2:])):
        msg = f"No connected Globalping probes are currently available in {source_asn}"
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    target_info = targets_mod.discover_target(dest_asn, user_target=target_ip)
    if not target_info:
        msg = f"No live target found in {dest_asn}"
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)
    target_ip = target_info["ip"]
    target_origin = target_info.get("origin")

    if not output_json:
        origin = {
            "iperf3": "iperf3 server",
            "atlas": "Atlas probe address",
            "peeringdb": "PeeringDB IXP address",
            "ripe-prefix": "RIPEstat prefix sample",
            "user": "user-provided target",
        }.get(target_origin or "", "trace target")
        display.console.print(f"[dim]Using {target_ip} ({origin}) as the destination target.[/dim]")
        if target_info.get("reason"):
            display.console.print(f"[dim]{target_info['reason']}[/dim]")
        display.console.print("[dim]Scheduling Globalping ping + MTR…[/dim]\n")

    try:
        mids = globalping_mod.schedule_path_measurements(source_asn, target_ip, gp_token)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 429:
            msg = "Globalping rate limit reached — pass --gp-token for higher limits"
        elif status == 422:
            msg = f"No Globalping probes matched {source_asn}"
        elif status == 401:
            msg = "Globalping authentication failed"
        else:
            msg = str(exc)
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    statuses = globalping_mod.poll_until_done(list(mids.values()), gp_token)
    result: dict = {
        "source_asn": source_asn,
        "dest_asn": dest_asn,
        "target_ip": target_ip,
        "target_origin": target_origin,
        "target": target_info,
        "measurement_ids": mids,
        "statuses": statuses,
        "candidates": [],
    }

    _merge_globalping_path_results(
        result, mids, statuses, target_ip, dest_asn, target_info, gp_token
    )
    _apply_path_json_contract(result)

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        display.aspath_report(source_asn, dest_asn, target_ip, result)
        if globe:
            globe_mod.render_aspath(result)

    if not result.get("optimal_path"):
        raise typer.Exit(1)


@app.command("citypath")
def citypath(
    source_city: str = typer.Argument(..., help='Source city, e.g. "Los Angeles"'),
    dest_city:   str = typer.Argument(..., help='Destination city, e.g. "Tel Aviv"'),
    gp_token:    Optional[str] = _GP_TOK,
    globe:       bool = typer.Option(False, "--globe", "-g", help="Open interactive globe visualization for the measured city path"),
    output_json: bool = typer.Option(False, "--json", help="Output results as JSON to stdout"),
):
    """Rank measured AS paths between two cities using Globalping + RIPE Atlas."""
    if not output_json:
        display.header(__version__)
        display.console.print(
            f"[dim]Finding source probes in [bold]{source_city}[/bold] "
            f"and a target near [bold]{dest_city}[/bold]…[/dim]\n"
        )

    try:
        source = targets_mod.geocode_city(source_city)
        dest = targets_mod.geocode_city(dest_city)
    except Exception as exc:
        msg = f"City geocoding failed: {exc}"
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    if not source or not dest:
        msg = "Could not geocode one or both cities"
        if output_json:
            print(json.dumps({"error": msg, "source": source_city, "dest": dest_city}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    target_info = targets_mod.atlas_target_near_city(dest)
    if not target_info:
        msg = f"No connected RIPE Atlas IPv4 target found near {dest['name']}, {dest['country_code']}"
        if output_json:
            print(json.dumps({"error": msg, "source_city": source, "dest_city": dest}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    if not output_json:
        display.console.print(
            f"[dim]Using {target_info['ip']} "
            f"(Atlas probe {target_info.get('distance_km')} km from "
            f"{dest['name']}, {dest['country_code']}) as the destination target.[/dim]"
        )
        if target_info.get("reason"):
            display.console.print(f"[dim]{target_info['reason']}[/dim]")
        display.console.print("[dim]Scheduling Globalping ping + MTR…[/dim]\n")

    source_location = {
        "name": source["name"],
        "city": source["name"],
        "country": source["country_code"],
    }
    try:
        mids = globalping_mod.schedule_location_path_measurements(
            source_location, target_info["ip"], gp_token
        )
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 429:
            msg = "Globalping rate limit reached — pass --gp-token for higher limits"
        elif status == 422:
            msg = f"No Globalping probes matched {source['name']}, {source['country_code']}"
        elif status == 401:
            msg = "Globalping authentication failed"
        else:
            msg = str(exc)
        if output_json:
            print(json.dumps({"error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    statuses = globalping_mod.poll_until_done(list(mids.values()), gp_token)
    target_asn = target_info.get("asn")
    result: dict = {
        "source_city": source,
        "dest_city": dest,
        "source_asn": f"{source['name']}, {source['country_code']}",
        "dest_asn": f"{dest['name']}, {dest['country_code']}",
        "target_ip": target_info["ip"],
        "target_origin": target_info.get("origin"),
        "target": target_info,
        "measurement_ids": mids,
        "statuses": statuses,
        "candidates": [],
    }

    _merge_globalping_path_results(
        result, mids, statuses, target_info["ip"], target_asn, target_info, gp_token
    )
    _apply_path_json_contract(result)

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        display.aspath_report(result["source_asn"], result["dest_asn"], target_info["ip"], result)
        if globe:
            globe_mod.render_aspath(result)

    if not result.get("optimal_path"):
        raise typer.Exit(1)


@app.command("target")
def target(
    asn:         str = typer.Argument(..., help="ASN to find a usable target for, e.g. AS7018 or 7018"),
    target_ip:   Optional[str] = typer.Option(None, "--target", help="Validate this user-provided IP against the ASN"),
    output_json: bool = typer.Option(False, "--json", help="Output target metadata as JSON"),
):
    """Find a usable IPv4 measurement target inside an ASN."""
    asn_norm = normalize_asn(asn)
    if not output_json:
        display.header(__version__)
        display.console.print(f"[dim]Finding a usable target in [bold]{asn_norm}[/bold]…[/dim]\n")

    try:
        info = targets_mod.discover_target(asn_norm, user_target=target_ip)
    except Exception as exc:
        if output_json:
            print(json.dumps({"asn": asn_norm, "error": str(exc)}, indent=2))
        else:
            display.error(f"Target discovery failed: {exc}")
        raise typer.Exit(1)

    if not info:
        msg = f"No usable target found in {asn_norm}"
        if output_json:
            print(json.dumps({"asn": asn_norm, "error": msg}, indent=2))
        else:
            display.error(msg)
        raise typer.Exit(1)

    try:
        geo = globe_mod.geolocate_hosts([info["ip"]])
        if geo.get(info["ip"]):
            info["geo"] = geo[info["ip"]]
    except Exception:
        pass

    output = {"asn": asn_norm, **info}
    if output_json:
        print(json.dumps(output, indent=2))
    else:
        display.target_report(asn_norm, info)


_COUNTRY_NAMES: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AR": "Argentina",
    "AT": "Austria", "AU": "Australia", "AZ": "Azerbaijan",
    "BA": "Bosnia and Herzegovina", "BD": "Bangladesh", "BE": "Belgium",
    "BG": "Bulgaria", "BH": "Bahrain", "BN": "Brunei", "BO": "Bolivia",
    "BR": "Brazil", "BY": "Belarus", "CA": "Canada", "CH": "Switzerland",
    "CL": "Chile", "CM": "Cameroon", "CN": "China", "CO": "Colombia",
    "CR": "Costa Rica", "CU": "Cuba", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "DO": "Dominican Republic",
    "DZ": "Algeria", "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt",
    "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji",
    "FR": "France", "GB": "United Kingdom", "GE": "Georgia",
    "GH": "Ghana", "GR": "Greece", "GT": "Guatemala", "HK": "Hong Kong",
    "HN": "Honduras", "HR": "Croatia", "HU": "Hungary", "ID": "Indonesia",
    "IE": "Ireland", "IL": "Israel", "IN": "India", "IQ": "Iraq",
    "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JM": "Jamaica",
    "JO": "Jordan", "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan",
    "KH": "Cambodia", "KR": "South Korea", "KW": "Kuwait", "KZ": "Kazakhstan",
    "LB": "Lebanon", "LI": "Liechtenstein", "LK": "Sri Lanka",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya",
    "MA": "Morocco", "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro",
    "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia",
    "MT": "Malta", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NG": "Nigeria", "NL": "Netherlands", "NO": "Norway",
    "NP": "Nepal", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama",
    "PE": "Peru", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland",
    "PT": "Portugal", "PY": "Paraguay", "QA": "Qatar", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia",
    "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia", "SK": "Slovakia",
    "SM": "San Marino", "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SV": "El Salvador", "SY": "Syria", "TH": "Thailand", "TJ": "Tajikistan",
    "TN": "Tunisia", "TR": "Turkey", "TT": "Trinidad and Tobago",
    "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "US": "United States", "UY": "Uruguay", "UZ": "Uzbekistan",
    "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen",
    "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}


@app.command()
def coverage(
    gp_token: Optional[str] = _GP_TOK,
    top: int = typer.Option(50, "--top", "-t", help="Number of top countries to show"),
    globe: bool = typer.Option(False, "--globe", "-g", help="Render choropleth globe after fetching"),
):
    """Show Globalping probe coverage ranked by country."""
    display.header(__version__)
    try:
        probes = globalping_mod.fetch_probes(gp_token)
    except globalping_mod.GlobalpingAuthError:
        if gp_token:
            display.error(
                "Globalping rejected the token from --gp-token / NETPATH_GLOBALPING_TOKEN"
            )
        else:
            display.error("Globalping rejected the probe inventory request as unauthorized")
        raise typer.Exit(1)
    coverage_map = globalping_mod.coverage_by_country(probes)

    if not coverage_map:
        display.warn("No coverage data returned from the Globalping API.")
        raise typer.Exit(1)

    ranked = sorted(coverage_map.items(), key=lambda x: x[1], reverse=True)[:top]

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        title=f"[bold]Globalping Coverage — Top {top} Countries[/bold]",
    )
    table.add_column("#", style="dim", justify="right")
    table.add_column("Code", justify="center")
    table.add_column("Country", min_width=22)
    table.add_column("Probes", justify="right", style="bold")

    for rank, (cc, probe_count) in enumerate(ranked, 1):
        table.add_row(
            str(rank),
            cc,
            _COUNTRY_NAMES.get(cc, cc),
            str(probe_count),
        )

    display.console.print(table)

    if globe:
        globe_mod.render_coverage(coverage_map)


def run():
    app()
