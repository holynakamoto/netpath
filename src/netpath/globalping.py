"""Globalping integration: probe inventory, measurement scheduling,
result polling, result parsing, and coverage by country.

No authentication is required. An optional Bearer token raises the
per-IP rate limit tier."""

import time

import requests

from .utils import _with_retry

_BASE = "https://api.globalping.io/v1"
_PROBE_LIMIT = 3
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


def fetch_probes(token: str | None = None) -> list[dict]:
    """Return all currently connected Globalping probes. Returns [] on failure."""
    try:
        r = _with_retry(lambda: requests.get(
            f"{_BASE}/probes",
            headers=_hdr(token),
            timeout=30,
        ))
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
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
            "measurementOptions": {"packets": 3},
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
