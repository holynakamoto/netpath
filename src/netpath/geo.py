from __future__ import annotations

import ipaddress
import math

from netpath import globe


def _public_host(host: str | None) -> bool:
    if not host or host == "???":
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast)


def _distance_km(a: dict, b: dict) -> float:
    lat1 = math.radians(float(a["lat"]))
    lon1 = math.radians(float(a["lon"]))
    lat2 = math.radians(float(b["lat"]))
    lon2 = math.radians(float(b["lon"]))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def analyze_path(hubs: list[dict]) -> dict:
    hosts = []
    for hub in hubs:
        host = hub.get("host")
        if _public_host(host) and host not in hosts:
            hosts.append(host)
    result: dict = {
        "hops": [],
        "total_geodesic_km": None,
        "latency_implied_max_km": None,
        "country_hops": [],
        "warnings": [],
        "error": None,
    }
    if not hosts:
        return result
    try:
        geo = globe.geolocate_hosts(hosts)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    geo_hops: list[dict] = []
    for hub in hubs:
        host = hub.get("host")
        if not host or host not in geo:
            continue
        item = {
            "hop": hub.get("count"),
            "host": host,
            "asn": hub.get("ASN"),
            "avg_ms": hub.get("Avg"),
            **geo[host],
        }
        geo_hops.append(item)
    result["hops"] = geo_hops
    countries = [h.get("country_code") for h in geo_hops if h.get("country_code")]
    result["country_hops"] = [c for i, c in enumerate(countries) if i == 0 or countries[i - 1] != c]

    total = 0.0
    for prev, cur in zip(geo_hops, geo_hops[1:]):
        total += _distance_km(prev, cur)
    if geo_hops:
        result["total_geodesic_km"] = round(total, 1)

    last_rtt = None
    for hop in reversed(geo_hops):
        if isinstance(hop.get("avg_ms"), (int, float)) and hop["avg_ms"] > 0:
            last_rtt = float(hop["avg_ms"])
            break
    if last_rtt is not None:
        # One-way fiber propagation is roughly 200 km/ms; RTT budget halves it.
        result["latency_implied_max_km"] = round(last_rtt * 100.0, 1)
        if total > result["latency_implied_max_km"] * 1.5 and total > 3000:
            result["warnings"].append("geographic_path_exceeds_latency_budget")
    if len(set(result["country_hops"])) >= 3:
        result["warnings"].append("multi_country_trombone")
    return result


def attach_hop_locations(hubs: list[dict], analysis: dict | None) -> None:
    """Attach structured approximate geolocation to matching trace hops in place."""
    locations = {
        hop.get("host"): {
            key: hop.get(key)
            for key in (
                "lat",
                "lon",
                "city",
                "region",
                "country",
                "country_code",
                "as",
                "org",
            )
            if hop.get(key) not in (None, "")
        }
        for hop in (analysis or {}).get("hops", [])
        if hop.get("host")
    }
    for hub in hubs:
        location = locations.get(hub.get("host"))
        if location:
            hub["geo"] = location
