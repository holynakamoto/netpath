from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
import subprocess
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from netpath import display, dns as dns_mod, edge as edge_mod, explain as explain_mod
from netpath import geo as geo_mod, globalping as globalping_mod, globe as globe_mod
from netpath import iperf as iperf_mod, latency as latency_mod, mtr, paris, pmtu as pmtu_mod
from netpath import trace_fusion as trace_fusion_mod
from netpath import rum as rum_mod, speedtest
from netpath.asn import normalize_asn
from netpath.diagnosis import diagnose
from netpath.types import MeasurementResult

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


def _parse_ping_avg(output: str) -> Optional[float]:
    m = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/', output)
    if m:
        return float(m.group(1))
    m = re.search(r'round-trip min/avg/max/stddev = [\d.]+/([\d.]+)/', output)
    if m:
        return float(m.group(1))
    return None


def _run_ping_probe_sync(host: str, duration: int) -> Optional[float]:
    count = min(duration, 5)
    try:
        proc = subprocess.run(
            ["ping", "-c", str(count), "-i", "1", host],
            capture_output=True, text=True, timeout=count + 10,
        )
        if proc.returncode != 0:
            stderr_lower = proc.stderr.lower()
            if "permission" in stderr_lower or "operation not permitted" in stderr_lower:
                return None
        return _parse_ping_avg(proc.stdout)
    except Exception:
        return None


def _check_deps(no_throughput: bool) -> bool:
    if not mtr.available() and paris.detect() is None and not mtr.traceroute_available():
        display.error(
            "no path prober found — install mtr (brew install mtr / apt install mtr) "
            "or traceroute (apt install traceroute; ships with macOS at /usr/sbin/traceroute)"
        )
        raise typer.Exit(1)
    return no_throughput


def _fallback_trace(host: str, cycles: int, prefer_tcp: bool = False) -> tuple[list[dict], str]:
    """mtr lacks raw-socket access — prefer a Paris prober, else system traceroute."""
    binary = paris.detect()
    if binary is not None:
        try:
            return paris.run(host, probes=cycles, binary=binary), binary
        except paris.ParisError:
            pass  # permission denied, timeout, bad output — fall through silently
    return mtr.run_traceroute(host, probes=cycles, prefer_tcp=prefer_tcp), "traceroute"


def _trace(host: str, cycles: int, prefer_tcp: bool = False) -> tuple[list[dict], str]:
    if not mtr.available():
        return _fallback_trace(host, cycles, prefer_tcp=prefer_tcp)
    try:
        return mtr.run(host, cycles=cycles), "mtr"
    except mtr.MtrPermissionError:
        return _fallback_trace(host, cycles, prefer_tcp=prefer_tcp)


def _fetch_rum(asn: str, cf_token: Optional[str]) -> Optional[dict]:
    if not cf_token:
        return None
    try:
        return rum_mod.fetch_asn_quality(asn, cf_token)
    except ValueError as e:
        display.warn(f"Cloudflare RUM: {e}")
        return None
    except Exception:
        return None


def _geo_for_mtr_results(mtr_results: list[dict], extra_hosts: list[str] | None = None) -> dict:
    geo_hosts: list[str] = []
    for item in mtr_results:
        for hop in item.get("result", {}).get("hops", []):
            ip = hop.get("resolvedAddress")
            if not ip:
                continue
            try:
                if ipaddress.ip_address(ip).is_private:
                    continue
            except ValueError:
                pass
            geo_hosts.append(ip)
    geo_hosts.extend(extra_hosts or [])
    if not geo_hosts:
        return {}
    try:
        return globe_mod.geolocate_hosts(list(dict.fromkeys(geo_hosts)))
    except Exception:
        return {}


