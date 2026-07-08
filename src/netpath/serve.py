"""
Run and register a self-hosted iperf3 server so netpath can find it.

Public iperf3 coverage is sparse — most ASNs have no listed server, so
throughput measurement degrades to low-confidence targets. `netpath serve`
wraps `iperf3 -s` and handles the discovery half: the local registry
(~/.netpath/servers.json), community registry announcement, the DNS SRV
record to publish, and public-list submission guidance.
"""
from __future__ import annotations

import ipaddress
import json
import subprocess
from importlib import resources
from pathlib import Path

import requests

from netpath import iperf as iperf_mod
from netpath.asn import cymru_bulk_lookup_rich
from netpath.globalping import get_public_ip
from netpath.servers import LOCAL_REGISTRY_PATH, SRV_SERVICE_PREFIX

PUBLIC_LIST_REPO = "https://github.com/R0GGER/public-iperf3-servers"

# Deployment assets shipped inside the package (src/netpath/deploy/) so
# `netpath serve --emit ...` works from any pip install, not just a checkout.
DEPLOY_ASSETS = {
    "systemd":    "iperf3-server.service",
    "docker":     "Dockerfile",
    "compose":    "docker-compose.yml",
    "cloud-init": "cloud-init.yaml",
    "install":    "install.sh",
    "registry":   "registry.py",
}
_DEFAULT_PORT = 5201


def detect_identity(advertise_host: str | None = None) -> dict:
    """
    Detect the public IP of this machine and its ASN attribution via Cymru.
    Returns {"ip", "host", "asn", "prefix", "country", "name"}; every field
    may be empty/None when detection fails (offline, RFC1918-only, etc.).
    """
    ip = get_public_ip()
    record = (cymru_bulk_lookup_rich([ip]) or {}).get(ip, {}) if ip else {}
    return {
        "ip": ip,
        "host": advertise_host or ip,
        "asn": record.get("asn"),
        "prefix": record.get("prefix"),
        "country": record.get("country", ""),
        "name": record.get("name", ""),
    }


def build_entry(identity: dict, port: int = _DEFAULT_PORT, site: str = "") -> dict:
    """Build a server entry in the public iperf3serverlist.net schema."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return {
        "IP/HOST": identity.get("host") or "",
        "PORT": str(port),
        "OPTIONS": "",
        "GB/S": "",
        "CONTINENT": "",
        "COUNTRY": identity.get("country") or "",
        "SITE": site,
        "PROVIDER": identity.get("name") or "",
    }


def register_local(entry: dict, path: Path | None = None) -> Path:
    """
    Merge entry into the local server registry, replacing any previous entry
    for the same host+port and keeping the newest entry first.
    """
    path = Path(path or LOCAL_REGISTRY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                existing = [e for e in data if isinstance(e, dict)]
        except (OSError, json.JSONDecodeError):
            existing = []
    key = (entry.get("IP/HOST"), str(entry.get("PORT")))
    existing = [e for e in existing if (e.get("IP/HOST"), str(e.get("PORT"))) != key]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps([entry] + existing, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)
    return path


def announce(url: str, entry: dict) -> None:
    """POST this server's entry to a community registry (see deploy/registry.py)."""
    resp = requests.post(url, json=entry, timeout=15)
    resp.raise_for_status()


def suggest_srv_domain(host: str) -> str | None:
    """Best-guess domain to publish the SRV record on; None when host is an IP."""
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    labels = host.rstrip(".").split(".")
    if len(labels) < 2:
        return None
    return ".".join(labels[1:]) if len(labels) > 2 else host


def srv_record(domain: str, target_host: str, port: int = _DEFAULT_PORT) -> str:
    """The DNS record an operator publishes so netpath can discover this server."""
    return f"{SRV_SERVICE_PREFIX}.{domain.rstrip('.')}. 3600 IN SRV 0 0 {port} {target_host.rstrip('.')}."


def emit_asset(name: str, port: int = _DEFAULT_PORT) -> str:
    """Return a packaged deployment asset, with the default port substituted."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if name not in DEPLOY_ASSETS:
        raise KeyError(f"unknown asset {name!r}; choose from {', '.join(sorted(DEPLOY_ASSETS))}")
    text = (resources.files("netpath") / "deploy" / DEPLOY_ASSETS[name]).read_text()
    if port != _DEFAULT_PORT:
        text = text.replace(str(_DEFAULT_PORT), str(port))
    return text


def run_server(port: int = _DEFAULT_PORT) -> int:
    """Run iperf3 -s in the foreground until interrupted. Returns the exit code."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not iperf_mod.available():
        raise RuntimeError(
            "iperf3 is not installed — install it first "
            "(brew install iperf3 / apt install iperf3 / dnf install iperf3)"
        )
    try:
        return subprocess.run(["iperf3", "-s", "-p", str(port)]).returncode
    except KeyboardInterrupt:
        return 0
