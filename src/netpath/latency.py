from __future__ import annotations

import socket
import ssl
import time


def measure_tcp_connect(host: str, port: int = 443, timeout: float = 5.0) -> float | None:
    """
    Measure TCP connect latency (SYN→SYN-ACK) in milliseconds.
    Returns None on any failure (connection refused, timeout, OS error).
    """
    try:
        t0 = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        sock.close()
        return round(elapsed_ms, 2)
    except (ConnectionRefusedError, OSError):
        return None


def measure_tls_handshake(host: str, port: int = 443, timeout: float = 5.0) -> float | None:
    """
    Measure TLS handshake duration in milliseconds (from TCP connect to handshake complete).
    Returns None on any failure (SSL error, connection refused, timeout, OS error).
    """
    try:
        ctx = ssl.create_default_context()
        t0 = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            ssl_sock = ctx.wrap_socket(sock, server_hostname=host)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            ssl_sock.close()
            return round(elapsed_ms, 2)
        except ssl.SSLError:
            sock.close()
            return None
    except (ConnectionRefusedError, OSError):
        return None
