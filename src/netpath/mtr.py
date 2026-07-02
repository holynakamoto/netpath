from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import subprocess

from .asn import cymru_bulk_lookup_rich
from .display import clean_asn_name
from .types import Hub


def _percentile(sorted_data: list, p: float) -> float:
    """Nearest-rank percentile from a pre-sorted list. p is 0–100."""
    n = len(sorted_data)
    if n == 0:
        return 0.0
    idx = min(math.ceil(p / 100.0 * n) - 1, n - 1)
    return sorted_data[max(0, idx)]


def _enrich_percentiles(hub: dict) -> None:
    """Add p50, p95, p99 to a hub dict using Avg+z*StDev estimation."""
    if hub.get("Loss%", 0.0) >= 100.0:
        hub["p50"] = None
        hub["p95"] = None
        hub["p99"] = None
        return
    avg = hub.get("Avg", 0.0)
    std = hub.get("StDev", 0.0)
    hub["p50"] = round(avg, 2)
    hub["p95"] = round(avg + 1.645 * std, 2)
    hub["p99"] = round(avg + 2.326 * std, 2)


def _enrich_names(hubs: list[dict]) -> None:
    """Batch-populate hub['asn_name'] from Cymru rich lookup. Silently skips on failure."""
    ips = [h.get("host", "") for h in hubs if h.get("host") not in ("???", "", None)]
    if not ips:
        return
    try:
        rich_info = cymru_bulk_lookup_rich(ips)
        for hub in hubs:
            ip = hub.get("host", "")
            if ip and ip not in ("???", "", None) and ip in rich_info:
                raw_name = rich_info[ip].get("name", "")
                if raw_name:
                    hub["asn_name"] = clean_asn_name(raw_name)
                if hub.get("ASN", "AS???") == "AS???":
                    hub["ASN"] = rich_info[ip].get("asn", "AS???")
    except Exception:
        pass


def available() -> bool:
    return shutil.which("mtr") is not None


_SOCKET_ERR_MARKERS = ("failure to open", "operation not permitted", "permission denied")
_SUID_REFUSED = "should not run suid"


class MtrPermissionError(RuntimeError):
    pass


class TraceTimeout(RuntimeError):
    """A trace pass exceeded its time budget but produced usable partial output.

    hubs holds the hops parsed from the output collected before the kill.
    """

    def __init__(self, message: str, hubs: "list[Hub]"):
        super().__init__(message)
        self.hubs = hubs


def run(host: str, cycles: int = 10, passes: int = 1) -> "list[Hub] | list[list[Hub]]":
    """
    Run mtr in JSON report mode. Raises MtrPermissionError on raw socket denial.
    When passes=1 (default): returns list[dict].
    When passes>1: runs mtr that many times sequentially and returns list[list[dict]].
    """
    def _single_pass() -> list[dict]:
        cmd = ["mtr", "--json", "--report", f"--report-cycles={cycles}", "--aslookup", host]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=cycles * 4 + 30)
        except subprocess.TimeoutExpired:
            raise RuntimeError("mtr timed out")
        if result.returncode != 0:
            stderr_lower = result.stderr.strip().lower()
            if _SUID_REFUSED in stderr_lower or any(m in stderr_lower for m in _SOCKET_ERR_MARKERS):
                raise MtrPermissionError(result.stderr.strip())
            raise RuntimeError(result.stderr.strip() or "mtr exited non-zero")
        try:
            data = json.loads(result.stdout)
            hubs = data["report"]["hubs"]
            for hub in hubs:
                _enrich_percentiles(hub)
            _enrich_names(hubs)
            return hubs
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Failed to parse mtr output: {e}")

    if passes <= 1:
        return _single_pass()
    return [_single_pass() for _ in range(passes)]


def _compare_as_paths(all_passes: list[list[dict]]) -> dict:
    """
    Compare AS paths across multiple mtr passes.
    Returns {"ecmp_paths": int, "path_changes": int}.
    ecmp_paths: number of distinct AS-hop sequences across all passes.
    path_changes: number of consecutive pass pairs where the AS sequence differs.
    """
    if not all_passes:
        return {"ecmp_paths": 1, "path_changes": 0}

    def asn_sequence(hubs: list[dict]) -> tuple:
        by_count = {h.get("count"): h.get("ASN", "AS???") for h in hubs}
        if not by_count:
            return ()
        return tuple(by_count.get(i, "???") for i in range(1, max(by_count) + 1))

    sequences = [asn_sequence(hubs) for hubs in all_passes]
    ecmp_paths = len(set(sequences))
    path_changes = sum(1 for i in range(1, len(sequences)) if sequences[i] != sequences[i - 1])
    return {"ecmp_paths": ecmp_paths, "path_changes": path_changes}


# ── traceroute fallback ───────────────────────────────────────────────────────

