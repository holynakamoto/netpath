"""
HTTP-based throughput measurement — no dedicated server required.

Downloads from / uploads to speed.cloudflare.com, which has CDN nodes
peered inside every major ISP globally. The measured throughput reflects
the path from this host to the nearest Cloudflare PoP, which is typically
inside the local ISP's network.
"""

from __future__ import annotations


import time
import requests

CF_DOWN_URL = "https://speed.cloudflare.com/__down"
CF_UP_URL   = "https://speed.cloudflare.com/__up"

# Payload sizes: ramp up to saturate the link quickly
_DOWN_BYTES = 25_000_000   # 25 MB download probe
_UP_BYTES   = 10_000_000   # 10 MB upload probe
_TIMEOUT    = 30           # seconds per direction


def _download(duration: int = 5) -> dict:
    """Stream a download from Cloudflare and return throughput stats."""
    start = time.monotonic()
    total = 0
    first_byte: float | None = None

    with requests.get(
        CF_DOWN_URL,
        params={"bytes": _DOWN_BYTES},
        stream=True,
        timeout=_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        deadline = start + duration
        for chunk in resp.iter_content(chunk_size=65_536):
            if first_byte is None:
                first_byte = time.monotonic()
            total += len(chunk)
            if time.monotonic() >= deadline:
                break

    elapsed = time.monotonic() - start
    ttfb_ms = (first_byte - start) * 1000 if first_byte else None
    return {
        "bps":     (total * 8) / elapsed if elapsed > 0 else 0,
        "bytes":   total,
        "elapsed": round(elapsed, 2),
        "ttfb_ms": round(ttfb_ms, 1) if ttfb_ms else None,
    }


def _upload(duration: int = 5) -> dict:
    """POST a zero-filled payload to Cloudflare and return throughput stats."""
    payload_size = min(_UP_BYTES, duration * 20_000_000)  # ~20 MB/s cap on payload
    start = time.monotonic()

    resp = requests.post(
        CF_UP_URL,
        data=bytes(payload_size),
        headers={"Content-Type": "application/octet-stream"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()

    elapsed = time.monotonic() - start
    return {
        "bps":     (payload_size * 8) / elapsed if elapsed > 0 else 0,
        "bytes":   payload_size,
        "elapsed": round(elapsed, 2),
    }


def run(duration: int = 5) -> dict:
    """
    Run download + upload speed test against Cloudflare.

    Each direction is attempted independently: a failure in one direction no
    longer discards a successful reading in the other (mirrors the
    ``probe_errors`` convention). Returns
    ``{"download": {...}|None, "upload": {...}|None,
       "server": "speed.cloudflare.com", "errors": {direction: reason}}``.
    """
    result: dict = {
        "download": None,
        "upload":   None,
        "server":   "speed.cloudflare.com",
        "errors":   {},
    }

    try:
        result["download"] = _download(duration)
    except Exception as e:
        result["errors"]["download"] = str(e)

    try:
        result["upload"] = _upload(duration)
    except Exception as e:
        result["errors"]["upload"] = str(e)

    return result


def extract_stats(result: dict) -> tuple[dict | None, dict | None]:
    """Return (upload_stats, download_stats) in the format display expects.

    Either element is None when that direction was not measured, so callers
    can render whatever succeeded.
    """
    dl = result.get("download")
    ul = result.get("upload")

    upload_stats = None
    if ul is not None:
        upload_stats = {
            "bps":         ul["bps"],
            "bytes":       ul["bytes"],
            "retransmits": None,
        }

    download_stats = None
    if dl is not None:
        download_stats = {
            "bps":      dl["bps"],
            "recv_bps": dl["bps"],
            "bytes":    dl["bytes"],
            "ttfb_ms":  dl.get("ttfb_ms"),
        }

    return upload_stats, download_stats
