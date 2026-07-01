JITTER_WARNING_MS = 10.0
LOSS_THRESHOLD_FEW = 5.0      # probe_count < 20
LOSS_THRESHOLD_DEFAULT = 1.0  # probe_count 20–99
LOSS_THRESHOLD_MANY = 0.5     # probe_count >= 100
TCP_LATENCY_WARNING_MS = 200.0
TLS_LATENCY_WARNING_MS = 500.0

_SEVERITY_ORDER = {"ok": 0, "warning": 1, "critical": 2}

_CONDITION_VERDICT = {
    "incomplete_path": "Incomplete Path",
    "severe_bufferbloat": "Severe Bufferbloat",
    "mid_path_packet_loss": "Mid-path Packet Loss",
    "rate_limited_hop": "Healthy",
    "last_mile_congestion": "Last-mile Congestion",
    "throughput_cap": "Throughput Cap",
    "high_jitter": "High Jitter",
    "pmtu_blackhole": "PMTU Black-hole",
    "route_flapping": "Route Flapping",
    "tcp_latency": "TCP Latency",
    "tls_latency": "TLS Latency",
}


def diagnose(result: dict) -> dict:
    """Classify collected measurements into a plain-language verdict.

    Pure function — no I/O, no imports from netpath modules.
    Returns a dict with keys: verdict, severity, detail, signals, partial_results.
    All nine checks run unconditionally; every matched condition is accumulated into
    signals before the verdict is derived. Never raises.
    """
    try:
        signals: list = []
        probe_errors = result.get("probe_errors") or {}

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

        # (0) Incomplete path — traceroute never reached the target ASN
        if result.get("path_complete") is False:
            stall = result.get("stall_hop")
            stall_str = f" at hop {stall}" if stall is not None else ""
            signals.append({
                "condition": "incomplete_path",
                "severity": "warning",
                "detail": (
                    f"Traceroute did not reach the target ASN{stall_str}. "
                    "The path may be filtered or the target unreachable."
                ),
            })

        # (1) Severe bufferbloat
        if bufferbloat is not None and bufferbloat > 30:
            signals.append({
                "condition": "severe_bufferbloat",
                "severity": "critical",
                "detail": (
                    f"Latency rose {bufferbloat:.0f} ms under load, "
                    "indicating severe queuing congestion on the path."
                ),
            })

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
                        signals.append({
                            "condition": "rate_limited_hop",
                            "severity": "ok",
                            "detail": (
                                "No end-to-end anomalies detected. One or more transit hops "
                                "appear to rate-limit ICMP probes."
                            ),
                        })
                    else:
                        hop_id = h.get("host", f"hop {i + 1}")
                        signals.append({
                            "condition": "mid_path_packet_loss",
                            "severity": "warning",
                            "detail": (
                                f"Packet loss of {loss:.1f}% detected at {hop_id}, "
                                "suggesting a congested or faulty intermediate hop."
                            ),
                        })
                    break

        # (3) Last-mile congestion — first hop loss combined with bufferbloat
        if hubs:
            first_loss = float(hubs[0].get("Loss%", 0.0) or 0.0)
            if first_loss > 0 and bufferbloat is not None and bufferbloat > 5:
                signals.append({
                    "condition": "last_mile_congestion",
                    "severity": "warning",
                    "detail": (
                        f"First-hop loss of {first_loss:.1f}% combined with "
                        f"{bufferbloat:.0f} ms bufferbloat indicates last-mile congestion."
                    ),
                })

        # (4) Throughput cap — measured download significantly below RUM baseline
        if rum is not None and download_mbps is not None:
            rum_dl = rum.get("dl_mbps")
            if rum_dl and download_mbps < rum_dl * 0.7:
                signals.append({
                    "condition": "throughput_cap",
                    "severity": "warning",
                    "detail": (
                        f"Measured download ({download_mbps:.0f} Mbps) is more than 30% below "
                        f"the Cloudflare RUM baseline for this ASN ({rum_dl:.0f} Mbps)."
                    ),
                })

        # (5) High jitter
        if jitter_ms is not None and jitter_ms > JITTER_WARNING_MS:
            signals.append({
                "condition": "high_jitter",
                "severity": "warning",
                "detail": (
                    f"Path jitter of {jitter_ms:.1f} ms exceeds the "
                    f"{JITTER_WARNING_MS:.1f} ms threshold, indicating unstable latency."
                ),
            })

        # (6) PMTU black-hole
        pmtu = result.get("pmtu") or {}
        if pmtu.get("blackhole"):
            signals.append({
                "condition": "pmtu_blackhole",
                "severity": "critical",
                "detail": (
                    "Large packets (1472-byte ICMP payload) are silently dropped while small "
                    "packets succeed, indicating a misconfigured MTU on the path."
                ),
            })

        # (7) Route flapping
        path_changes = result.get("path_changes")
        if path_changes is not None and path_changes > 0:
            signals.append({
                "condition": "route_flapping",
                "severity": "warning",
                "detail": (
                    f"AS path changed {path_changes} time(s) across consecutive probe cycles, "
                    "indicating route instability on the path."
                ),
            })

        # (8) TCP application latency
        tcp_connect_ms = result.get("tcp_connect_ms")
        if tcp_connect_ms is not None and tcp_connect_ms > TCP_LATENCY_WARNING_MS:
            signals.append({
                "condition": "tcp_latency",
                "severity": "warning",
                "detail": (
                    f"TCP connect latency of {tcp_connect_ms:.0f} ms exceeds the "
                    f"{TCP_LATENCY_WARNING_MS:.0f} ms threshold."
                ),
            })

        # (9) TLS application latency
        tls_handshake_ms = result.get("tls_handshake_ms")
        if tls_handshake_ms is not None and tls_handshake_ms > TLS_LATENCY_WARNING_MS:
            signals.append({
                "condition": "tls_latency",
                "severity": "warning",
                "detail": (
                    f"TLS handshake latency of {tls_handshake_ms:.0f} ms exceeds the "
                    f"{TLS_LATENCY_WARNING_MS:.0f} ms threshold."
                ),
            })

        if not signals:
            return {
                "verdict": "Healthy",
                "severity": "ok",
                "detail": "No anomalies detected on the measured path.",
                "signals": [],
                "partial_results": bool(probe_errors),
                "probe_errors": probe_errors,
            }

        worst_sev = max(signals, key=lambda s: _SEVERITY_ORDER.get(s["severity"], 0))["severity"]
        non_ok = [s for s in signals if s["severity"] != "ok"]
        top = (
            max(non_ok, key=lambda s: _SEVERITY_ORDER.get(s["severity"], 0))
            if non_ok else signals[0]
        )
        return {
            "verdict": _CONDITION_VERDICT.get(top["condition"], top["condition"]),
            "severity": worst_sev,
            "detail": top["detail"],
            "signals": signals,
            "partial_results": bool(probe_errors),
            "probe_errors": probe_errors,
        }

    except Exception:
        return {
            "verdict": "Healthy",
            "severity": "ok",
            "detail": "No anomalies detected on the measured path.",
            "signals": [],
            "partial_results": False,
            "probe_errors": {},
        }
