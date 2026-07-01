import requests
from .asn import resolve_hosts_parallel, cymru_bulk_lookup, normalize_asn
from .utils import _with_retry

SERVERS_URL = "https://export.iperf3serverlist.net/listed_iperf3_servers.json"

# Module-level cache so the country command doesn't re-fetch + re-resolve for each ASN
_resolved_cache: list[dict] | None = None


def parse_port(port_str: str | None) -> int:
    if not port_str:
        return 5201
    try:
        return int(str(port_str).split("-")[0].split(",")[0].strip())
    except (ValueError, AttributeError):
        return 5201


def _fetch_and_resolve() -> list[dict]:
    """
    Fetch the server list, resolve all hostnames, and bulk-lookup ASNs.
    Result is cached for the lifetime of the process.
    """
    global _resolved_cache
    if _resolved_cache is not None:
        return _resolved_cache

    resp = _with_retry(lambda: requests.get(SERVERS_URL, timeout=15))
    resp.raise_for_status()
    raw = resp.json()
    if isinstance(raw, dict):
        for key in ("servers", "data", "results"):
            if key in raw:
                raw = raw[key]
                break

    seen: set[str] = set()
    unique: list[dict] = []
    for s in raw:
        host = (s.get("IP/HOST") or "").strip()
        if host and host not in seen:
            seen.add(host)
            unique.append({**s, "HOST": host})

    host_to_ip = resolve_hosts_parallel([s["HOST"] for s in unique])
    ip_to_asn = cymru_bulk_lookup(list(set(host_to_ip.values())))

    enriched = []
    for s in unique:
        ip = host_to_ip.get(s["HOST"])
        if not ip:
            continue
        enriched.append({
            **s,
            "ip": ip,
            "asn": ip_to_asn.get(ip, "AS???"),
            "port": parse_port(s.get("PORT")),
        })

    _resolved_cache = enriched
    return enriched


def find_servers_in_asn(asn: str, max_count: int = 3) -> list[dict]:
    """Return up to max_count iperf3 servers in the given ASN."""
    target = normalize_asn(asn)
    all_servers = _fetch_and_resolve()
    found = [s for s in all_servers if s["asn"] == target]
    return found[:max_count] if max_count > 0 else found
