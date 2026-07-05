JITTER_WARNING_MS = 10.0
JITTER_MIN_SAMPLES = 5
REMOTE_MIN_PACKETS = 5  # near-target figures drive the verdict only at this sample size
LOSS_THRESHOLD_FEW = 5.0      # probe_count < 20
LOSS_THRESHOLD_DEFAULT = 1.0  # probe_count 20–99
LOSS_THRESHOLD_MANY = 0.5     # probe_count >= 100
TCP_LATENCY_WARNING_MS = 200.0
TLS_LATENCY_WARNING_MS = 500.0

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
_NO_SAMPLE = object()

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
    "dns_latency": "DNS Latency",
    "http_ttfb_latency": "HTTP Edge Latency",
}


def _signal(
    condition: str,
    severity: str,
    detail: str,
    source: str,
    confidence: str,
    evidence: dict,
    sample_size=_NO_SAMPLE,
) -> dict:
    signal = {
        "condition": condition,
        "severity": severity,
        "detail": detail,
        "source": source,
        "confidence": confidence,
        "evidence": evidence,
    }
    if sample_size is not _NO_SAMPLE and sample_size is not None:
        signal["sample_size"] = sample_size
    return signal


def _hop_evidence(hop: dict, index: int) -> dict:
    return {
        "hop_index": index + 1,
        "hop_count": hop.get("count"),
        "host": hop.get("host"),
        "asn": hop.get("ASN"),
        "loss_pct": float(hop.get("Loss%", 0.0) or 0.0),
    }


