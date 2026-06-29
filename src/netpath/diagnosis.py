def diagnose(result: dict) -> dict:
    """Classify collected measurements into a plain-language verdict.

    Pure function — no I/O, no imports from netpath modules.
    Returns a dict with keys: verdict, severity, detail, signals.
    Never raises.
    """
    default: dict = {
        "verdict": "Healthy",
        "severity": "ok",
        "detail": "No anomalies detected on the measured path.",
        "signals": [],
    }
    try:
        hubs = result.get("hubs") or []
        bufferbloat = result.get("bufferbloat_ms")
        rum = result.get("rum")
        download_mbps = result.get("download_mbps")

        # (1) Severe bufferbloat
        if bufferbloat is not None and bufferbloat > 30:
            return {
                "verdict": "Severe Bufferbloat",
                "severity": "critical",
                "detail": (
                    f"Latency rose {bufferbloat:.0f} ms under load, "
                    "indicating severe queuing congestion on the path."
                ),
                "signals": [f"bufferbloat_ms={bufferbloat:.1f}"],
            }

        # (2) Mid-path packet loss — requires at least 2 hops
        if len(hubs) > 1:
            last_resp_idx = -1
            for i, h in enumerate(hubs):
                if h.get("host") not in ("???", None, ""):
                    last_resp_idx = i
            for i, h in enumerate(hubs):
                if i == 0 or i >= last_resp_idx:
                    continue
                if h.get("host") in ("???", None, ""):
                    continue
                loss = float(h.get("Loss%", 0.0) or 0.0)
                if loss > 1.0:
                    hop_id = h.get("host", f"hop {i + 1}")
                    return {
                        "verdict": "Mid-path Packet Loss",
                        "severity": "warning",
                        "detail": (
                            f"Packet loss of {loss:.1f}% detected at {hop_id}, "
                            "suggesting a congested or faulty intermediate hop."
                        ),
                        "signals": [f"hop {h.get('count', i + 1)} ({hop_id}) Loss%={loss:.1f}"],
                    }

        # (3) Last-mile congestion — first hop loss combined with bufferbloat
        if hubs:
            first_loss = float(hubs[0].get("Loss%", 0.0) or 0.0)
            if first_loss > 0 and bufferbloat is not None and bufferbloat > 5:
                return {
                    "verdict": "Last-mile Congestion",
                    "severity": "warning",
                    "detail": (
                        f"First-hop loss of {first_loss:.1f}% combined with "
                        f"{bufferbloat:.0f} ms bufferbloat indicates last-mile congestion."
                    ),
                    "signals": [
                        f"first-hop Loss%={first_loss:.1f}",
                        f"bufferbloat_ms={bufferbloat:.1f}",
                    ],
                }

        # (4) Throughput cap — measured download significantly below RUM baseline
        if rum is not None and download_mbps is not None:
            rum_dl = rum.get("dl_mbps")
            if rum_dl and download_mbps < rum_dl * 0.7:
                return {
                    "verdict": "Throughput Cap",
                    "severity": "warning",
                    "detail": (
                        f"Measured download ({download_mbps:.0f} Mbps) is more than 30% below "
                        f"the Cloudflare RUM baseline for this ASN ({rum_dl:.0f} Mbps)."
                    ),
                    "signals": [
                        f"download_mbps={download_mbps:.0f}",
                        f"rum_dl_mbps={rum_dl:.0f}",
                    ],
                }

        return default

    except Exception:
        return default
