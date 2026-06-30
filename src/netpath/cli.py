import json
import queue
import re
import socket
import subprocess
import sys
import threading
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from netpath import __version__
from netpath import country as country_mod
from netpath import display, globe as globe_mod, iperf as iperf_mod, latency as latency_mod
from netpath import mtr, pmtu as pmtu_mod, rum as rum_mod, servers, speedtest
from netpath.asn import normalize_asn
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

_SEVERITY_CODE = {"ok": 0, "warning": 1, "critical": 2}


def _worst_exit_code(verdicts: list[dict]) -> int:
    return max((_SEVERITY_CODE.get(v.get("severity", "ok"), 0) for v in verdicts), default=0)


# ── internal helpers ──────────────────────────────────────────────────────────

def _extract_as_path(hubs: list[dict]) -> list[str]:
    asns: list[str] = []
    for h in hubs:
        asn = h.get("ASN", "")
        if asn and asn != "AS???" and (not asns or asns[-1] != asn):
            asns.append(asn)
    return asns


def _classify_path(hubs: list[dict], target_asn: str) -> dict:
    """
    Determine whether the traceroute reached target_asn.
    Returns {complete, rtt_ms, entry_transit_asn, stall_hop}.
    complete is True only when target_asn appears in at least one hub's ASN field.
    rtt_ms is the Avg RTT of the last hub inside target_asn (None when incomplete).
    entry_transit_asn is the last non-AS??? ASN before target_asn (complete) or
    the last non-AS??? ASN seen (incomplete); None if no resolvable ASNs exist.
    stall_hop is the count of the last responsive hub when path is incomplete (None when complete).
    """
    target_norm = normalize_asn(target_asn)

    complete = any(
        normalize_asn(h.get("ASN", "")) == target_norm
        for h in hubs
        if h.get("ASN") and h.get("ASN") != "AS???"
    )

    if complete:
        rtt_ms = None
        for h in reversed(hubs):
            if (h.get("ASN") and normalize_asn(h["ASN"]) == target_norm
                    and h.get("host") not in ("???", None, "")
                    and h.get("Avg", 0) > 0):
                rtt_ms = h["Avg"]
                break

        entry_transit_asn = None
        prev_asn = None
        for h in hubs:
            asn = h.get("ASN", "")
            if not asn or asn == "AS???":
                continue
            asn_norm = normalize_asn(asn)
            if asn_norm == target_norm:
                entry_transit_asn = prev_asn
                break
            prev_asn = asn_norm

        return {"complete": True, "rtt_ms": rtt_ms, "entry_transit_asn": entry_transit_asn, "stall_hop": None}
    else:
        rtt_ms = None
        entry_transit_asn = None
        stall_hop = None
        for h in hubs:
            asn = h.get("ASN", "")
            if asn and asn != "AS???":
                entry_transit_asn = normalize_asn(asn)
            if h.get("host") not in ("???", None, ""):
                stall_hop = h.get("count")
                if h.get("Avg", 0) > 0:
                    rtt_ms = h["Avg"]

        return {"complete": False, "rtt_ms": rtt_ms, "entry_transit_asn": entry_transit_asn, "stall_hop": stall_hop}


def _parse_ping_avg(output: str) -> float | None:
    m = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/', output)
    if m:
        return float(m.group(1))
    m = re.search(r'round-trip min/avg/max/stddev = [\d.]+/([\d.]+)/', output)
    if m:
        return float(m.group(1))
    return None


def _run_ping_probe(host: str, duration: int, result_q: queue.Queue) -> None:
    count = min(duration, 5)
    try:
        proc = subprocess.run(
            ["ping", "-c", str(count), "-i", "1", host],
            capture_output=True, text=True, timeout=count + 10,
        )
        if proc.returncode != 0:
            stderr_lower = proc.stderr.lower()
            if "permission" in stderr_lower or "operation not permitted" in stderr_lower:
                result_q.put(None)
                return
        result_q.put(_parse_ping_avg(proc.stdout))
    except FileNotFoundError:
        result_q.put(None)
    except PermissionError:
        result_q.put(None)
    except subprocess.TimeoutExpired:
        result_q.put(None)
    except Exception:
        result_q.put(None)


def _check_deps(no_throughput: bool) -> bool:
    if not mtr.available():
        display.error("mtr not found — install with: brew install mtr")
        raise typer.Exit(1)
    return no_throughput


