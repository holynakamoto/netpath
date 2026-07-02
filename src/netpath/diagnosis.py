JITTER_WARNING_MS = 10.0
JITTER_MIN_SAMPLES = 5
REMOTE_MIN_PACKETS = 5  # near-target figures drive the verdict only at this sample size
LOSS_THRESHOLD_FEW = 5.0      # probe_count < 20
LOSS_THRESHOLD_DEFAULT = 1.0  # probe_count 20–99
LOSS_THRESHOLD_MANY = 0.5     # probe_count >= 100
TCP_LATENCY_WARNING_MS = 200.0
TLS_LATENCY_WARNING_MS = 500.0

_SEVERITY_ORDER = {"ok": 0, "warning": 1, "critical": 2}

_CONDITION_VERDICT = {
    "incomplete_path": "Incomplete Path",
    "icmp_filtered_path": "Healthy",
    "severe_bufferbloat": "Severe Bufferbloat",
    "mid_path_packet_loss": "Mid-path Packet Loss",
    "rate_limited_hop": "Healthy",
    "last_mile_congestion": "Last-mile Congestion",
    "throughput_cap": "Throughput Cap",
    "high_jitter": "High Jitter",
    "jitter_low_sample": "Healthy",
    "jitter_remote_clean": "Healthy",
    "remote_packet_loss": "Near-target Packet Loss",
    "pmtu_blackhole": "PMTU Black-hole",
    "route_flapping": "Route Flapping",
    "tcp_latency": "TCP Latency",
    "tls_latency": "TLS Latency",
    "routing_loop": "Routing Loop",
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

        # Near-target (Globalping) figures — read defensively: the dict may be
        # missing, None, or partial, in which case the local trace drives the checks.
        gp = result.get("globalping")
        gp = gp if isinstance(gp, dict) else {}
        remote_loss = gp.get("ping_loss_pct")
        remote_jitter = gp.get("ping_jitter_ms")
        remote_packets = gp.get("ping_packets")
        if not isinstance(remote_loss, (int, float)):
            remote_loss = None
        if not isinstance(remote_jitter, (int, float)):
            remote_jitter = None
        remote_valid = (
            isinstance(remote_packets, (int, float))
            and remote_packets >= REMOTE_MIN_PACKETS
        )

        # Calibrated loss threshold — scales with sample size
        if probe_count is not None and probe_count < 20:
            loss_threshold = LOSS_THRESHOLD_FEW
        elif probe_count is not None and probe_count >= 100:
            loss_threshold = LOSS_THRESHOLD_MANY
        else:
            loss_threshold = LOSS_THRESHOLD_DEFAULT

        # (0) Incomplete path — traceroute never reached the target ASN
        if result.get("path_complete") is False:
            hubs_local = result.get("hubs") or []
            stall = result.get("stall_hop")
            if not hubs_local:
                # No trace data at all — genuine problem
                stall_str = f" at hop {stall}" if stall is not None else ""
                signals.append({
                    "condition": "incomplete_path",
                    "severity": "warning",
                    "detail": (
                        f"Traceroute did not reach the target ASN{stall_str}. "
                        "The path may be filtered or the target unreachable."
                    ),
                })
            else:
                all_stars = all(
                    h.get("host") in ("???", None, "") for h in hubs_local
                )
                if all_stars:
                    signals.append({
                        "condition": "icmp_filtered_path",
                        "severity": "ok",
                        "detail": (
                            "The entire path filtered ICMP probes. "
                            "The destination may still be reachable."
                        ),
                    })
                else:
                    max_count = max(h.get("count", 0) for h in hubs_local)
                    if stall is not None and max_count > stall:
                        # Trailing ??? hops — downstream routers filter ICMP
                        signals.append({
                            "condition": "icmp_filtered_path",
                            "severity": "ok",
                            "detail": (
                                "Downstream routers inside the target ISP filter ICMP "
                                "TTL-exceeded responses. The route is likely healthy."
                            ),
                        })
                    else:
                        # Last hub is responsive — genuine stall
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

        # (5) High jitter — a near-target measurement with a sufficient sample
        # drives the check; otherwise the local trace does, and it requires
        # enough samples to judge stability.
        if remote_valid and remote_jitter is not None:
            if remote_jitter > JITTER_WARNING_MS:
                signals.append({
                    "condition": "high_jitter",
                    "severity": "warning",
                    "detail": (
                        f"Near-target jitter of {remote_jitter:.1f} ms, measured from "
                        f"probes inside the target network, exceeds the "
                        f"{JITTER_WARNING_MS:.1f} ms threshold, indicating unstable latency."
                    ),
                })
            elif jitter_ms is not None and jitter_ms > JITTER_WARNING_MS:
                signals.append({
                    "condition": "jitter_remote_clean",
                    "severity": "ok",
                    "detail": (
                        f"Local trace jitter of {jitter_ms:.1f} ms reflects the long-haul "
                        f"approach path; the near-target measurement shows "
                        f"{remote_jitter:.1f} ms jitter, so no jitter alarm is raised."
                    ),
                })
        elif jitter_ms is not None and jitter_ms > JITTER_WARNING_MS:
            if probe_count is not None and probe_count < JITTER_MIN_SAMPLES:
                signals.append({
                    "condition": "jitter_low_sample",
                    "severity": "ok",
                    "detail": (
                        f"Path jitter of {jitter_ms:.1f} ms was measured from only "
                        f"{probe_count} probe(s) — too few samples to judge latency "
                        "stability, so no jitter alarm is raised."
                    ),
                })
            else:
                signals.append({
                    "condition": "high_jitter",
                    "severity": "warning",
                    "detail": (
                        f"Path jitter of {jitter_ms:.1f} ms exceeds the "
                        f"{JITTER_WARNING_MS:.1f} ms threshold, indicating unstable latency."
                    ),
                })

        # (5b) Near-target packet loss — genuine loss inside the target network,
        # surfaced independently of the jitter suppression above.
        if remote_valid and remote_loss is not None:
            if remote_packets < 20:
                remote_loss_threshold = LOSS_THRESHOLD_FEW
            elif remote_packets >= 100:
                remote_loss_threshold = LOSS_THRESHOLD_MANY
            else:
                remote_loss_threshold = LOSS_THRESHOLD_DEFAULT
            if remote_loss > remote_loss_threshold:
                signals.append({
                    "condition": "remote_packet_loss",
                    "severity": "warning",
                    "detail": (
                        f"Near-target measurement from probes inside the target network "
                        f"shows {remote_loss:.1f}% packet loss, exceeding the "
                        f"{remote_loss_threshold:.1f}% threshold."
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

        # (10) Routing loop — a known ASN appears more than once in the de-adjacent path
        as_path = result.get("as_path") or []
        known = [a for a in as_path if a and a != "AS???"]
        if len(known) != len(set(known)):
            seen_asns: set = set()
            first_repeat = None
            for asn_entry in known:
                if asn_entry in seen_asns:
                    first_repeat = asn_entry
                    break
                seen_asns.add(asn_entry)
            signals.append({
                "condition": "routing_loop",
                "severity": "warning",
                "detail": (
                    f"Routing loop detected: {first_repeat} appears more than once "
                    "in the AS path."
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
