from __future__ import annotations

import ipaddress
import random
import requests
from collections import defaultdict

from .asn import cymru_bulk_lookup_rich
from . import ixp

RIPE_COUNTRY_RESOURCES = "https://stat.ripe.net/data/country-resource-list/data.json"
RIPE_ATLAS_PROBES      = "https://atlas.ripe.net/api/v2/probes/"

# Global CDN / cloud ASNs that appear in every country's allocation —
# exclude so they don't crowd out actual domestic ISPs.
_GLOBAL_NETWORK_FRAGMENTS = {
    # Global CDN / hyperscaler / transit — appear in every country's allocation
    "AKAMAI", "CLOUDFLARE", "FASTLY", "AMAZON", "GOOGLE", "MICROSOFT",
    "LIMELIGHT", "STACKPATH", "INCAPSULA", "IMPERVA", "COGENT", "LUMEN",
    "LEVEL3", "TELIA", "NTT ", "SEABONE", "HURRICANE", "ZAYO",
    # Academic / research / government — not consumer ISPs
    "UNIVERSITY", "ACADEMIC", "RESEARCH", "EDUCATION", "COMPUTATION CENTER",
    "INTERUNIVERSITY", "IUCC",
}


def _is_global_cdn(name: str) -> bool:
    upper = name.upper()
    return any(frag in upper for frag in _GLOBAL_NETWORK_FRAGMENTS)


def get_top_asns(country_code: str, top_n: int = 4) -> list[dict]:
    """
    Rank ASNs in a country by total allocated IPv4 address space.

    Method:
      1. RIPE Stat country-resource-list  → all IPv4 prefixes allocated to
         entities registered in this country (single API call).
      2. Sample one IP per prefix.
      3. Team Cymru bulk whois            → ASN + org name for every sample
         (single TCP connection).
      4. Aggregate address space per ASN, exclude global CDNs, return top N.
    """
    code = country_code.upper()

    resp = requests.get(RIPE_COUNTRY_RESOURCES, params={"resource": code}, timeout=20)
    resp.raise_for_status()
    ipv4_prefixes = resp.json().get("data", {}).get("resources", {}).get("ipv4", [])

    if not ipv4_prefixes:
        raise RuntimeError(f"RIPE Stat returned no IPv4 resources for '{code}'")

    # Sample one usable IP per prefix; cap at 2000 so Cymru query stays fast
    sample_ips: list[str] = []
    ip_to_size: dict[str, int] = {}

    entries = ipv4_prefixes
    if len(entries) > 2000:
        entries = random.sample(entries, 2000)

    for prefix_str in entries:
        try:
            net = ipaddress.IPv4Network(prefix_str, strict=False)
            if net.is_private:
                continue
            # First usable host via arithmetic — never materialize net.hosts(),
            # which allocates every address in the prefix. /31 and /32 have no
            # distinct first host, so the network address itself is used.
            if net.prefixlen >= 31:
                ip = str(net.network_address)
            else:
                ip = str(net.network_address + 1)
            sample_ips.append(ip)
            ip_to_size[ip] = net.num_addresses
        except ValueError:
            continue

    rich = cymru_bulk_lookup_rich(sample_ips)

    # Aggregate: {asn_str: {addresses, prefix_count, name}}
    totals: dict[str, dict] = defaultdict(lambda: {"addresses": 0, "prefix_count": 0, "name": ""})
    for ip, info in rich.items():
        asn  = info["asn"]
        name = info["name"]
        size = ip_to_size.get(ip, 0)
        totals[asn]["addresses"]    += size
        totals[asn]["prefix_count"] += 1
        if name and not totals[asn]["name"]:
            totals[asn]["name"] = name

    # Filter out unrouted / global CDNs
    filtered = [
        (asn, d) for asn, d in totals.items()
        if asn != "AS???" and not _is_global_cdn(d["name"])
    ]
    filtered.sort(key=lambda x: x[1]["addresses"], reverse=True)

    if not filtered:
        raise RuntimeError(
            f"Could not determine top ASNs for '{code}' — "
            "RIPE data or Cymru lookup may have failed."
        )

    return [
        {
            "asn":          asn,
            "name":         d["name"] or "Unknown",
            "addresses":    d["addresses"],
            "prefix_count": d["prefix_count"],
        }
        for asn, d in filtered[:top_n]
    ]


def _get_atlas_probe_ip(asn: str) -> str | None:
    """Return the IPv4 of a connected RIPE Atlas probe in the ASN.

    This is a public, keyless lookup against the RIPE Atlas probes API —
    no API key, credits, or account are involved, and the address is used
    only as a trace target. It is the sole remnant of the removed
    Atlas measurement backend; no measurements are scheduled through Atlas.

    Tries anchor probes (is_anchor=true) first; falls back to any connected probe.
    Returns None if both queries find nothing or either request fails.
    """
    asn_num = asn.lstrip("ASas")
    base_params = {"asn": asn_num, "status": 1, "sort": "id", "page_size": 25}

    for extra in ({"is_anchor": "true"}, {}):
        try:
            r = requests.get(
                RIPE_ATLAS_PROBES,
                params={**base_params, **extra},
                timeout=5,
            )
            r.raise_for_status()
            for probe in r.json().get("results", []):
                ip = probe.get("address_v4")
                if ip and probe.get("asn_v4") == int(asn_num):
                    return ip
        except requests.RequestException:
            pass

    return None


def get_test_target_for_asn(asn: str) -> tuple[str | None, str | None]:
    """Return (ipv4, origin) for a live trace target in the ASN.

    origin is "atlas" when the address comes from a connected RIPE Atlas
    probe, "peeringdb" when it comes from the ASN's PeeringDB netixlan IXP
    interface list, or None when no target was found.

    A connected Atlas probe address is preferred because it is known to be
    alive; it comes from a public, keyless query of the RIPE Atlas probes
    API and is used purely as a trace target (no Atlas measurements are
    scheduled). When none exists, a PeeringDB IXP interface IPv4 is used as
    a second, non-RIPE source — these are real router interfaces that
    generally answer traceroute. Addresses guessed from announced prefixes
    are still not used, since they rarely answer and burn the full prober
    budget.
    """
    ip = _get_atlas_probe_ip(asn)
    if ip:
        return ip, "atlas"
    ip = ixp.netixlan_ipv4_for_asn(asn)
    if ip:
        return ip, "peeringdb"
    return None, None


def get_test_ip_for_asn(asn: str) -> str | None:
    """Return a live IPv4 trace target in the ASN, or None.

    A connected RIPE Atlas probe address is tried first (known alive); when
    none exists, a PeeringDB netixlan IXP interface IPv4 is returned as a
    fallback. See get_test_target_for_asn for the origin of the returned IP.
    """
    return get_test_target_for_asn(asn)[0]