def _trace(host: str, cycles: int, prefer_tcp: bool = False) -> tuple[list[dict], str]:
    try:
        return mtr.run(host, cycles=cycles), "mtr"
    except mtr.MtrPermissionError:
        return mtr.run_traceroute(host, probes=cycles, prefer_tcp=prefer_tcp), "traceroute"


def _fetch_rum(asn: str, cf_token: str | None) -> dict | None:
    if not cf_token:
        return None
    try:
        return rum_mod.fetch_asn_quality(asn, cf_token)
    except ValueError as e:
        display.warn(f"Cloudflare RUM: {e}")
        return None
    except Exception:
        return None


def _measure(host: str, port: int, target_asn: str,
             cycles: int, duration: int, skip_throughput: bool,
             cf_token: str | None = None, prefer_tcp: bool = False,
             ecmp_passes: int = 1, compare_v6: bool = False) -> dict:
    """Collect all measurement data. Returns enriched result dict.
    No display calls, no json_mode parameter.
    Internal _-prefixed keys carry state needed by _run_test() for display.
    """
    result: dict = {
        "as_path": [], "last_rtt_ms": None, "rum": None,
        "hubs": [], "bufferbloat_ms": None,
        "download_mbps": None, "upload_mbps": None, "verdict": {},
        "path_complete": False, "verified_rtt_ms": None,
        "entry_transit_asn": None, "stall_hop": None,
        "jitter_ms": None, "probe_count": cycles,
        "pmtu": None, "tcp_connect_ms": None, "tls_handshake_ms": None,
        "ecmp_paths": None, "path_changes": 0,
        "hubs_v4": None, "hubs_v6": None,
        "_trace_method": None, "_trace_error": None,
        "_iperf_upload": None, "_iperf_download": None,
        "_iperf_idle_rtt": None, "_iperf_loaded_rtt": None, "_iperf_error": None,
        "_speedtest_upload": None, "_speedtest_download": None, "_speedtest_error": None,
        "_v6_warn": None,
    }

    # Trace — single pass, multi-pass ECMP, or dual-stack IPv4/IPv6
    if compare_v6:
        v6_host = None
        try:
            v6_info = socket.getaddrinfo(host, None, socket.AF_INET6)
            v6_host = v6_info[0][4][0]
        except socket.gaierror:
            result["_v6_warn"] = "IPv6 resolution failed — showing IPv4 only"

        v4_q: queue.Queue = queue.Queue()
        v6_q: queue.Queue = queue.Queue()

        def _run_v4():
            try:
                v4_q.put(_trace(host, cycles, prefer_tcp=prefer_tcp))
            except RuntimeError as exc:
                v4_q.put(exc)

        def _run_v6():
            if v6_host is None:
                v6_q.put(None)
                return
            try:
                v6_hubs, _ = _trace(v6_host, cycles)
                v6_q.put(v6_hubs)
            except Exception:
                v6_q.put(None)

        t_v4 = threading.Thread(target=_run_v4, daemon=True)
        t_v6 = threading.Thread(target=_run_v6, daemon=True)
        t_v4.start()
        t_v6.start()
        t_v4.join(timeout=cycles * 4 + 35)
        t_v6.join(timeout=cycles * 4 + 35)

        v4_val = v4_q.get_nowait() if not v4_q.empty() else RuntimeError("v4 trace timed out")
        if isinstance(v4_val, RuntimeError):
            result["_trace_error"] = str(v4_val)
            return result
        hubs, method = v4_val
        result["_trace_method"] = method
        result["hubs_v4"] = hubs
        result["hubs_v6"] = v6_q.get_nowait() if not v6_q.empty() else None

    elif ecmp_passes > 1:
        try:
            all_passes = mtr.run(host, cycles=cycles, passes=ecmp_passes)
            comparison = mtr._compare_as_paths(all_passes)
            result["ecmp_paths"] = comparison["ecmp_paths"]
            result["path_changes"] = comparison["path_changes"]
            hubs = all_passes[0] if all_passes else []
            result["_trace_method"] = "mtr"
        except mtr.MtrPermissionError:
            hubs = mtr.run_traceroute(host, probes=cycles, prefer_tcp=prefer_tcp)
            result["_trace_method"] = "traceroute"
        except RuntimeError as e:
            result["_trace_error"] = str(e)
            return result

    else:
        try:
            hubs, method = _trace(host, cycles, prefer_tcp=prefer_tcp)
            result["_trace_method"] = method
        except RuntimeError as e:
            result["_trace_error"] = str(e)
            return result

    result["as_path"] = _extract_as_path(hubs)
    result["hubs"] = hubs

    responsive = [h for h in hubs if h.get("host") not in ("???", None, "")]
    if responsive:
        result["jitter_ms"] = round(
            sum(h.get("StDev", 0.0) or 0.0 for h in responsive) / len(responsive), 2
        )

    for _h in reversed(hubs):
        if _h.get("host") not in ("???", None, "") and _h.get("Avg", 0) > 0:
            result["last_rtt_ms"] = _h["Avg"]
            break

    classification = _classify_path(hubs, target_asn)
    result["path_complete"] = classification["complete"]
    result["verified_rtt_ms"] = classification["rtt_ms"]
    result["entry_transit_asn"] = classification["entry_transit_asn"]
    result["stall_hop"] = classification["stall_hop"]
    if not classification["complete"] and classification["rtt_ms"] is not None:
        result["last_rtt_ms"] = classification["rtt_ms"]

    # PMTU black-hole detection and TCP/TLS application latency
    result["pmtu"] = pmtu_mod.probe(host)
    result["tcp_connect_ms"] = latency_mod.measure_tcp_connect(host)
    result["tls_handshake_ms"] = latency_mod.measure_tls_handshake(host)

    rum_data = _fetch_rum(target_asn, cf_token)
    result["rum"] = rum_data

    if skip_throughput:
        result["verdict"] = diagnose(result)
        return result

    if iperf_mod.available():
        idle_rtt = result["last_rtt_ms"]
        result["_iperf_idle_rtt"] = idle_rtt
        ping_q: queue.Queue = queue.Queue()
        ping_thread = threading.Thread(
            target=_run_ping_probe, args=(host, duration, ping_q), daemon=True
        )
        ping_thread.start()
        try:
            upload, download = iperf_mod.run_bidirectional(host, port, duration)
            ping_thread.join(timeout=duration + 10)
            try:
                loaded_rtt = ping_q.get_nowait()
            except queue.Empty:
                loaded_rtt = None
            result["_iperf_loaded_rtt"] = loaded_rtt
            if idle_rtt is not None and loaded_rtt is not None:
                result["bufferbloat_ms"] = round(loaded_rtt - idle_rtt, 1)
            result["download_mbps"] = download.get("recv_bps", download.get("bps", 0)) / 1e6
            result["upload_mbps"] = upload.get("bps", 0) / 1e6
            result["_iperf_upload"] = upload
            result["_iperf_download"] = download
        except RuntimeError as e:
            ping_thread.join(timeout=5)
            result["_iperf_error"] = str(e)
        result["verdict"] = diagnose(result)
        return result

    # iperf3 not installed — fall back to HTTP speedtest as a baseline.
    # This measures user → Cloudflare, NOT user → target ASN.
    try:
        st_result = speedtest.run(duration=duration)
        upload, download = speedtest.extract_stats(st_result)
        result["download_mbps"] = download.get("recv_bps", download.get("bps", 0)) / 1e6
        result["upload_mbps"] = upload.get("bps", 0) / 1e6
        result["_speedtest_upload"] = upload
        result["_speedtest_download"] = download
    except RuntimeError as e:
        result["_speedtest_error"] = str(e)

    result["verdict"] = diagnose(result)
    return result


