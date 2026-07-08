#!/usr/bin/env python3
"""
Reference community registry for self-hosted iperf3 servers — stdlib only.

Serves and accepts entries in the same JSON schema as iperf3serverlist.net,
so netpath clients can consume it directly:

    NETPATH_SERVERS_URL=https://registry.example.net/ netpath asn AS64501

Endpoints:
    GET  /          -> {"servers": [...]}
    POST /register  -> validate an entry, TCP-check the claimed server, persist

Run:
    python3 registry.py --port 8080 --store /var/lib/netpath-registry/servers.json

Operators announce themselves with:
    netpath serve --announce https://registry.example.net/register

This is a minimal reference implementation: put it behind a TLS-terminating
reverse proxy and add rate limiting there. Entries are re-verified on write
only; run a periodic sweep (cron + curl/jq) if you need liveness pruning.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 4096
MAX_ENTRIES = 5000
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")
_ALLOWED_KEYS = {"IP/HOST", "PORT", "OPTIONS", "GB/S", "CONTINENT", "COUNTRY", "SITE", "PROVIDER"}

_lock = threading.Lock()


def _valid_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        return bool(_HOSTNAME_RE.match(host)) and "." in host


def _validate(entry: object) -> tuple[dict, str] | tuple[None, str]:
    if not isinstance(entry, dict):
        return None, "entry must be a JSON object"
    host = str(entry.get("IP/HOST", "")).strip()
    if not _valid_host(host):
        return None, "IP/HOST must be a public IP or hostname"
    try:
        port = int(str(entry.get("PORT", "5201")))
    except ValueError:
        return None, "PORT must be an integer"
    if not (1 <= port <= 65535):
        return None, "PORT out of range"
    clean = {k: str(entry.get(k, ""))[:128] for k in _ALLOWED_KEYS}
    clean["IP/HOST"] = host
    clean["PORT"] = str(port)
    return clean, ""


def _tcp_alive(host: str, port: int, timeout: float = 5.0) -> bool:
    """Connect only to a DNS-pinned, globally routable address."""
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    if not addresses:
        return False
    for _family, _socktype, _proto, _canonname, sockaddr in addresses:
        try:
            if not ipaddress.ip_address(sockaddr[0]).is_global:
                return False
        except ValueError:
            return False
    for family, socktype, proto, _canonname, sockaddr in addresses:
        try:
            with socket.socket(family, socktype, proto) as connection:
                connection.settimeout(timeout)
                connection.connect(sockaddr)
            return True
        except OSError:
            continue
    return False


class Handler(BaseHTTPRequestHandler):
    store: Path  # set in main()

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.store.read_text())
            return data.get("servers", []) if isinstance(data, dict) else []
        except (OSError, json.JSONDecodeError):
            return []

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path.rstrip("/") not in ("", "/servers"):
            self._send(404, {"error": "not found"})
            return
        with _lock:
            servers = self._load()
        self._send(200, {"servers": servers})

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        if self.path.rstrip("/") != "/register":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if not 0 < length <= MAX_BODY_BYTES:
            self._send(413, {"error": f"body must be 1-{MAX_BODY_BYTES} bytes"})
            return
        try:
            entry = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return

        clean, err = _validate(entry)
        if clean is None:
            self._send(400, {"error": err})
            return
        if not _tcp_alive(clean["IP/HOST"], int(clean["PORT"])):
            self._send(422, {"error": "could not connect to the advertised server — is the port open?"})
            return

        with _lock:
            servers = self._load()
            key = (clean["IP/HOST"], clean["PORT"])
            servers = [s for s in servers if (s.get("IP/HOST"), str(s.get("PORT"))) != key]
            servers.insert(0, clean)
            if len(servers) > MAX_ENTRIES:
                servers = servers[:MAX_ENTRIES]
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(json.dumps({"servers": servers}, indent=2) + "\n")
        self._send(200, {"registered": clean})

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.client_address[0]} {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--store", default="servers.json", help="JSON file to persist entries in")
    args = parser.parse_args()

    Handler.store = Path(args.store)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"netpath community registry on {args.host}:{args.port}, storing {args.store}")
    server.serve_forever()


if __name__ == "__main__":
    main()
