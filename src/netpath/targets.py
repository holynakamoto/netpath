from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from netpath import country as country_mod, servers
from netpath.asn import cymru_bulk_lookup_rich, normalize_asn

RIPE_ANNOUNCED_PREFIXES = "https://stat.ripe.net/data/announced-prefixes/data.json"


def _tcp_status(ip: str, port: int, timeout: float = 0.75) -> str | None:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return "open"
    except ConnectionRefusedError:
        return "refused"
    except OSError:
        return None


def _awkward_host_address(ip: ipaddress.IPv4Address) -> bool:
    last_octet = int(ip) & 0xff
    return last_octet in (0, 255)


def _prefix_candidate_ips(prefix: str) -> list[str]:
    try:
        net = ipaddress.IPv4Network(prefix, strict=False)
    except ValueError:
        return []
    if net.is_private or net.is_loopback or net.is_link_local or net.is_multicast:
        return []
    if net.prefixlen >= 31:
        if _awkward_host_address(net.network_address):
            return []
        return [str(net.network_address)]

    first = net.network_address + 1
    midpoint = net.network_address + max(1, net.num_addresses // 2)
    last = net.broadcast_address - 1
    candidates = []
    for ip in (first, midpoint, last):
        if ip not in (net.network_address, net.broadcast_address) and not _awkward_host_address(ip):
            candidates.append(str(ip))
    return list(dict.fromkeys(candidates))


def announced_prefix_candidates(asn: str, max_prefixes: int = 12) -> list[str]:
    """Return a small deterministic sample of IPv4 addresses from announced prefixes."""
    asn_norm = normalize_asn(asn)
    r = requests.get(
        RIPE_ANNOUNCED_PREFIXES,
        params={"resource": asn_norm, "min_peers_seeing": 3},
        timeout=15,
    )
    r.raise_for_status()
    raw_prefixes = [
        p.get("prefix") for p in r.json().get("data", {}).get("prefixes", [])
        if isinstance(p, dict) and isinstance(p.get("prefix"), str)
    ]

    parsed: list[ipaddress.IPv4Network] = []
    for prefix in raw_prefixes:
        try:
            net = ipaddress.IPv4Network(prefix, strict=False)
        except ValueError:
            continue
        if not (net.is_private or net.is_loopback or net.is_link_local or net.is_multicast):
            parsed.append(net)

    parsed.sort(key=lambda n: (-n.num_addresses, n.prefixlen, str(n.network_address)))
    ips: list[str] = []
    for net in parsed[:max_prefixes]:
        ips.extend(_prefix_candidate_ips(str(net)))
    return list(dict.fromkeys(ips))


def _validated_prefix_target(asn: str) -> dict | None:
    asn_norm = normalize_asn(asn)
    candidates = announced_prefix_candidates(asn_norm, max_prefixes=4)[:12]
    if not candidates:
        return None

    rich = cymru_bulk_lookup_rich(candidates)
    verified = [
        ip for ip in candidates
        if normalize_asn((rich.get(ip) or {}).get("asn", "")) == asn_norm
    ]
    probes = [(ip, port) for ip in verified for port in (443, 80)]
    with ThreadPoolExecutor(max_workers=min(12, len(probes) or 1)) as executor:
        futures = {
            executor.submit(_tcp_status, ip, port): (ip, port)
            for ip, port in probes
        }
        for future in as_completed(futures):
            ip, port = futures[future]
            status = future.result()
            if status:
                return {
                    "ip": ip,
                    "origin": "ripe-prefix",
                    "confidence": "medium",
                    "reason": (
                        f"sampled from RIPEstat announced prefixes; "
                        f"Cymru verified {asn_norm}; TCP/{port} {status}"
                    ),
                    "port": port,
                    "tcp_status": status,
                    "prefix": (rich.get(ip) or {}).get("prefix"),
                }
    if verified:
        ip = verified[0]
        return {
            "ip": ip,
            "origin": "ripe-prefix",
            "confidence": "low",
            "reason": (
                f"sampled from RIPEstat announced prefixes; Cymru verified "
                f"{asn_norm}, but no TCP liveness check succeeded"
            ),
            "prefix": (rich.get(ip) or {}).get("prefix"),
        }
    return None


def _origin_reason(origin: str | None, asn: str) -> tuple[str, str]:
    if origin == "iperf3":
        return "high", f"public iperf3 server found in {asn}"
    if origin == "atlas":
        return "high", f"connected RIPE Atlas probe address found in {asn}"
    if origin == "peeringdb":
        return "medium", f"PeeringDB netixlan interface address found for {asn}"
    if origin == "user":
        return "user", "user-provided target"
    return "low", "target source unknown"


def discover_target(asn: str, user_target: str | None = None) -> dict | None:
    """Find a usable IPv4 target for an ASN, with source and confidence metadata."""
    asn_norm = normalize_asn(asn)
    if user_target:
        confidence, reason = _origin_reason("user", asn_norm)
        rich = cymru_bulk_lookup_rich([user_target])
        verified_asn = (rich.get(user_target) or {}).get("asn")
        if verified_asn:
            verified_norm = normalize_asn(verified_asn)
            if verified_norm == asn_norm:
                reason = f"user-provided target; Cymru verified {asn_norm}"
            else:
                reason = f"user-provided target; Cymru reports {verified_norm}, expected {asn_norm}"
                confidence = "low"
        return {
            "ip": user_target,
            "origin": "user",
            "confidence": confidence,
            "reason": reason,
            "verified_asn": verified_asn,
            "prefix": (rich.get(user_target) or {}).get("prefix"),
        }

    found = servers.find_servers_in_asn(asn_norm, max_count=1)
    if found:
        confidence, reason = _origin_reason("iperf3", asn_norm)
        return {
            "ip": found[0]["HOST"],
            "origin": "iperf3",
            "confidence": confidence,
            "reason": reason,
            "port": found[0].get("port", 5201),
        }

    ip, origin = country_mod.get_test_target_for_asn(asn_norm)
    if ip:
        confidence, reason = _origin_reason(origin, asn_norm)
        return {
            "ip": ip,
            "origin": origin,
            "confidence": confidence,
            "reason": reason,
        }

    return _validated_prefix_target(asn_norm)