def _merge_globalping_path_results(
    result: dict,
    mids: dict[str, str],
    statuses: dict[str, str],
    target_ip: str,
    target_asn: str | None,
    target_info: dict,
    gp_token: Optional[str],
) -> None:
    if statuses.get(mids["ping"]) == "finished":
        ping_results = globalping_mod.fetch_results(mids["ping"], gp_token)
        rtt = globalping_mod.parse_ping_rtt(ping_results)
        if rtt:
            result["ping_rtt"] = rtt
        stats = globalping_mod.parse_ping_stats(ping_results)
        if stats:
            result["ping_packets"] = stats.get("packets")
            if "loss_pct" in stats:
                result["ping_loss_pct"] = stats["loss_pct"]
            if "jitter_ms" in stats:
                result["ping_jitter_ms"] = stats["jitter_ms"]

    if statuses.get(mids["mtr"]) == "finished":
        mtr_results = globalping_mod.fetch_results(mids["mtr"], gp_token)
        geo = _geo_for_mtr_results(mtr_results, [target_ip])
        if target_ip and geo.get(target_ip):
            target_info["geo"] = geo[target_ip]
        result["target"] = target_info
        result["candidates"] = globalping_mod.parse_mtr_path_candidates(
            mtr_results, target_asn, geo=geo
        )

    complete_candidates = [c for c in result["candidates"] if c.get("reaches_target")]
    if complete_candidates:
        result["optimal_path"] = complete_candidates[0]
    elif result["candidates"]:
        result["partial_paths"] = result["candidates"]
        result["path_status"] = "incomplete"
        result["path_note"] = (
            "Globalping MTR did not expose a complete AS path to the destination; "
            "the selected target may be non-responsive or filtered."
        )


