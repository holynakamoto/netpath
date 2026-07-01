import requests
from .utils import _with_retry

CF_API_BASE = "https://api.cloudflare.com/client/v4/radar"


def fetch_asn_quality(asn: str, token: str, date_range: str = "7d") -> dict | None:
    """
    Fetch Cloudflare Radar speed + latency summary for an ASN.
    Token needs the radar:read permission (free Cloudflare account).
    Returns a flat dict of metrics, or None on failure.
    """
    asn_num = asn.lstrip("ASas")
    headers = {"Authorization": f"Bearer {token}"}
    params  = {"asn": asn_num, "dateRange": date_range}

    try:
        resp = _with_retry(lambda: requests.get(
            f"{CF_API_BASE}/quality/speed/summary",
            params=params,
            headers=headers,
            timeout=10,
        ))
        if resp.status_code == 401:
            raise ValueError("Cloudflare token invalid or missing radar:read permission")
        resp.raise_for_status()
        data = resp.json()
    except ValueError:
        raise
    except Exception:
        return None

    if not data.get("success"):
        return None

    # The summary lives under result.summary_0
    summary = data.get("result", {}).get("summary_0", {})
    if not summary:
        return None

    def _f(key: str) -> float | None:
        v = summary.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return {
        "dl_mbps":       _f("bandwidthDownload"),
        "ul_mbps":       _f("bandwidthUpload"),
        "latency_idle":  _f("latencyIdle"),
        "latency_loaded": _f("latencyLoaded"),
        "jitter":        _f("jitter"),
        "packet_loss":   _f("packetLoss"),
        "date_range":    date_range,
    }
