import ipaddress

import requests

_IXP_PREFIXES: list | None = None  # None = not yet fetched; [] = fetched but empty/failed


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