def _run_test(host: str, port: int, server_meta: dict, target_asn: str,
              cycles: int, duration: int, skip_throughput: bool,
              cf_token: str | None = None, show_server_heading: bool = True,
              json_mode: bool = False, prefer_tcp: bool = False,
              ecmp_passes: int = 1, compare_v6: bool = False) -> dict:
    """Run trace + optional throughput test. Returns enriched result dict."""
    if show_server_heading and not json_mode:
        display.server_heading(server_meta)

    if not json_mode:
        display.console.print(f"  [dim]Tracing path ({cycles} probes)…[/dim]")
        if not skip_throughput:
            if iperf_mod.available():
                display.console.print(
                    f"  [dim]Measuring throughput via iperf3 to {host}:{port} ({duration}s each direction)…[/dim]"
                )
            else:
                display.console.print(
                    "  [dim]iperf3 not installed — showing Cloudflare baseline "
                    "(install iperf3 for cross-ASN measurement)…[/dim]"
                )
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=display.console, transient=True) as p:
            p.add_task(f"probing → {host}", total=None)
            result = _measure(host, port, target_asn, cycles, duration, skip_throughput, cf_token,
                              prefer_tcp=prefer_tcp, ecmp_passes=ecmp_passes, compare_v6=compare_v6)
    else:
        result = _measure(host, port, target_asn, cycles, duration, skip_throughput, cf_token,
                          prefer_tcp=prefer_tcp, ecmp_passes=ecmp_passes, compare_v6=compare_v6)

    if result.get("_trace_error"):
        if not json_mode:
            display.error(f"trace: {result['_trace_error']}")
        return result

    if result.get("_trace_method") == "traceroute" and not json_mode:
        display.console.print("  [dim](mtr unavailable — using traceroute + Cymru ASN lookup)[/dim]\n")

    if not json_mode:
        if compare_v6 and result.get("hubs_v6") is not None:
            display.dual_stack_columns(result["hubs_v4"], result["hubs_v6"], target_asn)
        else:
            if compare_v6 and result.get("_v6_warn"):
                display.warn(result["_v6_warn"])
            display.path_table(result["hubs"], target_asn)
        display.as_path_summary(result["hubs"])

    rum_data = result.get("rum")

    if skip_throughput:
        if rum_data and not json_mode:
            display.rum_only_panel(rum_data, target_asn)
        if not json_mode:
            display.verdict_panel(result["verdict"])
        return result

    if iperf_mod.available():
        if result.get("_iperf_download") is not None:
            if not json_mode:
                display.throughput_and_rum(
                    result["_iperf_upload"], result["_iperf_download"],
                    rum=rum_data, server=f"{host} (iperf3)"
                )
                display.bufferbloat_line(result.get("_iperf_idle_rtt"), result.get("_iperf_loaded_rtt"))
                display.verdict_panel(result["verdict"])
        else:
            if not json_mode:
                display.warn(f"iperf3 to {host}:{port} failed: {result.get('_iperf_error', 'unknown error')}")
                if rum_data:
                    display.rum_only_panel(rum_data, target_asn)
                display.verdict_panel(result["verdict"])
        return result

    # iperf3 not installed path
    if result.get("_speedtest_download") is not None:
        if not json_mode:
            display.throughput_and_rum(
                result["_speedtest_upload"], result["_speedtest_download"],
                rum=rum_data, server="speed.cloudflare.com (baseline — not cross-ASN)"
            )
    elif result.get("_speedtest_error") and not json_mode:
        display.warn(f"speedtest: {result['_speedtest_error']}")
        if rum_data:
            display.rum_only_panel(rum_data, target_asn)

    if not json_mode:
        display.verdict_panel(result["verdict"])
    return result


