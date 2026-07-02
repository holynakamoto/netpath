"""Paris traceroute fallback via dublin-traceroute or scamper.

Paris probers hold the flow identifier constant across probes so every packet
to a given TTL follows the same ECMP path, keeping load-balancer route
diversity out of the per-hop loss and RTT figures. Strictly best-effort: any
failure (binary absent, permission denied, timeout, unparseable output)
raises ParisError so callers can fall through silently to the system
traceroute.
"""

import json
import os
import statistics
import shutil
import subprocess
import tempfile

from .mtr import _enrich_names, _percentile
from .types import Hub

PARIS_MAX_PROBES = 5
SUPPORTED_BINARIES = ("dublin-traceroute", "scamper")
_MAX_TTL = 30
_PER_RUN_TIMEOUT = 45


class ParisError(RuntimeError):
    pass


def detect() -> "str | None":
    for binary in SUPPORTED_BINARIES:
        if shutil.which(binary) is not None:
            return binary
    return None


def available() -> bool:
    return detect() is not None


def _build_hub(ttl: int, host: "str | None", rtts: "list[float]", probes: int) -> Hub:
    if not rtts:
        return {
            "count": ttl, "host": host or "???", "ASN": "AS???",
            "Loss%": 100.0, "Avg": 0.0, "Best": 0.0, "Wrst": 0.0, "StDev": 0.0,
            "p50": None, "p95": None, "p99": None,
        }
    loss_pct = round(max(probes - len(rtts), 0) / probes * 100.0, 1) if probes > 0 else 0.0
    sorted_rtts = sorted(rtts)
    return {
        "count": ttl,
        "host": host or "???",
        "ASN": "AS???",
        "Loss%": loss_pct,
        "Avg": round(sum(rtts) / len(rtts), 2),
        "Best": round(min(rtts), 2),
        "Wrst": round(max(rtts), 2),
        "StDev": round(statistics.stdev(rtts) if len(rtts) > 1 else 0.0, 2),
        "p50": round(_percentile(sorted_rtts, 50), 2),
        "p95": round(_percentile(sorted_rtts, 95), 2),
        "p99": round(_percentile(sorted_rtts, 99), 2),
    }


def _parse_dublin_outputs(payloads: "list[dict]", probes: int) -> "list[Hub]":
    """
    Aggregate per-TTL samples from one or more dublin-traceroute JSON payloads.
    Each payload is one single-flow run (--npaths=1), so every sample for a TTL
    shares the same flow identifier and therefore the same path.
    """
    samples: "dict[int, dict]" = {}
    for payload in payloads:
        flows = payload.get("flows") or {}
        for hops in flows.values():
            for idx, hop in enumerate(hops or []):
                if not isinstance(hop, dict):
                    continue
                sent = hop.get("sent") or {}
                ttl = (sent.get("ip") or {}).get("ttl") or idx + 1
                entry = samples.setdefault(ttl, {"host": None, "rtts": []})
                received = hop.get("received") or {}
                src = (received.get("ip") or {}).get("src")
                if entry["host"] is None and src:
                    entry["host"] = src
                rtt_usec = hop.get("rtt_usec")
                if rtt_usec:  # 0 / None means this probe got no reply
                    entry["rtts"].append(rtt_usec / 1000.0)
    if not samples:
        raise ParisError("no hops in dublin-traceroute output")
    return [_build_hub(ttl, samples[ttl]["host"], samples[ttl]["rtts"], probes)
            for ttl in sorted(samples)]


def _parse_scamper_output(output: str) -> "list[Hub]":
    """
    Parse scamper's line-delimited JSON (-O json) trace output.
    Replies are grouped by probe_ttl; a TTL with no reply entries between 1 and
    hop_count is an unresponsive hop.
    """
    trace = None
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "trace":
            trace = obj
            break
    if trace is None:
        raise ParisError("no trace object in scamper output")

    attempts = trace.get("attempts") or 1
    samples: "dict[int, dict]" = {}
    for hop in trace.get("hops") or []:
        if not isinstance(hop, dict):
            continue
        ttl = hop.get("probe_ttl")
        if not isinstance(ttl, int):
            continue
        entry = samples.setdefault(ttl, {"host": None, "rtts": []})
        if entry["host"] is None and hop.get("addr"):
            entry["host"] = hop["addr"]
        rtt = hop.get("rtt")
        if isinstance(rtt, (int, float)):
            entry["rtts"].append(float(rtt))
    if not samples:
        raise ParisError("no hops in scamper output")

    max_ttl = trace.get("hop_count") or max(samples)
    hubs = []
    for ttl in range(1, max_ttl + 1):
        entry = samples.get(ttl, {"host": None, "rtts": []})
        hubs.append(_build_hub(ttl, entry["host"], entry["rtts"], attempts))
    return hubs


def _run_dublin(host: str, probes: int) -> "list[Hub]":
    """
    Run dublin-traceroute once per probe with a single pinned flow (--npaths=1)
    and aggregate the runs, so every sample per TTL follows the same path.
    """
    payloads = []
    with tempfile.TemporaryDirectory() as tmpdir:
        outfile = os.path.join(tmpdir, "trace.json")
        for _ in range(probes):
            cmd = ["dublin-traceroute", "--npaths=1", f"--max-ttl={_MAX_TTL}",
                   f"--output-file={outfile}", host]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=_PER_RUN_TIMEOUT)
            if result.returncode != 0:
                raise ParisError(result.stderr.strip() or "dublin-traceroute failed")
            try:
                with open(outfile) as f:
                    payloads.append(json.load(f))
            except (OSError, json.JSONDecodeError) as e:
                raise ParisError(f"unreadable dublin-traceroute output: {e}")
    return _parse_dublin_outputs(payloads, probes)


def _run_scamper(host: str, probes: int) -> "list[Hub]":
    cmd = ["scamper", "-O", "json", "-I",
           f"trace -P icmp-paris -q {probes} -Q -w 1 -m {_MAX_TTL} {host}"]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=_PER_RUN_TIMEOUT * probes)
    if result.returncode != 0:
        raise ParisError(result.stderr.strip() or "scamper failed")
    return _parse_scamper_output(result.stdout)


def run(host: str, probes: int = 5, binary: "str | None" = None) -> "list[Hub]":
    """
    Run the first available Paris prober against host and return Hub-shaped
    hop dicts. Raises ParisError on any failure so the caller can fall through
    silently to the system traceroute.
    """
    if binary is None:
        binary = detect()
    if binary is None:
        raise ParisError("no Paris-capable prober installed")
    effective_probes = max(1, min(probes, PARIS_MAX_PROBES))
    try:
        if binary == "dublin-traceroute":
            hubs = _run_dublin(host, effective_probes)
        elif binary == "scamper":
            hubs = _run_scamper(host, effective_probes)
        else:
            raise ParisError(f"unsupported Paris prober: {binary}")
    except ParisError:
        raise
    except subprocess.TimeoutExpired:
        raise ParisError(f"{binary} timed out")
    except Exception as e:  # permission denied, binary vanished, OS errors
        raise ParisError(str(e))
    if not hubs:
        raise ParisError(f"{binary} produced no hops")
    _enrich_names(hubs)
    return hubs
