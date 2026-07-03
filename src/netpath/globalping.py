"""Globalping integration: probe inventory, measurement scheduling,
result polling, result parsing, and coverage by country.

No authentication is required. An optional Bearer token raises the
per-IP rate limit tier."""

from __future__ import annotations


import statistics
import time

import requests

from .utils import _with_retry

_BASE = "https://api.globalping.io/v1"
_PROBE_LIMIT = 3
_PING_PACKETS = 16  # API per-measurement maximum; enough for loss/jitter stats
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 60


def _hdr(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def get_public_ip() -> str | None:
    """Return the caller's public IPv4 via ipify. Returns None on failure."""
    try:
        r = _with_retry(lambda: requests.get(
            "https://api.ipify.org?format=json", timeout=10
        ))
        r.raise_for_status()
        return r.json().get("ip")
    except Exception:
        return None


class GlobalpingAuthError(RuntimeError):
    """The Globalping API rejected the request as unauthorized (HTTP 401/403)."""


def fetch_probes(token: str | None = None) -> list[dict]:
    """Return all currently connected Globalping probes.

    Raises GlobalpingAuthError on HTTP 401/403 (rejected token) so callers can
    report an authentication problem instead of missing coverage. Returns []
    on any other failure so remote measurements are skipped gracefully."""
    try:
        r = _with_retry(lambda: requests.get(
            f"{_BASE}/probes",
            headers=_hdr(token),
            timeout=30,
        ))
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in (401, 403):
            raise GlobalpingAuthError(
                f"Globalping probe inventory request rejected (HTTP {e.response.status_code})"
            ) from e
        return []
    except Exception:
        return []


def count_probes_by_asn(probes: list[dict]) -> dict[int, int]:
    """Build {asn: connected probe count} from a probe inventory."""
    counts: dict[int, int] = {}
    for probe in probes:
        asn = probe.get("location", {}).get("asn")
        if isinstance(asn, int):
            counts[asn] = counts.get(asn, 0) + 1
    return counts


def coverage_by_country(probes: list[dict]) -> dict[str, int]:
    """Build {country_code: connected probe count} from a probe inventory."""
    coverage: dict[str, int] = {}
    for probe in probes:
        cc = probe.get("location", {}).get("country", "")
        if cc:
            coverage[cc] = coverage.get(cc, 0) + 1
    return coverage


def schedule_measurements(
    asn: str,
    target_ip: str,
    user_ip: str,
    token: str | None = None,
) -> dict[str, str]:
    """
    Schedule one ping (to target_ip) and one mtr (to user_ip) from probes
    inside the given ASN.

    Returns {"ping": measurement_id, "mtr": measurement_id}.
    Raises requests.HTTPError on API failure (422 = no matching probes,
    429 = rate limit exhausted, 401 = invalid token).
    """
    asn_num = str(asn).lstrip("ASas")
    locations = [{"magic": f"AS{asn_num}"}]

    r = _with_retry(lambda: requests.post(
        f"{_BASE}/measurements",
        json={
            "type": "ping",
            "target": target_ip,
            "locations": locations,
            "limit": _PROBE_LIMIT,
            "measurementOptions": {"packets": _PING_PACKETS},
        },
        headers=_hdr(token),
        timeout=30,
    ))
    r.raise_for_status()
    ping_id = r.json()["id"]

    r = _with_retry(lambda: requests.post(
        f"{_BASE}/measurements",
        json={
            "type": "mtr",
            "target": user_ip,
            "locations": locations,
            "limit": _PROBE_LIMIT,
        },
        headers=_hdr(token),
        timeout=30,
    ))
    r.raise_for_status()
    mtr_id = r.json()["id"]

    return {"ping": ping_id, "mtr": mtr_id}


def schedule_path_measurements(
    source_asn: str,
    target_ip: str,
    token: str | None = None,
) -> dict[str, str]:
    """
    Schedule ping + mtr from probes inside source_asn toward target_ip.

    This is used by the aspath command to compare candidate paths between two
    ASNs as seen from Globalping probes in the source network.
    """
    asn_num = str(source_asn).lstrip("ASas")
    locations = [{"magic": f"AS{asn_num}"}]

    r = _with_retry(lambda: requests.post(
        f"{_BASE}/measurements",
        json={
            "type": "ping",
            "target": target_ip,
            "locations": locations,
            "limit": _PROBE_LIMIT,
            "measurementOptions": {"packets": _PING_PACKETS},
        },
        headers=_hdr(token),
        timeout=30,
    ))
    r.raise_for_status()
    ping_id = r.json()["id"]

    r = _with_retry(lambda: requests.post(
        f"{_BASE}/measurements",
        json={
            "type": "mtr",
            "target": target_ip,
            "locations": locations,
            "limit": _PROBE_LIMIT,
        },
        headers=_hdr(token),
        timeout=30,
    ))
    r.raise_for_status()
    mtr_id = r.json()["id"]

    return {"ping": ping_id, "mtr": mtr_id}


def poll_until_done(
    measurement_ids: list[str],
    token: str | None = None,
    timeout: int = _POLL_TIMEOUT,
) -> dict[str, str]:
    """
    Poll measurements until all leave "in-progress" or timeout expires.

    Returns {measurement_id: status}.
    Measurements that don't finish in time get status "timed_out".
    """
    hdrs = _hdr(token)
    deadline = time.monotonic() + timeout
    pending = set(measurement_ids)
    final: dict[str, str] = {}

    while pending:
        for mid in list(pending):
            try:
                r = _with_retry(lambda mid=mid: requests.get(
                    f"{_BASE}/measurements/{mid}",
                    headers=hdrs,
                    timeout=15,
                ))
                r.raise_for_status()
                status = r.json().get("status", "")
                if status and status != "in-progress":
                    final[mid] = status
                    pending.discard(mid)
            except Exception:
                pass
        if pending:
            if time.monotonic() >= deadline:
                break
            time.sleep(_POLL_INTERVAL)

    for mid in pending:
        final[mid] = "timed_out"
    return final


def fetch_results(measurement_id: str, token: str | None = None) -> list[dict]:
    """Fetch per-probe results for a measurement. Returns [] on failure."""
    try:
        r = _with_retry(lambda: requests.get(
            f"{_BASE}/measurements/{measurement_id}",
            headers=_hdr(token),
            timeout=30,
        ))
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:
        return []


def parse_ping_rtt(results: list[dict]) -> dict[str, float] | None:
    """
    Extract min/avg/max RTT (ms) from Globalping ping results, aggregated
    across probes. Returns None if no probe produced valid stats.
    """
    mins: list[float] = []
    avgs: list[float] = []
    maxs: list[float] = []
    for item in results:
        stats = item.get("result", {}).get("stats", {})
        lo, mid, hi = stats.get("min"), stats.get("avg"), stats.get("max")
        if all(isinstance(v, (int, float)) for v in (lo, mid, hi)):
            mins.append(float(lo))
            avgs.append(float(mid))
            maxs.append(float(hi))
    if not mins:
        return None
    return {
        "min": round(min(mins), 2),
        "avg": round(sum(avgs) / len(avgs), 2),
        "max": round(max(maxs), 2),
    }


def parse_ping_stats(results: list[dict]) -> dict | None:
    """
    Extract aggregate loss and jitter from Globalping ping results.

    Loss aggregates dropped/sent packet counts across probes. Jitter is
    computed per probe as the standard deviation of its packet timings and
    aggregated across probes via the median (robust to one bad probe).

    Returns {"loss_pct": float, "jitter_ms": float, "packets": int} where
    "packets" is the number of received timings the jitter rests on; the
    loss_pct / jitter_ms keys are present only when computable. Returns
    None if no probe produced usable data.
    """
    total_sent = 0
    total_dropped = 0
    received = 0
    jitters: list[float] = []
    for item in results:
        res = item.get("result") or {}
        if not isinstance(res, dict):
            continue
        stats = res.get("stats") or {}
        total, drop = stats.get("total"), stats.get("drop")
        if (isinstance(total, (int, float)) and isinstance(drop, (int, float))
                and total > 0):
            total_sent += int(total)
            total_dropped += int(drop)
        timings = res.get("timings") or []
        rtts = [
            t.get("rtt") for t in timings
            if isinstance(t, dict) and isinstance(t.get("rtt"), (int, float))
        ]
        received += len(rtts)
        if len(rtts) >= 2:
            jitters.append(statistics.stdev(rtts))
    if total_sent == 0 and received == 0:
        return None
    parsed: dict = {"packets": received}
    if total_sent > 0:
        parsed["loss_pct"] = round(100.0 * total_dropped / total_sent, 2)
    if jitters:
        parsed["jitter_ms"] = round(statistics.median(jitters), 2)
    return parsed


def _hostname_domain(hostname: str | None) -> str:
    """Reduce a hop hostname to its registered domain, e.g.
    'be3084.ccr41.jfk02.atlas.cogentco.com' -> 'cogentco.com'."""
    if not hostname or "." not in hostname:
        return ""
    parts = hostname.rstrip(".").split(".")
    return ".".join(parts[-2:])


def parse_mtr_as_path(results: list[dict]) -> list[str]:
    """
    Derive a deduplicated AS-hop sequence from Globalping mtr results.

    Each hop carries its own `asn` list, so no external IP-to-ASN lookup
    is needed. Hostnames provide a readable name per AS where available.
    Returns [] if no probe produced a usable path.
    """
    for item in results:
        hops = item.get("result", {}).get("hops", [])
        path_asns: list[int] = []   # deduplicate on bare ASN number
        path_labels: list[str] = []  # display strings like "AS1234 (name)"
        for hop in hops:
            asns = hop.get("asn") or []
            if not asns:
                continue
            asn = asns[0]
            if path_asns and path_asns[-1] == asn:
                continue
            domain = _hostname_domain(hop.get("resolvedHostname"))
            label = f"AS{asn} ({domain})" if domain else f"AS{asn}"
            path_asns.append(asn)
            path_labels.append(label)
        if path_labels:
            return path_labels
    return []


def _hop_avg_ms(hop: dict) -> float | None:
    stats = hop.get("stats") or {}
    for key in ("avg", "mean"):
        val = stats.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    timings = hop.get("timings") or []
    rtts = [
        t.get("rtt") for t in timings
        if isinstance(t, dict) and isinstance(t.get("rtt"), (int, float))
    ]
    if rtts:
        return float(sum(rtts) / len(rtts))
    return None


def _probe_label(item: dict) -> str:
    probe = item.get("probe") or {}
    location = probe.get("location") or item.get("location") or {}
    city = location.get("city")
    country = location.get("country")
    network = location.get("network")
    parts = [p for p in (city, country, network) if p]
    return ", ".join(parts) if parts else "Globalping probe"


def parse_mtr_path_candidates(results: list[dict]) -> list[dict]:
    """
    Return ranked AS-path candidates from Globalping mtr results.

    Each candidate has: path, as_hops, probe, rtt_ms. Consecutive duplicate ASNs
    are collapsed. Multiple probes can reveal different policy paths from the
    same source ASN; callers can rank these alongside ping loss/jitter.
    """
    candidates: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for item in results:
        hops = item.get("result", {}).get("hops", [])
        path_asns: list[int] = []
        path_labels: list[str] = []
        final_rtt = None
        for hop in hops:
            hop_rtt = _hop_avg_ms(hop)
            if hop_rtt is not None:
                final_rtt = hop_rtt
            asns = hop.get("asn") or []
            if not asns:
                continue
            asn = asns[0]
            if path_asns and path_asns[-1] == asn:
                continue
            domain = _hostname_domain(hop.get("resolvedHostname"))
            label = f"AS{asn} ({domain})" if domain else f"AS{asn}"
            path_asns.append(asn)
            path_labels.append(label)
        key = tuple(path_labels)
        if not path_labels or key in seen:
            continue
        seen.add(key)
        candidates.append({
            "path": path_labels,
            "as_hops": len(path_labels),
            "probe": _probe_label(item),
            "rtt_ms": round(final_rtt, 2) if final_rtt is not None else None,
        })
    candidates.sort(key=lambda c: (
        c["rtt_ms"] is None,
        c["rtt_ms"] if c["rtt_ms"] is not None else 0,
        c["as_hops"],
    ))
    return candidates