# ── asn subcommand ────────────────────────────────────────────────────────────

@app.command()
def asn(
    target:        str  = typer.Argument(..., help="Target ASN, e.g. AS15169 or 15169"),
    count:         int  = _COUNT,
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    no_throughput: bool = _NO_TPUT,
    cf_token:      str | None = _CF_TOK,
    output_json:   bool = typer.Option(False, "--json", help="Output results as JSON to stdout; suppresses terminal display"),
    globe:         bool = typer.Option(False, "--globe", "-g", help="Open interactive 3D globe visualization after probe"),
    ecmp_passes:   int  = typer.Option(1, "--ecmp-passes", help="Number of mtr passes for ECMP path divergence detection"),
    compare_v6:    bool = typer.Option(False, "--compare-v6", help="Run parallel IPv4/IPv6 traces and display side-by-side"),
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
        server = found[0]
        result = _run_test(
            host=server["HOST"], port=server["port"],
            server_meta=server, target_asn=asn_norm,
            cycles=cycles, duration=duration,
            skip_throughput=skip_throughput, cf_token=cf_token,
            json_mode=True, ecmp_passes=ecmp_passes, compare_v6=compare_v6,
        )
        upload_mbps   = result.get("upload_mbps")
        download_mbps = result.get("download_mbps")
        output = {
            "asn": asn_norm,
            "target_host": server["HOST"],
            "path": [
                {
                    "hop":      hub.get("count"),
                    "host":     hub.get("host"),
                    "asn":      hub.get("ASN"),
                    "loss_pct": hub.get("Loss%"),
                    "avg_ms":   hub.get("Avg"),
                    "best_ms":  hub.get("Best"),
                    "worst_ms": hub.get("Wrst"),
                    "p50_ms":   hub.get("p50"),
                    "p95_ms":   hub.get("p95"),
                    "p99_ms":   hub.get("p99"),
                }
                for hub in result.get("hubs", [])
            ],
            "throughput": (
                {"upload_mbps": upload_mbps, "download_mbps": download_mbps}
                if upload_mbps is not None or download_mbps is not None
                else None
            ),
            "jitter_ms":        result.get("jitter_ms"),
            "tcp_connect_ms":   result.get("tcp_connect_ms"),
            "tls_handshake_ms": result.get("tls_handshake_ms"),
            "pmtu":             result.get("pmtu"),
            "ecmp_paths":       result.get("ecmp_paths"),
            "path_changes":     result.get("path_changes"),
            "bufferbloat_ms":   result.get("bufferbloat_ms"),
            "rum":              result.get("rum"),
            "verdict":          result.get("verdict", {}),
        }
        print(json.dumps(output, indent=2))
        code = _worst_exit_code([result.get("verdict", {})])
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
            )
            last_hubs = r["hubs"]
            if r.get("verdict"):
                verdicts.append(r["verdict"])
        if globe and last_hubs:
            globe_mod.render({asn_norm: last_hubs})
        code = _worst_exit_code(verdicts)
        if code:
            raise typer.Exit(code)


