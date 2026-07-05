from __future__ import annotations

import datetime as _dt
import socket
import ssl
import time
from urllib.parse import urljoin, urlparse


def _cert_summary(cert: dict) -> dict:
    summary: dict = {}
    not_after = cert.get("notAfter")
    if not_after:
        summary["not_after"] = not_after
        try:
            expiry = _dt.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=_dt.timezone.utc)
            summary["days_until_expiry"] = max(0, int((expiry - _dt.datetime.now(_dt.timezone.utc)).total_seconds() // 86400))
        except ValueError:
            pass
    names: list[str] = []
    for key, value in cert.get("subjectAltName", ()):
        if key.lower() == "dns":
            names.append(value)
    if names:
        summary["san_dns"] = names[:20]
    return summary


def _read_headers(sock: ssl.SSLSocket) -> tuple[bytes, float | None, float]:
    chunks: list[bytes] = []
    ttfb_ms: float | None = None
    start = time.monotonic()
    while b"\r\n\r\n" not in b"".join(chunks):
        chunk = sock.recv(4096)
        if not chunk:
            break
        if ttfb_ms is None:
            ttfb_ms = (time.monotonic() - start) * 1000.0
        chunks.append(chunk)
        if sum(len(c) for c in chunks) > 65536:
            break
    header_ms = (time.monotonic() - start) * 1000.0
    return b"".join(chunks), ttfb_ms, header_ms


def _single_request(host: str, connect_host: str, path: str, timeout: float) -> dict:
    ctx = ssl.create_default_context()
    request_start = time.monotonic()
    t0 = request_start
    raw = socket.create_connection((connect_host, 443), timeout=timeout)
    tcp_ms = (time.monotonic() - t0) * 1000.0
    try:
        t1 = time.monotonic()
        sock = ctx.wrap_socket(raw, server_hostname=host)
        tls_ms = (time.monotonic() - t1) * 1000.0
        cert = sock.getpeercert() or {}
        req = (
            f"HEAD {path or '/'} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "User-Agent: netpath/edge-probe\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(req.encode("ascii", "replace"))
        header_blob, ttfb_ms, header_ms = _read_headers(sock)
        total_ms = (time.monotonic() - request_start) * 1000.0
        sock.close()
    except Exception:
        raw.close()
        raise

    header_text = header_blob.decode("iso-8859-1", "replace")
    lines = header_text.splitlines()
    status_code = None
    if lines:
        parts = lines[0].split()
        if len(parts) >= 2:
            try:
                status_code = int(parts[1])
            except ValueError:
                pass
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.lower()] = value.strip()
    return {
        "status_code": status_code,
        "tcp_connect_ms": round(tcp_ms, 2),
        "tls_handshake_ms": round(tls_ms, 2),
        "ttfb_ms": round(ttfb_ms, 2) if ttfb_ms is not None else None,
        "header_ms": round(header_ms, 2),
        "total_ms": round(total_ms, 2),
        "http_version": lines[0].split()[0] if lines else None,
        "location": headers.get("location"),
        "server": headers.get("server"),
        "certificate": _cert_summary(cert),
    }


def measure(hostname: str, connect_host: str | None = None, timeout: float = 5.0, max_redirects: int = 3) -> dict:
    """Measure HTTPS edge timing and shallow HTTP metadata."""
    target_host = hostname
    connect_target = connect_host or hostname
    result: dict = {
        "host": target_host,
        "connect_host": connect_target,
        "scheme": "https",
        "status_code": None,
        "redirect_count": 0,
        "ttfb_ms": None,
        "header_ms": None,
        "total_ms": None,
        "chain_total_ms": None,
        "requests": [],
        "http_version": None,
        "certificate": {},
        "error": None,
    }
    path = "/"
    try:
        chain_total_ms = 0.0
        for redirect_count in range(max_redirects + 1):
            one = _single_request(target_host, connect_target, path, timeout)
            chain_total_ms += one.get("total_ms") or 0.0
            request_info = {
                "url": f"https://{target_host}{path}",
                "host": target_host,
                "connect_host": connect_target,
                "status_code": one.get("status_code"),
                "tcp_connect_ms": one.get("tcp_connect_ms"),
                "tls_handshake_ms": one.get("tls_handshake_ms"),
                "ttfb_ms": one.get("ttfb_ms"),
                "header_ms": one.get("header_ms"),
                "total_ms": one.get("total_ms"),
            }
            if one.get("location"):
                request_info["location"] = one["location"]
            result["requests"].append(request_info)
            result.update({k: v for k, v in one.items() if k != "location"})
            result["redirect_count"] = redirect_count
            location = one.get("location")
            if one.get("status_code") not in {301, 302, 303, 307, 308} or not location:
                break
            parsed = urlparse(urljoin(f"https://{target_host}{path}", location))
            if parsed.scheme != "https" or not parsed.hostname:
                break
            target_host = parsed.hostname
            connect_target = parsed.hostname
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
        result["host"] = target_host
        result["connect_host"] = connect_target
        result["chain_total_ms"] = round(chain_total_ms, 2)
    except Exception as exc:
        result["error"] = str(exc)
    return result