def _norm_asn(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return text if text.startswith("AS") else f"AS{text}"


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
                signals.append(_signal(
                    "incomplete_path",
                    "warning",
                    (
                        f"Traceroute did not reach the target ASN{stall_str}. "
                        "The path may be filtered or the target unreachable."
                    ),
                    "path",
                    CONFIDENCE_MEDIUM,
                    {
                        "path_complete": False,
                        "stall_hop": stall,
                        "responsive_hops": 0,
                        "hop_count": 0,
                    },
                    sample_size=0,
                ))
            else:
                all_stars = all(
                    h.get("host") in ("???", None, "") for h in hubs_local
                )
                if all_stars:
                    signals.append(_signal(
                        "icmp_filtered_path",
                        "ok",
                        (
                            "The entire path filtered ICMP probes. "
                            "The destination may still be reachable."
                        ),
                        "path",
                        CONFIDENCE_MEDIUM,
                        {
                            "path_complete": False,
                            "stall_hop": stall,
                            "responsive_hops": 0,
                            "hop_count": len(hubs_local),
                            "filtered_hops": len(hubs_local),
                        },
                        sample_size=len(hubs_local),
                    ))
                else:
                    max_count = max(h.get("count", 0) for h in hubs_local)
                    responsive_hops = [
                        h for h in hubs_local if h.get("host") not in ("???", None, "")
                    ]
                    if stall is not None and max_count > stall:
                        # Trailing ??? hops — downstream routers filter ICMP
                        last_responsive = responsive_hops[-1] if responsive_hops else {}
                        last_asn = _norm_asn(last_responsive.get("ASN"))
                        last_known_asn = None
                        for hop in reversed(responsive_hops):
                            candidate = _norm_asn(hop.get("ASN"))
                            if candidate and candidate != "AS???":
                                last_known_asn = candidate
                                break
                        target_asn = _norm_asn(result.get("target_asn"))
                        if target_asn and last_asn == target_asn:
                            detail = (
                                "Downstream routers inside the target ASN filter ICMP "
                                "TTL-exceeded responses. The route is likely healthy."
                            )
                            filter_scope = "target_asn"
                        else:
                            target_part = f" {target_asn}" if target_asn else ""
                            last_part = f" after {last_known_asn}" if last_known_asn else ""
                            detail = (
                                f"Traceroute did not expose the target ASN{target_part}; "
                                f"ICMP TTL-exceeded responses are filtered{last_part}. "
                                "The endpoint may still be reachable by TCP/HTTPS."
                            )
                            filter_scope = "before_target_asn"
                        signals.append(_signal(
                            "icmp_filtered_path",
                            "ok",
                            detail,
                            "path",
                            CONFIDENCE_MEDIUM,
                            {
                                "path_complete": False,
                                "stall_hop": stall,
                                "max_hop_count": max_count,
                                "responsive_hops": len(responsive_hops),
                                "hop_count": len(hubs_local),
                                "trailing_filtered_hops": max_count - stall,
                                "filter_scope": filter_scope,
                                "last_responsive_asn": last_asn,
                                "last_known_asn": last_known_asn,
                                "target_asn": target_asn,
                            },
                            sample_size=len(hubs_local),
                        ))
                    else:
                        # Last hub is responsive — genuine stall
                        stall_str = f" at hop {stall}" if stall is not None else ""
                        signals.append(_signal(
                            "incomplete_path",
                            "warning",
                            (
                                f"Traceroute did not reach the target ASN{stall_str}. "
                                "The path may be filtered or the target unreachable."
                            ),
                            "path",
                            CONFIDENCE_MEDIUM,
                            {
                                "path_complete": False,
                                "stall_hop": stall,
                                "max_hop_count": max_count,
                                "responsive_hops": len(responsive_hops),
                                "hop_count": len(hubs_local),
                            },
                            sample_size=len(hubs_local),
                        ))

        # (1) Severe bufferbloat
        if bufferbloat is not None and bufferbloat > 30:
            signals.append(_signal(
                "severe_bufferbloat",
                "critical",
                (
                    f"Latency rose {bufferbloat:.0f} ms under load, "
                    "indicating severe queuing congestion on the path."
                ),
                "throughput",
                CONFIDENCE_HIGH,
                {
                    "bufferbloat_ms": bufferbloat,
                    "threshold_ms": 30,
                },
            ))

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
                    downstream = [
                        dh for j, dh in enumerate(hubs)
                        if j > i and dh.get("host") not in ("???", None, "")
                    ]
                    downstream_clean = all(
                        float(dh.get("Loss%", 0.0) or 0.0) <= loss_threshold
                        for dh in downstream
                    )
                    if downstream_clean:
                        signals.append(_signal(
                            "rate_limited_hop",
                            "ok",
                            (
                                "No end-to-end anomalies detected. One or more "
                                "transit hops appear to rate-limit ICMP probes."
                            ),
                            "local_trace",
                            CONFIDENCE_HIGH,
                            {
                                "loss_hop": _hop_evidence(h, i),
                                "loss_threshold_pct": loss_threshold,
                                "downstream_responsive_hops": len(downstream),
                                "downstream_clean": True,
                            },
                            sample_size=probe_count,
                        ))
                    else:
                        hop_id = h.get("host", f"hop {i + 1}")
                        downstream_loss = [
                            float(dh.get("Loss%", 0.0) or 0.0) for dh in downstream
                        ]
                        signals.append(_signal(
                            "mid_path_packet_loss",
                            "warning",
                            (
                                f"Packet loss of {loss:.1f}% detected at {hop_id}, "
                                "suggesting a congested or faulty intermediate hop."
                            ),
                            "local_trace",
                            CONFIDENCE_MEDIUM,
                            {
                                "loss_hop": _hop_evidence(h, i),
                                "loss_threshold_pct": loss_threshold,
                                "downstream_loss_pct": downstream_loss,
                                "downstream_clean": False,
                            },
                            sample_size=probe_count,
                        ))
                    break

        # (3) Last-mile congestion — first hop loss combined with bufferbloat
        if hubs:
            first_loss = float(hubs[0].get("Loss%", 0.0) or 0.0)
            if first_loss > 0 and bufferbloat is not None and bufferbloat > 5:
                signals.append(_signal(
                    "last_mile_congestion",
                    "warning",
                    (
                        f"First-hop loss of {first_loss:.1f}% combined with "
                        f"{bufferbloat:.0f} ms bufferbloat indicates last-mile congestion."
                    ),
                    "local_trace",
                    CONFIDENCE_MEDIUM,
                    {
                        "first_hop": _hop_evidence(hubs[0], 0),
                        "bufferbloat_ms": bufferbloat,
                        "bufferbloat_threshold_ms": 5,
                    },
                    sample_size=probe_count,
                ))

        # (4) Throughput cap — measured download significantly below RUM baseline
        if rum is not None and download_mbps is not None:
            rum_dl = rum.get("dl_mbps")
            if rum_dl and download_mbps < rum_dl * 0.7:
                signals.append(_signal(
                    "throughput_cap",
                    "warning",
                    (
                        f"Measured download ({download_mbps:.0f} Mbps) is more than "
                        "30% below the Cloudflare RUM baseline for this ASN "
                        f"({rum_dl:.0f} Mbps)."
                    ),
                    "rum_compare",
                    CONFIDENCE_MEDIUM,
                    {
                        "download_mbps": download_mbps,
                        "rum_dl_mbps": rum_dl,
                        "ratio": download_mbps / rum_dl,
                        "threshold_ratio": 0.7,
                    },
                ))

        # (5) High jitter — a near-target measurement with a sufficient sample
        # drives the check; otherwise the local trace does, and it requires
        # enough samples to judge stability.
        if remote_valid and remote_jitter is not None:
            if remote_jitter > JITTER_WARNING_MS:
                signals.append(_signal(
                    "high_jitter",
                    "warning",
                    (
                        f"Near-target jitter of {remote_jitter:.1f} ms, measured from "
                        "probes inside the target network, exceeds the "
                        f"{JITTER_WARNING_MS:.1f} ms threshold, indicating unstable latency."
                    ),
                    "remote_globalping",
                    CONFIDENCE_HIGH,
                    {
                        "remote_jitter_ms": remote_jitter,
                        "jitter_threshold_ms": JITTER_WARNING_MS,
                        "remote_packets": remote_packets,
                    },
                    sample_size=remote_packets,
                ))
            elif jitter_ms is not None and jitter_ms > JITTER_WARNING_MS:
                signals.append(_signal(
                    "jitter_remote_clean",
                    "ok",
                    (
                        f"Local trace jitter of {jitter_ms:.1f} ms reflects the long-haul "
                        "approach path; the near-target measurement shows "
                        f"{remote_jitter:.1f} ms jitter, so no jitter alarm is raised."
                    ),
                    "remote_globalping",
                    CONFIDENCE_HIGH,
                    {
                        "local_jitter_ms": jitter_ms,
                        "remote_jitter_ms": remote_jitter,
                        "jitter_threshold_ms": JITTER_WARNING_MS,
                        "remote_packets": remote_packets,
                    },
                    sample_size=remote_packets,
                ))
        elif jitter_ms is not None and jitter_ms > JITTER_WARNING_MS:
            if probe_count is not None and probe_count < JITTER_MIN_SAMPLES:
                signals.append(_signal(
                    "jitter_low_sample",
                    "ok",
                    (
                        f"Path jitter of {jitter_ms:.1f} ms was measured from only "
                        f"{probe_count} probe(s) — too few samples to judge latency "
                        "stability, so no jitter alarm is raised."
                    ),
                    "local_trace",
                    CONFIDENCE_LOW,
                    {
                        "jitter_ms": jitter_ms,
                        "jitter_threshold_ms": JITTER_WARNING_MS,
                        "min_samples": JITTER_MIN_SAMPLES,
                    },
                    sample_size=probe_count,
                ))
            else:
                signals.append(_signal(
                    "high_jitter",
                    "warning",
                    (
                        f"Path jitter of {jitter_ms:.1f} ms exceeds the "
                        f"{JITTER_WARNING_MS:.1f} ms threshold, indicating unstable latency."
                    ),
                    "local_trace",
                    CONFIDENCE_MEDIUM,
                    {
                        "jitter_ms": jitter_ms,
                        "jitter_threshold_ms": JITTER_WARNING_MS,
                    },
                    sample_size=probe_count,
                ))

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
                signals.append(_signal(
                    "remote_packet_loss",
                    "warning",
                    (
                        "Near-target measurement from probes inside the target network "
                        f"shows {remote_loss:.1f}% packet loss, exceeding the "
                        f"{remote_loss_threshold:.1f}% threshold."
                    ),
                    "remote_globalping",
                    CONFIDENCE_HIGH,
                    {
                        "remote_loss_pct": remote_loss,
                        "loss_threshold_pct": remote_loss_threshold,
                        "remote_packets": remote_packets,
                    },
                    sample_size=remote_packets,
                ))

        # (6) PMTU black-hole
        pmtu = result.get("pmtu") or {}
        if pmtu.get("blackhole"):
            signals.append(_signal(
                "pmtu_blackhole",
                "critical",
                (
                    "Large packets (1472-byte ICMP payload) are silently dropped while "
                    "small packets succeed, indicating a misconfigured MTU on the path."
                ),
                "pmtu",
                CONFIDENCE_HIGH,
                {
                    "blackhole": True,
                    "large_payload_bytes": 1472,
                    "mtu_floor_bytes": pmtu.get("mtu_floor_bytes"),
                },
            ))

        # (7) Route flapping
        path_changes = result.get("path_changes")
        if path_changes is not None and path_changes > 0:
            ecmp_passes = result.get("ecmp_passes")
            if ecmp_passes is None:
                ecmp_passes = path_changes + 1
            signals.append(_signal(
                "route_flapping",
                "warning",
                (
                    f"AS path changed {path_changes} time(s) across consecutive probe cycles, "
                    "indicating route instability on the path."
                ),
                "ecmp",
                CONFIDENCE_MEDIUM,
                {
                    "path_changes": path_changes,
                    "ecmp_paths": result.get("ecmp_paths"),
                    "ecmp_passes": ecmp_passes,
                },
                sample_size=ecmp_passes,
            ))

        # (8) TCP application latency
        tcp_connect_ms = result.get("tcp_connect_ms")
        if tcp_connect_ms is not None and tcp_connect_ms > TCP_LATENCY_WARNING_MS:
            signals.append(_signal(
                "tcp_latency",
                "warning",
                (
                    f"TCP connect latency of {tcp_connect_ms:.0f} ms exceeds the "
                    f"{TCP_LATENCY_WARNING_MS:.0f} ms threshold."
                ),
                "tcp",
                CONFIDENCE_HIGH,
                {
                    "tcp_connect_ms": tcp_connect_ms,
                    "threshold_ms": TCP_LATENCY_WARNING_MS,
                },
            ))

        # (9) TLS application latency
        tls_handshake_ms = result.get("tls_handshake_ms")
        if tls_handshake_ms is not None and tls_handshake_ms > TLS_LATENCY_WARNING_MS:
            signals.append(_signal(
                "tls_latency",
                "warning",
                (
                    f"TLS handshake latency of {tls_handshake_ms:.0f} ms exceeds the "
                    f"{TLS_LATENCY_WARNING_MS:.0f} ms threshold."
                ),
                "tls",
                CONFIDENCE_HIGH,
                {
                    "tls_handshake_ms": tls_handshake_ms,
                    "threshold_ms": TLS_LATENCY_WARNING_MS,
                },
            ))

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
            signals.append(_signal(
                "routing_loop",
                "warning",
                (
                    f"Routing loop detected: {first_repeat} appears more than once "
                    "in the AS path."
                ),
                "path",
                CONFIDENCE_MEDIUM,
                {
                    "as_path": known,
                    "repeated_asn": first_repeat,
                    "path_length": len(known),
                },
                sample_size=len(known),
            ))

        dns = result.get("dns") or {}
        dns_ms = dns.get("lookup_ms")
        if dns_ms is not None and dns_ms > 250:
            signals.append(_signal(
                "dns_latency",
                "warning",
                f"DNS lookup took {dns_ms:.0f} ms, which can delay application setup before the network path is used.",
                "dns",
                CONFIDENCE_MEDIUM,
                {
                    "lookup_ms": dns_ms,
                    "threshold_ms": 250.0,
                    "resolver_ips": dns.get("resolver_ips") or [],
                },
            ))

        edge = result.get("http_edge") or {}
        ttfb_ms = edge.get("ttfb_ms")
        if ttfb_ms is not None and ttfb_ms > 1000:
            signals.append(_signal(
                "http_ttfb_latency",
                "warning",
                f"HTTPS time-to-first-byte was {ttfb_ms:.0f} ms, pointing to application edge or origin delay.",
                "http_edge",
                CONFIDENCE_MEDIUM,
                {
                    "ttfb_ms": ttfb_ms,
                    "threshold_ms": 1000.0,
                    "status_code": edge.get("status_code"),
                    "redirect_count": edge.get("redirect_count"),
                },
            ))

        if not signals:
            return {
                "verdict": "Healthy",
                "severity": "ok",
                "detail": "No anomalies detected on the measured path.",
                "signals": [],
                "partial_results": bool(probe_errors),
                "probe_errors": probe_errors,
            }

        worst_sev = max(signals, key=lambda s: _SEVERITY_ORDER.get(s["severity"], 0))[
            "severity"
        ]
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
