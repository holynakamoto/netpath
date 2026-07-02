"""RIPE Atlas integration: probe discovery, credit budget check,
measurement scheduling, result polling, and result parsing."""

import time

import requests
from rich.progress import Progress, SpinnerColumn, TextColumn

from .asn import cymru_bulk_lookup_rich
from .display import clean_asn_name, console
from .utils import _with_retry

_BASE = "https://atlas.ripe.net/api/v4"
_ANCHORS_BASE = "https://atlas.ripe.net/api/v2"
_PING_CREDITS = 1
_TRACE_CREDITS = 10
_TERMINAL = {"stopped", "forced to stop", "no suitable probes", "failed", "denied"}


def _hdr(atlas_key: str) -> dict[str, str]:
    return {"Authorization": f"Key {atlas_key}"}


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


def find_probes_in_asn(asn: str, atlas_key: str) -> list[int]:
    """Return up to 3 connected probe IDs inside the given ASN. Returns [] on failure."""
    asn_num = asn.lstrip("ASas")
    try:
        r = _with_retry(lambda: requests.get(
            f"{_BASE}/probes/",
            params={"asn_v4": asn_num, "status": 1, "page_size": 3},
            headers=_hdr(atlas_key),
            timeout=15,
        ))
        r.raise_for_status()
        return [p["id"] for p in r.json().get("results", [])]
    except Exception:
        return []


def find_anchors_in_asn(asn: str, atlas_key: str) -> list[int]:
    """Return probe IDs for Atlas anchors inside the given ASN. Returns [] on failure."""
    asn_num = asn.lstrip("ASas")
    try:
        r = _with_retry(lambda: requests.get(
            f"{_ANCHORS_BASE}/anchors/",
            params={"asn_v4": asn_num, "status": 1, "page_size": 100},
            headers=_hdr(atlas_key),
            timeout=15,
        ))
        r.raise_for_status()
        return [a["probe"] for a in r.json().get("results", []) if a.get("probe")]
    except Exception:
        return []


def check_budget(
    probes_by_asn: dict[str, list[int]], atlas_key: str
) -> tuple[bool, int, int]:
    """
    Check if Atlas credits cover the planned sweep.

    Returns (sufficient, estimated_cost, current_balance).
    Raises on credit endpoint failure.
    """
    total_probes = sum(len(v) for v in probes_by_asn.values())
    cost = total_probes * (_PING_CREDITS + _TRACE_CREDITS)
    r = _with_retry(lambda: requests.get(
        f"{_BASE}/credits/",
        headers=_hdr(atlas_key),
        timeout=15,
    ))
    r.raise_for_status()
    balance = r.json().get("current_balance", 0)
    return cost <= balance, cost, balance


def schedule_measurements(
    probe_ids: list[int],
    target_ip: str,
    user_ip: str,
    atlas_key: str,
) -> dict[str, int]:
    """
    Schedule one ping (to target_ip) and one traceroute (to user_ip).

    Returns {"ping": measurement_id, "traceroute": measurement_id}.
    Raises requests.HTTPError on API failure.
    """
    hdrs = {**_hdr(atlas_key), "Content-Type": "application/json"}
    probe_spec = [{
        "type": "probes",
        "value": ",".join(str(p) for p in probe_ids),
        "requested": len(probe_ids),
    }]

    r = _with_retry(lambda: requests.post(
        f"{_BASE}/measurements/",
        json={
            "definitions": [{
                "type": "ping",
                "af": 4,
                "target": target_ip,
                "packets": 3,
                "is_oneoff": True,
                "description": f"netpath ping {target_ip}",
            }],
            "probes": probe_spec,
        },
        headers=hdrs,
        timeout=30,
    ))
    r.raise_for_status()
    ping_id = r.json()["measurements"][0]

    r = _with_retry(lambda: requests.post(
        f"{_BASE}/measurements/",
        json={
            "definitions": [{
                "type": "traceroute",
                "af": 4,
                "target": user_ip,
                "protocol": "TCP",
                "port": 80,
                "paris": 6,
                "is_oneoff": True,
                "description": f"netpath traceroute {user_ip}",
            }],
            "probes": probe_spec,
        },
        headers=hdrs,
        timeout=30,
    ))
    r.raise_for_status()
    trace_id = r.json()["measurements"][0]

    return {"ping": ping_id, "traceroute": trace_id}