def _parse_traceroute_output(output: str) -> "list[Hub]":
    hubs = []
    for line in output.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue

        m = re.match(r'^(\d+)\s+(.*)', line)
        if not m:
            continue

        hop_num = int(m.group(1))
        rest = m.group(2).strip()

        if re.match(r'^[\*\s]+$', rest):
            hubs.append({
                "count": hop_num, "host": "???", "ASN": "AS???",
                "Loss%": 100.0, "Avg": 0.0, "Best": 0.0, "Wrst": 0.0, "StDev": 0.0,
                "p50": None, "p95": None, "p99": None,
            })
            continue

        tokens = rest.split()
        host = tokens[0]

        rtts = []
        stars = 0
        i = 1
        while i < len(tokens):
            if tokens[i] == "*":
                stars += 1
                i += 1
            elif i + 1 < len(tokens) and tokens[i + 1] == "ms":
                try:
                    rtts.append(float(tokens[i]))
                except ValueError:
                    pass
                i += 2
            else:
                i += 1

        total = len(rtts) + stars
        loss_pct = (stars / total * 100.0) if total > 0 else 0.0

        if not rtts:
            hubs.append({
                "count": hop_num, "host": host, "ASN": "AS???",
                "Loss%": 100.0, "Avg": 0.0, "Best": 0.0, "Wrst": 0.0, "StDev": 0.0,
                "p50": None, "p95": None, "p99": None,
            })
            continue

        avg = sum(rtts) / len(rtts)
        sorted_rtts = sorted(rtts)
        hubs.append({
            "count": hop_num,
            "host": host,
            "ASN": "AS???",
            "Loss%": loss_pct,
            "Avg": round(avg, 2),
            "Best": round(min(rtts), 2),
            "Wrst": round(max(rtts), 2),
            "StDev": round(statistics.stdev(rtts) if len(rtts) > 1 else 0.0, 2),
            "p50": round(_percentile(sorted_rtts, 50), 2),
            "p95": round(_percentile(sorted_rtts, 95), 2),
            "p99": round(_percentile(sorted_rtts, 99), 2),
        })

    return hubs


def _all_stars(hubs: list[dict]) -> bool:
    return bool(hubs) and all(h["host"] == "???" for h in hubs)


TRACEROUTE_MAX_PROBES = 5


def _run_traceroute_cmd(host: str, tcp: bool = False, probes: int = 2) -> list[dict]:
    """
    Run one traceroute pass.
    Parameters tuned for bounded runtime: 1s wait, 30 hops, probes capped at
    TRACEROUTE_MAX_PROBES; the subprocess timeout scales with the probe count.
    tcp=True uses TCP SYN to port 443 (requires pcap — may fail on macOS without privs).
    """
    effective_probes = max(1, min(probes, TRACEROUTE_MAX_PROBES))
    cmd = ["/usr/sbin/traceroute", "-n", "-w", "1", "-m", "30", "-q", str(effective_probes)]
    if tcp:
        cmd += ["-P", "tcp", "-p", "443"]
    cmd.append(host)

    # Popen rather than subprocess.run: on timeout the partial stdout must be
    # harvested after the kill, and subprocess.run does not reliably attach it
    # to TimeoutExpired across Python 3.9-3.13.
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, errors="replace")
    try:
        stdout, stderr = proc.communicate(timeout=30 * effective_probes + 15)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            stdout, _ = proc.communicate()
        except Exception:
            stdout = None
        hubs: list[dict] = []
        if isinstance(stdout, str) and stdout:
            try:
                hubs = _parse_traceroute_output(stdout)
            except Exception:
                hubs = []
        if hubs and not _all_stars(hubs):
            raise TraceTimeout("traceroute timed out", hubs)
        raise RuntimeError("traceroute timed out")

    if proc.returncode != 0:
        raise RuntimeError((stderr or "").strip() or "traceroute failed")

    return _parse_traceroute_output(stdout or "")


def run_traceroute(host: str, probes: int = 5, prefer_tcp: bool = False) -> list[dict]:
    """
    Fallback when mtr lacks raw socket access.
    When prefer_tcp=True: tries TCP-443 first; falls back to UDP if TCP returns
    all-stars or raises (used for country-mode paths without an iperf3 server).
    When prefer_tcp=False (default): tries UDP first; if all hops are filtered,
    retries with TCP SYN (port 443). TCP requires pcap — if that also fails
    (common on macOS), returns the filtered UDP result rather than raising.
    A pass that times out with usable partial output raises TraceTimeout
    carrying the name-enriched hops; no further pass runs, since a full time
    budget has already been spent against a target that answers slowly.
    """
    try:
        if prefer_tcp:
            tcp_hubs = None
            try:
                tcp_hubs = _run_traceroute_cmd(host, tcp=True, probes=probes)
            except TraceTimeout:
                raise
            except RuntimeError:
                pass
            if tcp_hubs is not None and not _all_stars(tcp_hubs):
                hubs = tcp_hubs
            else:
                hubs = _run_traceroute_cmd(host, tcp=False, probes=probes)
        else:
            hubs = _run_traceroute_cmd(host, tcp=False, probes=probes)

            if _all_stars(hubs):
                try:
                    tcp_hubs = _run_traceroute_cmd(host, tcp=True, probes=probes)
                    if not _all_stars(tcp_hubs):
                        hubs = tcp_hubs
                except TraceTimeout:
                    raise
                except RuntimeError:
                    pass  # pcap unavailable or path still filtered — keep UDP result
    except TraceTimeout as e:
        _enrich_names(e.hubs)
        raise

    _enrich_names(hubs)
    return hubs
