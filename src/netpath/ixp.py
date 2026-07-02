from __future__ import annotations

import ipaddress

import requests

from .asn import normalize_asn

_IXP_PREFIXES: list | None = None  # None = not yet fetched; [] = fetched but empty/failed

# Per-ASN cache of PeeringDB netixlan records (the ASN's IXP interface entries).
# Missing key = not yet fetched; [] = fetched but empty/failed.
_NETIXLAN_CACHE: dict[str, list] = {}


def _load_ixp_prefixes() -> list:
    global _IXP_PREFIXES
    if _IXP_PREFIXES is not None:
        return _IXP_PREFIXES
    try:
        resp = requests.get("https://www.peeringdb.com/api/ixpfx", timeout=5)
        data = resp.json()
        _IXP_PREFIXES = [
            item["prefix"]
            for item in data.get("data", [])
            if item.get("prefix")
        ]
    except Exception:
        _IXP_PREFIXES = []
    return _IXP_PREFIXES


def classify_hop(ip: str) -> str:
    """
    Classify an IP address as 'ixp' or 'transit'.
    Fetches PeeringDB IXP prefix data on first call and caches it in process memory.
    Returns 'transit' silently when the fetch fails or the IP is not in any IXP prefix.
    """
    if not ip or ip == "???":
        return "transit"
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return "transit"

    for prefix_str in _load_ixp_prefixes():
        try:
            if ip_obj in ipaddress.ip_network(prefix_str, strict=False):
                return "ixp"
        except ValueError:
            continue
    return "transit"


def _load_netixlan(asn: str) -> list:
    """Fetch PeeringDB netixlan records for an ASN, caching the result per-ASN.

    Returns the raw list of interface records (each carrying ipaddr4/ipaddr6);
    an empty list on any failure. Reuses the same PeeringDB access pattern as
    the IXP prefix classifier above.
    """
    asn_num = normalize_asn(asn)[2:]  # bare integer string, e.g. "3356"
    if asn_num in _NETIXLAN_CACHE:
        return _NETIXLAN_CACHE[asn_num]
    try:
        resp = requests.get(
            "https://www.peeringdb.com/api/netixlan",
            params={"asn": asn_num},
            timeout=5,
        )
        records = resp.json().get("data", [])
    except Exception:
        records = []
    _NETIXLAN_CACHE[asn_num] = records
    return records


def netixlan_ipv4_for_asn(asn: str) -> str | None:
    """Return one PeeringDB IXP interface IPv4 for the ASN, or None.

    These are real router interface addresses at the IXPs the ASN peers on,
    which generally answer ping/traceroute. Selection is deterministic: the
    first record (in PeeringDB's returned order) carrying a usable ipaddr4.
    """
    for rec in _load_netixlan(asn):
        ip = rec.get("ipaddr4")
        if ip:
            return ip
    return None
