import json
import math
import re
import shutil
import statistics
import subprocess

from .asn import cymru_bulk_lookup


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


def available() -> bool:
    return shutil.which("mtr") is not None


_SOCKET_ERR_MARKERS = ("failure to open", "operation not permitted", "permission denied")
_SUID_REFUSED = "should not run suid"


class MtrPermissionError(RuntimeError):
    pass


def run(host: str, cycles: int = 10) -> list[dict]:
    """
    Run mtr in JSON report mode. Raises MtrPermissionError on raw socket
    denial so the caller can fall back to traceroute.
    """
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
        return hubs
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse mtr output: {e}")


# ── traceroute fallback ───────────────────────────────────────────────────────

def _parse_traceroute_output(output: str) -> list[dict]:
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


def _run_traceroute_cmd(host: str, tcp: bool = False) -> list[dict]:
    """
    Run one traceroute pass.
    Parameters tuned for fast failure: 1s wait, 15 hops, 2 probes → 30s worst case.
    tcp=True uses TCP SYN to port 443 (requires pcap — may fail on macOS without privs).
    """
    cmd = ["/usr/sbin/traceroute", "-n", "-w", "1", "-m", "15", "-q", "2"]
    if tcp:
        cmd += ["-P", "tcp", "-p", "443"]
    cmd.append(host)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError("traceroute timed out")

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "traceroute failed")

    return _parse_traceroute_output(result.stdout)


def run_traceroute(host: str, probes: int = 5) -> list[dict]:
    """
    Fallback when mtr lacks raw socket access.
    Tries UDP first; if all hops are filtered, retries with TCP SYN (port 443).
    TCP requires pcap — if that also fails (common on macOS), returns the
    filtered UDP result rather than raising an error.
    """
    hubs = _run_traceroute_cmd(host, tcp=False)

    if _all_stars(hubs):
        try:
            tcp_hubs = _run_traceroute_cmd(host, tcp=True)
            if not _all_stars(tcp_hubs):
                hubs = tcp_hubs
        except RuntimeError:
            pass  # pcap unavailable or path still filtered — keep UDP result

    ips = [h["host"] for h in hubs if h["host"] != "???"]
    if ips:
        ip_asn = cymru_bulk_lookup(ips)
        for hub in hubs:
            if hub["host"] != "???":
                hub["ASN"] = ip_asn.get(hub["host"], "AS???")

    return hubs
