import ipaddress
import random
import requests
from collections import defaultdict

from .asn import cymru_bulk_lookup_rich

RIPE_COUNTRY_RESOURCES = "https://stat.ripe.net/data/country-resource-list/data.json"
RIPE_PREFIXES          = "https://stat.ripe.net/data/announced-prefixes/data.json"
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
            hosts = list(net.hosts())
            if not hosts:
                continue
            ip = str(hosts[0])
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

    Tries anchor probes (is_anchor=true) first; falls back to any connected probe.
    Returns None if both queries find nothing or either request fails.
    """
    asn_num = asn.lstrip("ASas")
    base_params = {"asn": asn_num, "status": 1, "sort": "id", "page_size": 1}

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
                if ip:
                    return ip
        except requests.RequestException:
            pass

    return None


def get_test_ip_for_asn(asn: str) -> str | None:
    """Return a routable IPv4 in the ASN — Atlas probe first, RIPE prefix as fallback."""
    atlas_ip = _get_atlas_probe_ip(asn)
    if atlas_ip:
        return atlas_ip

    asn_num = asn.lstrip("ASas")
    try:
        resp = requests.get(
            RIPE_PREFIXES, params={"resource": f"AS{asn_num}"}, timeout=15
        )
        resp.raise_for_status()
        prefixes = resp.json().get("data", {}).get("prefixes", [])
    except Exception:
        return None

    # Build valid IPv4 networks sorted most-specific first (highest prefixlen)
    ipv4_nets: list[ipaddress.IPv4Network] = []
    for entry in prefixes:
        prefix = entry.get("prefix", "")
        if ":" in prefix:
            continue
        try:
            net = ipaddress.IPv4Network(prefix, strict=False)
            if not net.is_private and net.prefixlen >= 8:
                ipv4_nets.append(net)
        except ValueError:
            continue

    ipv4_nets.sort(key=lambda n: n.prefixlen, reverse=True)

    for net in ipv4_nets:
        hosts = list(net.hosts())
        if len(hosts) >= 2:
            return str(hosts[1])
    return None
