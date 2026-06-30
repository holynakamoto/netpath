JITTER_WARNING_MS = 10.0
LOSS_THRESHOLD_FEW = 5.0      # probe_count < 20
LOSS_THRESHOLD_DEFAULT = 1.0  # probe_count 20–99
LOSS_THRESHOLD_MANY = 0.5     # probe_count >= 100
TCP_LATENCY_WARNING_MS = 200.0
TLS_LATENCY_WARNING_MS = 500.0


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
        probe_count = result.get("probe_count")
        jitter_ms = result.get("jitter_ms")

        # Calibrated loss threshold — scales with sample size
        if probe_count is not None and probe_count < 20:
            loss_threshold = LOSS_THRESHOLD_FEW
        elif probe_count is not None and probe_count >= 100:
            loss_threshold = LOSS_THRESHOLD_MANY
        else:
            loss_threshold = LOSS_THRESHOLD_DEFAULT

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
                if loss > loss_threshold:
                    # Forward-scan: if all subsequent responsive hops are clean, this
                    # hop is rate-limiting ICMP probes, not congested.
                    downstream_clean = all(
                        float(dh.get("Loss%", 0.0) or 0.0) <= loss_threshold
                        for j, dh in enumerate(hubs)
                        if j > i and dh.get("host") not in ("???", None, "")
                    )
                    if downstream_clean:
                        hop_id = h.get("host", f"hop {i + 1}")
                        return {
                            "verdict": "Healthy",
                            "severity": "ok",
                            "detail": (
                                "No end-to-end anomalies detected. One or more transit hops "
                                "appear to rate-limit ICMP probes."
                            ),
                            "signals": [
                                f"rate_limited_hops: hop {h.get('count', i + 1)} "
                                f"({hop_id}) Loss%={loss:.1f}"
                            ],
                        }
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

        # (5) High jitter
        if jitter_ms is not None and jitter_ms > JITTER_WARNING_MS:
            return {
                "verdict": "High Jitter",
                "severity": "warning",
                "detail": (
                    f"Path jitter of {jitter_ms:.1f} ms exceeds the "
                    f"{JITTER_WARNING_MS:.1f} ms threshold, indicating unstable latency."
                ),
                "signals": [f"jitter_ms={jitter_ms:.1f}"],
            }

        # (6) PMTU black-hole
        pmtu = result.get("pmtu") or {}
        if pmtu.get("blackhole"):
            return {
                "verdict": "PMTU Black-hole",
                "severity": "critical",
                "detail": (
                    "Large packets (1472-byte ICMP payload) are silently dropped while small "
                    "packets succeed, indicating a misconfigured MTU on the path."
                ),
                "signals": ["pmtu_blackhole=True"],
            }

        # (7) Route flapping
        path_changes = result.get("path_changes")
        if path_changes is not None and path_changes > 0:
            return {
                "verdict": "Route Flapping",
                "severity": "warning",
                "detail": (
                    f"AS path changed {path_changes} time(s) across consecutive probe cycles, "
                    "indicating route instability on the path."
                ),
                "signals": [f"path_changes={path_changes}"],
            }

        # (8) TCP application latency
        tcp_connect_ms = result.get("tcp_connect_ms")
        if tcp_connect_ms is not None and tcp_connect_ms > TCP_LATENCY_WARNING_MS:
            return {
                "verdict": "TCP Latency",
                "severity": "warning",
                "detail": (
                    f"TCP connect latency of {tcp_connect_ms:.0f} ms exceeds the "
                    f"{TCP_LATENCY_WARNING_MS:.0f} ms threshold."
                ),
                "signals": [f"tcp_connect_ms={tcp_connect_ms:.0f}"],
            }

        # (9) TLS application latency
        tls_handshake_ms = result.get("tls_handshake_ms")
        if tls_handshake_ms is not None and tls_handshake_ms > TLS_LATENCY_WARNING_MS:
            return {
                "verdict": "TLS Latency",
                "severity": "warning",
                "detail": (
                    f"TLS handshake latency of {tls_handshake_ms:.0f} ms exceeds the "
                    f"{TLS_LATENCY_WARNING_MS:.0f} ms threshold."
                ),
                "signals": [f"tls_handshake_ms={tls_handshake_ms:.0f}"],
            }

        return default

    except Exception:
        return default
