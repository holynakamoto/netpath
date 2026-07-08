from __future__ import annotations

import json
import os
import socket
import subprocess
import warnings
from pathlib import Path

import requests
from . import iperf as _iperf
from .asn import resolve_hosts_parallel, cymru_bulk_lookup, normalize_asn
from .utils import _with_retry

SERVERS_URL = "https://export.iperf3serverlist.net/listed_iperf3_servers.json"

# Self-hosted servers (see `netpath serve`): a local registry file plus any
# number of org/community-hosted list URLs, all in the same JSON schema as
# the public list. These sources are preferred over the public list.
LOCAL_REGISTRY_PATH = Path.home() / ".netpath" / "servers.json"
EXTRA_SERVERS_ENV = "NETPATH_SERVERS_URL"

# DNS-based advertisement: operators publish an SRV record like
#   _netpath-iperf3._tcp.example.com. 3600 IN SRV 0 0 5201 iperf.example.com.
SRV_SERVICE_PREFIX = "_netpath-iperf3._tcp"
DOH_URL = "https://cloudflare-dns.com/dns-query"

# Module-level cache so the country command doesn't re-fetch + re-resolve for each ASN
_resolved_cache: list[dict] | None = None


def parse_port(port_str: str | None) -> int:
    if not port_str:
        return 5201
    try:
        return int(str(port_str).split("-")[0].split(",")[0].strip())
    except (ValueError, AttributeError):
        return 5201


def _unwrap_server_list(raw) -> list[dict]:
    if isinstance(raw, dict):
        for key in ("servers", "data", "results"):
            if key in raw:
                raw = raw[key]
                break
    return [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []


def _load_local_registry() -> list[dict]:
    """Servers registered on this machine via `netpath serve` or by hand."""
    try:
        return _unwrap_server_list(json.loads(LOCAL_REGISTRY_PATH.read_text()))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        warnings.warn(f"ignoring unreadable local server registry {LOCAL_REGISTRY_PATH}: {exc}")
        return []


def _fetch_extra_lists() -> list[dict]:
    """Servers from org/community-hosted list URLs in NETPATH_SERVERS_URL (comma-separated)."""
    entries: list[dict] = []
    for url in (u.strip() for u in os.environ.get(EXTRA_SERVERS_ENV, "").split(",")):
        if not url:
            continue
        try:
            resp = _with_retry(lambda url=url: requests.get(url, timeout=15))
            resp.raise_for_status()
            entries.extend(_unwrap_server_list(resp.json()))
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            warnings.warn(f"ignoring unreachable server list {url}: {exc}")
    return entries


def _fetch_public_list(have_other_sources: bool) -> list[dict]:
    try:
        resp = _with_retry(lambda: requests.get(SERVERS_URL, timeout=15))
        resp.raise_for_status()
        return _unwrap_server_list(resp.json())
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        if not have_other_sources:
            raise
        warnings.warn("public iperf3 server list unavailable; using local/custom servers only")
        return []


def _fetch_and_resolve() -> list[dict]:
    """
    Gather servers from the local registry, custom list URLs, and the public
    list; resolve all hostnames and bulk-lookup ASNs.
    Local/custom entries come first so self-hosted servers are preferred.
    Result is cached for the lifetime of the process.
    """
    global _resolved_cache
    if _resolved_cache is not None:
        return _resolved_cache

    raw = [{**s, "source": "local"} for s in _load_local_registry()]
    raw += [{**s, "source": "custom"} for s in _fetch_extra_lists()]
    raw += [{**s, "source": "public"} for s in _fetch_public_list(have_other_sources=bool(raw))]

    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for s in raw:
        host = (s.get("IP/HOST") or "").strip()
        port = parse_port(s.get("PORT"))
        key = (host, port)
        if host and key not in seen:
            seen.add(key)
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


def _tcp_alive(ip: str, port: int, timeout: float = 3.0) -> bool:
    try:
        socket.create_connection((ip, port), timeout).close()
        return True
    except OSError:
        return False


def _is_iperf3_alive(ip: str, port: int) -> bool:
    if not _iperf.available():
        return _tcp_alive(ip, port)
    try:
        r = subprocess.run(
            ["iperf3", "-c", ip, "-p", str(port), "-t", "1", "-J"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if r.returncode != 0:
        return False
    try:
        data = json.loads(r.stdout or r.stderr)
    except json.JSONDecodeError:
        return False
    return "error" not in data


def find_servers_in_asn(asn: str, max_count: int = 3) -> list[dict]:
    """Return up to max_count live iperf3 servers in the given ASN."""
    target = normalize_asn(asn)
    all_servers = _fetch_and_resolve()
    candidates = [s for s in all_servers if s["asn"] == target]
    live = [s for s in candidates if _is_iperf3_alive(s["ip"], s["port"])]
    if max_count > 0:
        live = live[:max_count]
    return live


def _doh_srv_query(name: str, timeout: int = 8) -> list[dict]:
    """Resolve SRV records for name via DNS-over-HTTPS (JSON API)."""
    resp = requests.get(
        DOH_URL,
        params={"name": name, "type": "SRV"},
        headers={"Accept": "application/dns-json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    records: list[dict] = []
    for answer in resp.json().get("Answer") or []:
        if answer.get("type") != 33:  # SRV
            continue
        parts = str(answer.get("data", "")).split()
        if len(parts) != 4:
            continue
        priority, weight, port, target = parts
        try:
            parsed_port = int(port)
            if not 1 <= parsed_port <= 65535:
                continue
            records.append({
                "priority": int(priority),
                "weight": int(weight),
                "port": parsed_port,
                "host": target.rstrip("."),
            })
        except ValueError:
            continue
    records.sort(key=lambda r: (r["priority"], -r["weight"]))
    return records


def find_advertised_server(hostname: str) -> dict | None:
    """
    Find an iperf3 server advertised for hostname via a DNS SRV record
    (see SRV_SERVICE_PREFIX). The record must be owned by the exact hostname
    being tested; parent-zone walking would cross DNS delegation boundaries.
    Returns {"host", "port", "domain"} or None.
    """
    domain = hostname.rstrip(".")
    try:
        records = _doh_srv_query(f"{SRV_SERVICE_PREFIX}.{domain}")
    except (requests.RequestException, ValueError):
        return None
    for record in records:
        if record["host"] and record["port"]:
            return {"host": record["host"], "port": record["port"], "domain": domain}
    return None