def _measure(host: str, port: int, target_asn: str,
             cycles: int, duration: int, skip_throughput: bool,
             cf_token: Optional[str] = None, prefer_tcp: bool = False,
             ecmp_passes: int = 1, compare_v6: bool = False,
             service_host: Optional[str] = None, trace_fusion: bool = False) -> MeasurementResult:
    """Collect all measurement data. Returns enriched result dict.
    No display calls, no json_mode parameter.
    Internal _-prefixed keys carry state needed by _run_test() for display.
    """
    result: dict = {
        "as_path": [], "last_rtt_ms": None, "rum": None,
        "hubs": [], "bufferbloat_ms": None,
        "download_mbps": None, "upload_mbps": None, "verdict": {},
        "path_complete": False, "verified_rtt_ms": None,
        "target_asn": target_asn,
        "entry_transit_asn": None, "stall_hop": None,
        "jitter_ms": None, "probe_count": cycles,
        "pmtu": None, "dns": None, "http_edge": None, "geo_path": None,
        "tcp_connect_ms": None, "tls_handshake_ms": None,
        "ecmp_paths": None, "path_changes": 0,
        "trace_fusion": None,
        "hubs_v4": None, "hubs_v6": None,
        "trace_truncated": False,
        "_trace_method": None,
        "_iperf_upload": None, "_iperf_download": None,
        "_iperf_idle_rtt": None, "_iperf_loaded_rtt": None,
        "_speedtest_upload": None, "_speedtest_download": None,
        "_v6_warn": None,
        "probe_errors": {},
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # ── Trace section ─────────────────────────────────────────────────
        if trace_fusion:
            try:
                hubs, fusion_meta = trace_fusion_mod.run(host, cycles=cycles, prefer_tcp=prefer_tcp)
                result["_trace_method"] = "trace-fusion"
                result["trace_fusion"] = fusion_meta
            except RuntimeError as e:
                result["probe_errors"]["v4_trace"] = f"trace fusion: {e}"
                return result

        elif compare_v6:
            v6_host = None
            try:
                v6_info = socket.getaddrinfo(host, None, socket.AF_INET6)
                v6_host = v6_info[0][4][0]
            except socket.gaierror:
                result["_v6_warn"] = "IPv6 resolution failed — showing IPv4 only"

            def _do_v4() -> tuple[list[dict], str]:
                return _trace(host, cycles, prefer_tcp=prefer_tcp)

            def _do_v6() -> Optional[list[dict]]:
                if v6_host is None:
                    return None
                try:
                    v6_hubs, _ = _trace(v6_host, cycles)
                    return v6_hubs
                except Exception:
                    return None

            # The outer wait is a safety net only — it must cover the
            # worst-case inner subprocess budgets (mtr attempt, then Paris,
            # then up to two traceroute passes under prefer_tcp), or it fires
            # first and discards the partial path the prober recovered.
            trace_timeout = (
                (cycles * 4 + 30)
                + paris._PER_RUN_TIMEOUT * min(cycles, paris.PARIS_MAX_PROBES)
                + 2 * (30 * min(cycles, mtr.TRACEROUTE_MAX_PROBES) + 15)
                + 15
            )
            fut_v4 = executor.submit(_do_v4)
            fut_v6 = executor.submit(_do_v6)

            try:
                hubs, method = fut_v4.result(timeout=trace_timeout)
            except mtr.TraceTimeout as exc:
                hubs, method = exc.hubs, "traceroute"
                result["probe_errors"]["v4_trace"] = "timed out (partial path shown)"
                result["trace_truncated"] = True
            except concurrent.futures.TimeoutError:
                result["probe_errors"]["v4_trace"] = "timed out"
                return result
            except RuntimeError as exc:
                result["probe_errors"]["v4_trace"] = str(exc)
                return result

            result["_trace_method"] = method
            result["hubs_v4"] = hubs
            try:
                result["hubs_v6"] = fut_v6.result(timeout=trace_timeout)
            except Exception:
                result["hubs_v6"] = None

        elif ecmp_passes > 1 and mtr.available():
            try:
                all_passes = mtr.run(host, cycles=cycles, passes=ecmp_passes)
                comparison = mtr._compare_as_paths(all_passes)
                result["ecmp_paths"] = comparison["ecmp_paths"]
                result["path_changes"] = comparison["path_changes"]
                hubs = all_passes[0] if all_passes else []
                result["_trace_method"] = "mtr"
            except mtr.MtrPermissionError:
                try:
                    hubs, method = _fallback_trace(host, cycles, prefer_tcp=prefer_tcp)
                except mtr.TraceTimeout as exc:
                    hubs, method = exc.hubs, "traceroute"
                    result["probe_errors"]["v4_trace"] = "timed out (partial path shown)"
                    result["trace_truncated"] = True
                result["_trace_method"] = method
            except RuntimeError as e:
                result["probe_errors"]["v4_trace"] = str(e)
                return result

        else:
            try:
                hubs, method = _trace(host, cycles, prefer_tcp=prefer_tcp)
                result["_trace_method"] = method
            except mtr.TraceTimeout as exc:
                hubs = exc.hubs
                result["_trace_method"] = "traceroute"
                result["probe_errors"]["v4_trace"] = "timed out (partial path shown)"
                result["trace_truncated"] = True
            except RuntimeError as e:
                result["probe_errors"]["v4_trace"] = str(e)
                return result

        result["as_path"] = _extract_as_path(hubs)
        result["hubs"] = hubs

        if result["_trace_method"] == "trace-fusion":
            result["probe_count"] = min(cycles, trace_fusion_mod.MAX_FUSION_PROBES)
        elif result["_trace_method"] == "traceroute":
            result["probe_count"] = min(cycles, mtr.TRACEROUTE_MAX_PROBES)
        elif result["_trace_method"] in paris.SUPPORTED_BINARIES:
            result["probe_count"] = min(cycles, paris.PARIS_MAX_PROBES)

        for _h in reversed(hubs):
            if _h.get("host") not in ("???", None, "") and _h.get("StDev") is not None:
                result["jitter_ms"] = round(_h["StDev"] or 0.0, 2)
                break

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

        # ── Concurrent independent probes ─────────────────────────────────
        name_for_dns = service_host or host
        fut_pmtu = executor.submit(pmtu_mod.probe, host)
        fut_dns  = executor.submit(dns_mod.measure, name_for_dns)
        fut_edge = executor.submit(edge_mod.measure, service_host or host, host if service_host else None)
        fut_geo  = executor.submit(geo_mod.analyze_path, hubs)
        fut_tcp  = executor.submit(latency_mod.measure_tcp_connect, host)
        fut_tls  = executor.submit(latency_mod.measure_tls_handshake, service_host or host)
        fut_rum  = executor.submit(_fetch_rum, target_asn, cf_token)

        try:
            result["pmtu"] = fut_pmtu.result(timeout=30)
        except Exception:
            result["probe_errors"]["pmtu"] = "timeout"

        try:
            result["dns"] = fut_dns.result(timeout=10)
        except Exception:
            result["probe_errors"]["dns"] = "timeout"

        try:
            result["http_edge"] = fut_edge.result(timeout=20)
        except Exception:
            result["probe_errors"]["http_edge"] = "timeout"

        try:
            result["geo_path"] = fut_geo.result(timeout=15)
        except Exception:
            result["probe_errors"]["geo_path"] = "timeout"

        try:
            result["tcp_connect_ms"] = fut_tcp.result(timeout=15)
        except Exception:
            result["probe_errors"]["tcp_connect"] = "timeout"

        try:
            result["tls_handshake_ms"] = fut_tls.result(timeout=15)
        except Exception:
            result["probe_errors"]["tls_handshake"] = "timeout"

        try:
            result["rum"] = fut_rum.result(timeout=15)
        except Exception:
            result["rum"] = None

        if skip_throughput:
            result["verdict"] = diagnose(result)
            return result

        # ── Throughput with concurrent ping ───────────────────────────────
        if iperf_mod.available():
            idle_rtt = result["last_rtt_ms"]
            result["_iperf_idle_rtt"] = idle_rtt
            fut_ping = executor.submit(_run_ping_probe_sync, host, duration)
            try:
                upload, download = iperf_mod.run_bidirectional(host, port, duration)
                fut_ping.cancel()
                try:
                    loaded_rtt = fut_ping.result(timeout=duration + 10)
                except Exception:
                    loaded_rtt = None
                result["_iperf_loaded_rtt"] = loaded_rtt
                if idle_rtt is not None and loaded_rtt is not None:
                    result["bufferbloat_ms"] = round(loaded_rtt - idle_rtt, 1)
                result["download_mbps"] = download.get("recv_bps", download.get("bps", 0)) / 1e6
                result["upload_mbps"] = upload.get("bps", 0) / 1e6
                result["_iperf_upload"] = upload
                result["_iperf_download"] = download
            except RuntimeError as e:
                fut_ping.cancel()
                try:
                    fut_ping.result(timeout=5)
                except Exception:
                    pass
                result["probe_errors"]["iperf3"] = str(e)
            result["verdict"] = diagnose(result)
            return result

        # ── Speedtest fallback ────────────────────────────────────────────
        # This measures user → Cloudflare, NOT user → target ASN.
        st_result = speedtest.run(duration=duration)
        upload, download = speedtest.extract_stats(st_result)
        if download is not None:
            result["download_mbps"] = download.get("recv_bps", download.get("bps", 0)) / 1e6
            result["_speedtest_download"] = download
        if upload is not None:
            result["upload_mbps"] = upload.get("bps", 0) / 1e6
            result["_speedtest_upload"] = upload
        st_errors = st_result.get("errors", {})
        if st_errors:
            result["probe_errors"]["speedtest"] = "; ".join(
                f"{d}: {e}" for d, e in st_errors.items()
            )

        result["verdict"] = diagnose(result)
        return result


def _run_test(host: str, port: int, server_meta: dict, target_asn: str,
              cycles: int, duration: int, skip_throughput: bool,
              cf_token: Optional[str] = None, show_server_heading: bool = True,
              json_mode: bool = False, prefer_tcp: bool = False,
              ecmp_passes: int = 1, compare_v6: bool = False,
              service_host: Optional[str] = None, trace_fusion: bool = False,
              _measure_impl=None) -> dict:
    """Run trace + optional throughput test. Returns enriched result dict."""
    measure = _measure_impl or _measure
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
            result = measure(host, port, target_asn, cycles, duration, skip_throughput, cf_token,
                             prefer_tcp=prefer_tcp, ecmp_passes=ecmp_passes, compare_v6=compare_v6,
                             service_host=service_host, trace_fusion=trace_fusion)
    else:
        result = measure(host, port, target_asn, cycles, duration, skip_throughput, cf_token,
                         prefer_tcp=prefer_tcp, ecmp_passes=ecmp_passes, compare_v6=compare_v6,
                         service_host=service_host, trace_fusion=trace_fusion)

    if result.get("probe_errors", {}).get("v4_trace") and not result.get("hubs"):
        if not json_mode:
            display.error(f"trace: {result['probe_errors']['v4_trace']}")
        return result

    if result.get("_trace_method") == "traceroute" and not json_mode:
        display.console.print("  [dim](mtr unavailable — using traceroute + Cymru ASN lookup)[/dim]\n")
    elif result.get("_trace_method") == "trace-fusion" and not json_mode:
        methods = [
            item["name"]
            for item in (result.get("trace_fusion") or {}).get("methods", [])
            if item.get("status") == "ok"
        ]
        suffix = f": {', '.join(methods)}" if methods else ""
        display.console.print(f"  [dim](trace fusion{suffix})[/dim]\n")
    elif result.get("_trace_method") in paris.SUPPORTED_BINARIES and not json_mode:
        display.console.print(
            f"  [dim](mtr unavailable — using {result['_trace_method']} Paris traceroute"
            " + Cymru ASN lookup)[/dim]\n"
        )

    answer_shown = False
    if not json_mode:
        answer = explain_mod.build_operator_answer(destination=host, result=result)
        answer_shown = display.operator_answer(answer)

    if not json_mode:
        truncated = result.get("trace_truncated", False)
        if compare_v6 and result.get("hubs_v6") is not None:
            display.dual_stack_columns(result["hubs_v4"], result["hubs_v6"], target_asn,
                                       truncated=truncated)
        else:
            if compare_v6 and result.get("_v6_warn"):
                display.warn(result["_v6_warn"])
            display.path_table(result["hubs"], target_asn, truncated=truncated)
        display.as_path_summary(result["hubs"])
        display.edge_metrics(result)

    rum_data = result.get("rum")

    if skip_throughput:
        if rum_data and not json_mode:
            display.rum_only_panel(rum_data, target_asn)
        if not json_mode and not answer_shown:
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
                if not answer_shown:
                    display.verdict_panel(result["verdict"])
        else:
            if not json_mode:
                display.warn(f"iperf3 to {host}:{port} failed: {result.get('probe_errors', {}).get('iperf3', 'unknown error')}")
                if rum_data:
                    display.rum_only_panel(rum_data, target_asn)
                if not answer_shown:
                    display.verdict_panel(result["verdict"])
        return result

    # iperf3 not installed path
    if result.get("_speedtest_download") is not None:
        if not json_mode:
            display.throughput_and_rum(
                result["_speedtest_upload"], result["_speedtest_download"],
                rum=rum_data, server="speed.cloudflare.com (baseline — not cross-ASN)"
            )
    elif result.get("probe_errors", {}).get("speedtest") and not json_mode:
        display.warn(f"speedtest: {result['probe_errors']['speedtest']}")
        if rum_data:
            display.rum_only_panel(rum_data, target_asn)

    if not json_mode and not answer_shown:
        display.verdict_panel(result["verdict"])
    return result