# ── country subcommand ────────────────────────────────────────────────────────

@app.command()
def country(
    code:          str  = typer.Argument(..., help="ISO country code, e.g. US, GB, IL"),
    top:           int  = typer.Option(10,    "--top",  "-t", help="Number of top ASNs to test"),
    count:         int  = _COUNT,
    duration:      int  = _DUR,
    cycles:        int  = _CYCLES,
    no_throughput: bool = _NO_TPUT,
    cf_token:      str | None = _CF_TOK,
    globe:         bool = typer.Option(False, "--globe", "-g", help="Open interactive 3D globe visualization after probes"),
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
        try:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=display.console, transient=True) as p:
                p.add_task("speed.cloudflare.com ↑↓", total=None)
                st_result = speedtest.run(duration=duration)
            ul, dl = speedtest.extract_stats(st_result)
            display.baseline_panel(ul, dl)
        except RuntimeError as e:
            display.warn(f"Baseline speedtest failed: {e}")

    # Warm the server cache once — all subsequent find_servers_in_asn calls are free
    display.console.print("[dim]Fetching + resolving iperf3 server list…[/dim]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=display.console, transient=True) as progress:
        progress.add_task("DNS + bulk ASN lookup via Cymru…", total=None)
        servers._fetch_and_resolve()
    display.console.print()

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
            can_test_throughput = not no_throughput and iperf_mod.available()
            r = _run_test(
                host=server["HOST"], port=server["port"],
                server_meta=server, target_asn=asn_str,
                cycles=cycles, duration=duration,
                skip_throughput=not can_test_throughput,
                show_server_heading=True,
                cf_token=cf_token,
            )
        else:
            test_ip = country_mod.get_test_ip_for_asn(asn_str)
            if not test_ip:
                display.warn(f"Could not find a test IP for {asn_str} — skipping")
                summary_rows.append({"asn": asn_str, "name": display.clean_asn_name(isp_name),
                                     "as_path": [], "last_rtt_ms": None, "rum": None,
                                     "path_complete": False, "verified_rtt_ms": None,
                                     "entry_transit_asn": None, "stall_hop": None})
                continue

            display.console.print(
                f"  [dim]→ {test_ip}  (traceroute target — no iperf3 server in {asn_str})[/dim]\n"
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
            )

        summary_rows.append({
            "asn":  asn_str,
            "name": display.clean_asn_name(isp_name),
            **r,
        })
        if globe:
            hubs_for_globe[asn_str] = r.get("hubs", [])

    display.country_summary(code, summary_rows)
    if globe and hubs_for_globe:
        globe_mod.render(hubs_for_globe)

    verdicts = [row["verdict"] for row in summary_rows if row.get("verdict")]
    exit_code = _worst_exit_code(verdicts)
    if exit_code:
        raise typer.Exit(exit_code)


def run():
    app()
