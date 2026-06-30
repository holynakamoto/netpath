"""
HTTP-based throughput measurement — no dedicated server required.

Downloads from / uploads to speed.cloudflare.com, which has CDN nodes
peered inside every major ISP globally. The measured throughput reflects
the path from this host to the nearest Cloudflare PoP, which is typically
inside the local ISP's network.
"""

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
    Returns {"download": {...}, "upload": {...}, "server": "speed.cloudflare.com"}.
    """
    try:
        download = _download(duration)
    except Exception as e:
        raise RuntimeError(f"Download test failed: {e}")

    try:
        upload = _upload(duration)
    except Exception as e:
        raise RuntimeError(f"Upload test failed: {e}")

    return {
        "download": download,
        "upload":   upload,
        "server":   "speed.cloudflare.com",
    }


def extract_stats(result: dict) -> tuple[dict, dict]:
    """Return (upload_stats, download_stats) in the format display expects."""
    dl = result["download"]
    ul = result["upload"]
    upload_stats = {
        "bps":         ul["bps"],
        "bytes":       ul["bytes"],
        "retransmits": None,
    }
    download_stats = {
        "bps":      dl["bps"],
        "recv_bps": dl["bps"],
        "bytes":    dl["bytes"],
        "ttfb_ms":  dl.get("ttfb_ms"),
    }
    return upload_stats, download_stats
