import json
import os
import queue
import re
import subprocess
import threading
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from netpath import __version__
from netpath import country as country_mod
from netpath import display, iperf as iperf_mod, mtr, rum as rum_mod, servers, speedtest
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


# ── internal helpers ──────────────────────────────────────────────────────────

def _extract_as_path(hubs: list[dict]) -> list[str]:
    asns: list[str] = []
    for h in hubs:
        asn = h.get("ASN", "")
        if asn and asn != "AS???" and (not asns or asns[-1] != asn):
            asns.append(asn)
    return asns


def _extract_last_rtt(hubs: list[dict]) -> float | None:
    for h in reversed(hubs):
        if h.get("host") not in ("???", None, "") and h.get("Avg", 0) > 0:
            return h["Avg"]
    return None


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


def _trace(host: str, cycles: int) -> tuple[list[dict], str]:
    try:
        return mtr.run(host, cycles=cycles), "mtr"
    except mtr.MtrPermissionError:
        return mtr.run_traceroute(host, probes=cycles), "traceroute"


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


def _run_test(host: str, port: int, server_meta: dict, target_asn: str,
              cycles: int, duration: int, skip_throughput: bool,
              cf_token: str | None = None, show_server_heading: bool = True,
              json_mode: bool = False) -> dict:
    """Run trace + optional throughput test. Returns enriched result dict."""
    result: dict = {"as_path": [], "last_rtt_ms": None, "rum": None,
                    "hubs": [], "bufferbloat_ms": None,
                    "download_mbps": None, "upload_mbps": None, "verdict": {}}

    if show_server_heading and not json_mode:
        display.server_heading(server_meta)

    if not json_mode:
        display.console.print(f"  [dim]Tracing path ({cycles} probes)…[/dim]")
    try:
        if not json_mode:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=display.console, transient=True) as p:
                p.add_task(f"probing → {host}", total=None)
                hubs, method = _trace(host, cycles)
        else:
            hubs, method = _trace(host, cycles)
    except RuntimeError as e:
        if not json_mode:
            display.error(f"trace: {e}")
        return result

    if method == "traceroute" and not json_mode:
        display.console.print("  [dim](mtr unavailable — using traceroute + Cymru ASN lookup)[/dim]\n")

    if not json_mode:
        display.path_table(hubs, target_asn)
        display.as_path_summary(hubs)

    result["as_path"]     = _extract_as_path(hubs)
    result["last_rtt_ms"] = _extract_last_rtt(hubs)
    result["hubs"]        = hubs

    rum_data = _fetch_rum(target_asn, cf_token)
    result["rum"] = rum_data

    if skip_throughput:
        if rum_data and not json_mode:
            display.rum_only_panel(rum_data, target_asn)
        verdict = diagnose(result)
        result["verdict"] = verdict
        if not json_mode:
            display.verdict_panel(verdict)
        return result

    # iperf3 measures the actual path from this host to the server in target_asn.
    # Fall back to HTTP speedtest only if iperf3 is unavailable (that measures
    # user → Cloudflare, not user → target ASN).
    if iperf_mod.available():
        if not json_mode:
            display.console.print(
                f"  [dim]Measuring throughput via iperf3 to {host}:{port} ({duration}s each direction)…[/dim]"
            )
        idle_rtt = result["last_rtt_ms"]
        ping_q: queue.Queue = queue.Queue()
        ping_thread = threading.Thread(
            target=_run_ping_probe, args=(host, duration, ping_q), daemon=True
        )
        ping_thread.start()
        try:
            if not json_mode:
                with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                              console=display.console, transient=True) as p:
                    p.add_task(f"iperf3 → {host} ↑↓", total=None)
                    upload, download = iperf_mod.run_bidirectional(host, port, duration)
            else:
                upload, download = iperf_mod.run_bidirectional(host, port, duration)
            ping_thread.join(timeout=duration + 10)
            try:
                loaded_rtt = ping_q.get_nowait()
            except queue.Empty:
                loaded_rtt = None
            if idle_rtt is not None and loaded_rtt is not None:
                result["bufferbloat_ms"] = round(loaded_rtt - idle_rtt, 1)
            result["download_mbps"] = download.get("recv_bps", download.get("bps", 0)) / 1e6
            result["upload_mbps"]   = upload.get("bps", 0) / 1e6
            verdict = diagnose(result)
            result["verdict"] = verdict
            if not json_mode:
                display.throughput_and_rum(upload, download, rum=rum_data,
                                           server=f"{host} (iperf3)")
                display.bufferbloat_line(idle_rtt, loaded_rtt)
                display.verdict_panel(verdict)
            return result
        except RuntimeError as e:
            ping_thread.join(timeout=5)
            if not json_mode:
                display.warn(f"iperf3 to {host}:{port} failed: {e}")
                if rum_data:
                    display.rum_only_panel(rum_data, target_asn)
            verdict = diagnose(result)
            result["verdict"] = verdict
            if not json_mode:
                display.verdict_panel(verdict)
            return result

    # iperf3 not installed — fall back to HTTP speedtest as a baseline.
    # This measures user → Cloudflare, NOT user → target ASN.
    if not json_mode:
        display.console.print(
            f"  [dim]iperf3 not installed — showing Cloudflare baseline "
            f"(install iperf3 for cross-ASN measurement)…[/dim]"
        )
    try:
        if not json_mode:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          console=display.console, transient=True) as p:
                p.add_task("speed.cloudflare.com ↑↓", total=None)
                st_result = speedtest.run(duration=duration)
        else:
            st_result = speedtest.run(duration=duration)

        upload, download = speedtest.extract_stats(st_result)
        result["download_mbps"] = download.get("recv_bps", download.get("bps", 0)) / 1e6
        result["upload_mbps"]   = upload.get("bps", 0) / 1e6
        if not json_mode:
            display.throughput_and_rum(upload, download, rum=rum_data,
                                       server="speed.cloudflare.com (baseline — not cross-ASN)")

    except RuntimeError as e:
        if not json_mode:
            display.warn(f"speedtest: {e}")
            if rum_data:
                display.rum_only_panel(rum_data, target_asn)

    verdict = diagnose(result)
    result["verdict"] = verdict
    if not json_mode:
        display.verdict_panel(verdict)
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
):
    """Test latency, packet loss, and throughput to servers in a specific ASN."""
    asn_norm = normalize_asn(target)
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
            json_mode=True,
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
            "bufferbloat_ms": result.get("bufferbloat_ms"),
            "rum":            result.get("rum"),
            "verdict":        result.get("verdict", {}),
        }
        print(json.dumps(output, indent=2))
    else:
        for server in found:
            _run_test(
                host=server["HOST"], port=server["port"],
                server_meta=server, target_asn=asn_norm,
                cycles=cycles, duration=duration,
                skip_throughput=skip_throughput, cf_token=cf_token,
            )


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
                                     "as_path": [], "last_rtt_ms": None, "rum": None})
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
            )

        summary_rows.append({
            "asn":  asn_str,
            "name": display.clean_asn_name(isp_name),
            **r,
        })

    display.country_summary(code, summary_rows)


def run():
    app()