def poll_until_done(
    measurement_ids: list[int],
    atlas_key: str,
    timeout: int = 600,
) -> dict[int, str]:
    """
    Poll measurements until all reach a terminal status or timeout expires.

    Returns {measurement_id: status_name}.
    Measurements that don't finish in time get status "timed_out".
    """
    hdrs = _hdr(atlas_key)
    deadline = time.monotonic() + timeout
    pending = set(measurement_ids)
    final: dict[int, str] = {}

    while pending and time.monotonic() < deadline:
        for mid in list(pending):
            try:
                r = _with_retry(lambda mid=mid: requests.get(
                    f"{_BASE}/measurements/{mid}/",
                    headers=hdrs,
                    timeout=15,
                ))
                r.raise_for_status()
                name = r.json().get("status", {}).get("name", "").lower()
                if name in _TERMINAL:
                    final[mid] = name
                    pending.discard(mid)
            except Exception:
                pass
        if pending:
            time.sleep(30)

    for mid in pending:
        final[mid] = "timed_out"
    return final


def fetch_results(measurement_id: int, atlas_key: str) -> list[dict]:
    """Fetch raw probe results for a measurement. Returns [] on failure."""
    try:
        r = _with_retry(lambda: requests.get(
            f"{_BASE}/measurements/{measurement_id}/results/",
            headers=_hdr(atlas_key),
            timeout=30,
        ))
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def parse_ping_rtt(results: list[dict]) -> dict[str, float] | None:
    """Extract min/avg/max RTT (ms) from Atlas ping results. Returns None if no valid RTTs."""
    rtts = [
        float(pkt["rtt"])
        for probe in results
        for pkt in probe.get("result", [])
        if isinstance(pkt.get("rtt"), (int, float)) and pkt["rtt"] > 0
    ]
    if not rtts:
        return None
    return {
        "min": round(min(rtts), 2),
        "avg": round(sum(rtts) / len(rtts), 2),
        "max": round(max(rtts), 2),
    }


def fetch_coverage_by_country(api_key: str) -> dict[str, dict]:
    """
    Paginate Atlas probes and anchors endpoints to build per-country counts.
    Returns {country_code: {"probes": int, "anchors": int}}.
    Shows a Rich progress spinner during the fetch.
    """
    coverage: dict[str, dict] = {}

    def _accumulate(start_url: str, key: str) -> None:
        url: str | None = start_url
        while url:
            try:
                captured = url
                r = _with_retry(lambda u=captured: requests.get(
                    u, headers=_hdr(api_key), timeout=30
                ))
                r.raise_for_status()
                data = r.json()
            except Exception:
                break
            for item in data.get("results", []):
                cc = item.get("country_code", "")
                if cc:
                    entry = coverage.setdefault(cc, {"probes": 0, "anchors": 0})
                    entry[key] += 1
            url = data.get("next")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        p.add_task("Fetching probe coverage by country…", total=None)
        _accumulate(
            f"{_ANCHORS_BASE}/probes/?status=1&fields=country_code&page_size=500",
            "probes",
        )

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        p.add_task("Fetching anchor coverage by country…", total=None)
        _accumulate(
            f"{_ANCHORS_BASE}/anchors/?status=1&fields=country_code&page_size=200",
            "anchors",
        )

    return coverage


def parse_traceroute_as_path(results: list[dict]) -> list[str]:
    """
    Derive a deduplicated AS-hop sequence from Atlas traceroute results.

    Collects all responding hop IPs, resolves them via Cymru bulk lookup,
    then walks the first probe's hop list to build the path.
    Returns [] if no hops could be resolved.
    """
    all_ips: set[str] = set()
    for probe in results:
        for hop in probe.get("result", []):
            for pkt in hop.get("result", []):
                ip = pkt.get("from", "")
                if ip and not ip.startswith("*") and ":" not in ip:
                    all_ips.add(ip)

    if not all_ips:
        return []

    ip_to_info = cymru_bulk_lookup_rich(list(all_ips))

    for probe in results:
        path_asns: list[str] = []   # deduplicate on bare ASN number
        path_labels: list[str] = [] # display strings like "AS1234 (Name)"
        for hop in probe.get("result", []):
            for pkt in hop.get("result", []):
                ip = pkt.get("from", "")
                if ip in ip_to_info:
                    info = ip_to_info[ip]
                    asn = info.get("asn", "")
                    name = clean_asn_name(info.get("name", ""))
                    label = f"{asn} ({name})" if name else asn
                    if not path_asns or path_asns[-1] != asn:
                        path_asns.append(asn)
                        path_labels.append(label)
                    break
        if path_labels:
            return path_labels
    return []
