import json

from netpath.diagnosis import diagnose


def _signal(result, condition):
    return next(s for s in result["signals"] if s["condition"] == condition)


def _assert_signal_metadata(signal, source, confidence, evidence_items, sample_size=None):
    assert signal["source"] == source
    assert signal["confidence"] == confidence
    assert signal["evidence"]
    json.dumps(signal["evidence"])
    for key, value in evidence_items.items():
        assert signal["evidence"][key] == value
    if sample_size is not None:
        assert signal["sample_size"] == sample_size
    else:
        assert "sample_size" not in signal


def test_signal_metadata_for_major_conditions():
    hubs_loss = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1", "Loss%": 0.8},
        {"count": 3, "host": "8.8.8.8", "Loss%": 0.8},
    ]
    hubs_rate_limited = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1", "Loss%": 50.0},
        {"count": 3, "host": "8.8.8.8", "Loss%": 0.0},
    ]
    cases = [
        (
            {"path_complete": False, "stall_hop": 12, "hubs": []},
            "incomplete_path",
            "path",
            "medium",
            {"path_complete": False, "stall_hop": 12, "hop_count": 0},
            0,
        ),
        (
            {"bufferbloat_ms": 50},
            "severe_bufferbloat",
            "throughput",
            "high",
            {"bufferbloat_ms": 50, "threshold_ms": 30},
            None,
        ),
        (
            {"hubs": hubs_loss, "probe_count": 100},
            "mid_path_packet_loss",
            "local_trace",
            "medium",
            {"loss_threshold_pct": 0.5, "downstream_clean": False},
            100,
        ),
        (
            {"hubs": hubs_rate_limited, "probe_count": 10},
            "rate_limited_hop",
            "local_trace",
            "high",
            {"loss_threshold_pct": 5.0, "downstream_clean": True},
            10,
        ),
        (
            {"hubs": [{"count": 1, "host": "192.168.1.1", "Loss%": 5.0}], "bufferbloat_ms": 10, "probe_count": 10},
            "last_mile_congestion",
            "local_trace",
            "medium",
            {"bufferbloat_ms": 10, "bufferbloat_threshold_ms": 5},
            10,
        ),
        (
            {"rum": {"dl_mbps": 100}, "download_mbps": 50},
            "throughput_cap",
            "rum_compare",
            "medium",
            {"download_mbps": 50, "rum_dl_mbps": 100, "ratio": 0.5},
            None,
        ),
        (
            {"jitter_ms": 20.0, "probe_count": 5, "hubs": []},
            "high_jitter",
            "local_trace",
            "medium",
            {"jitter_ms": 20.0, "jitter_threshold_ms": 10.0},
            5,
        ),
        (
            {"jitter_ms": 20.0, "probe_count": 2, "hubs": []},
            "jitter_low_sample",
            "local_trace",
            "low",
            {"jitter_ms": 20.0, "min_samples": 5},
            2,
        ),
        (
            {"globalping": {"ping_jitter_ms": 25.0, "ping_packets": 16}},
            "high_jitter",
            "remote_globalping",
            "high",
            {"remote_jitter_ms": 25.0, "remote_packets": 16},
            16,
        ),
        (
            {"globalping": {"ping_loss_pct": 8.0, "ping_jitter_ms": 1.0, "ping_packets": 16}},
            "remote_packet_loss",
            "remote_globalping",
            "high",
            {"remote_loss_pct": 8.0, "loss_threshold_pct": 5.0, "remote_packets": 16},
            16,
        ),
        (
            {"pmtu": {"blackhole": True, "mtu_floor_bytes": 64}},
            "pmtu_blackhole",
            "pmtu",
            "high",
            {"blackhole": True, "large_payload_bytes": 1472, "mtu_floor_bytes": 64},
            None,
        ),
        (
            {"path_changes": 1, "ecmp_paths": 2, "ecmp_passes": 3},
            "route_flapping",
            "ecmp",
            "medium",
            {"path_changes": 1, "ecmp_paths": 2, "ecmp_passes": 3},
            3,
        ),
        (
            {"tcp_connect_ms": 250},
            "tcp_latency",
            "tcp",
            "high",
            {"tcp_connect_ms": 250, "threshold_ms": 200.0},
            None,
        ),
        (
            {"tls_handshake_ms": 600},
            "tls_latency",
            "tls",
            "high",
            {"tls_handshake_ms": 600, "threshold_ms": 500.0},
            None,
        ),
    ]
    for payload, condition, source, confidence, evidence, sample_size in cases:
        signal = _signal(diagnose(payload), condition)
        _assert_signal_metadata(signal, source, confidence, evidence, sample_size)


def test_healthy_default():
    result = diagnose({})
    assert result["verdict"] == "Healthy"
    assert result["severity"] == "ok"
    assert result["signals"] == []


def test_severe_bufferbloat():
    result = diagnose({"bufferbloat_ms": 50})
    assert result["verdict"] == "Severe Bufferbloat"
    assert result["severity"] == "critical"
    assert len(result["signals"]) > 0


def test_mid_path_packet_loss():
    # Hop 2 has loss AND downstream hop 3 also has loss — genuine congestion, not rate-limiting.
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 10.0},
        {"count": 3, "host": "8.8.8.8",    "Loss%": 8.0},
    ]
    result = diagnose({"hubs": hubs})
    assert result["verdict"] == "Mid-path Packet Loss"
    assert result["severity"] == "warning"
    assert len(result["signals"]) > 0


def test_last_mile_congestion():
    hubs = [{"count": 1, "host": "192.168.1.1", "Loss%": 5.0}]
    result = diagnose({"hubs": hubs, "bufferbloat_ms": 10})
    assert result["verdict"] == "Last-mile Congestion"
    assert result["severity"] == "warning"
    assert len(result["signals"]) > 0


def test_throughput_cap():
    result = diagnose({
        "rum": {"dl_mbps": 100},
        "download_mbps": 50,
    })
    assert result["verdict"] == "Throughput Cap"
    assert result["severity"] == "warning"
    assert len(result["signals"]) > 0


def test_rate_limited_hop_produces_healthy_not_mid_path_loss():
    # Hop 6 has 50% loss but hops 7-10 are all clean — ICMP rate limiting, not congestion.
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 0.0},
        {"count": 3, "host": "10.0.0.2",   "Loss%": 0.0},
        {"count": 4, "host": "10.0.0.3",   "Loss%": 0.0},
        {"count": 5, "host": "10.0.0.4",   "Loss%": 0.0},
        {"count": 6, "host": "203.0.113.1", "Loss%": 50.0},
        {"count": 7, "host": "203.0.113.2", "Loss%": 0.0},
        {"count": 8, "host": "203.0.113.3", "Loss%": 0.0},
        {"count": 9, "host": "203.0.113.4", "Loss%": 0.0},
        {"count": 10, "host": "8.8.8.8",    "Loss%": 0.0},
    ]
    result = diagnose({"hubs": hubs})
    assert result["verdict"] == "Healthy"
    assert result["severity"] == "ok"
    assert any(s["condition"] == "rate_limited_hop" for s in result["signals"])


def test_high_jitter_warning():
    """jitter_ms above JITTER_WARNING_MS triggers High Jitter warning."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "8.8.8.8",    "Loss%": 0.0},
    ]
    result = diagnose({"jitter_ms": 15.0, "hubs": hubs})
    assert result["verdict"] == "High Jitter"
    assert result["severity"] == "warning"
    assert any("jitter" in s["condition"] for s in result["signals"])


def test_jitter_below_threshold_is_healthy():
    """jitter_ms at or below threshold does not trigger a warning."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "8.8.8.8",    "Loss%": 0.0},
    ]
    result = diagnose({"jitter_ms": 9.9, "hubs": hubs})
    assert result["verdict"] == "Healthy"


def test_high_jitter_suppressed_below_min_samples():
    """jitter from only 2 probes yields an informational signal, not a High Jitter warning."""
    result = diagnose({"jitter_ms": 20.0, "probe_count": 2, "hubs": []})
    assert result["verdict"] == "Healthy"
    assert result["severity"] == "ok"
    assert any(s["condition"] == "jitter_low_sample" for s in result["signals"])
    assert not any(s["condition"] == "high_jitter" for s in result["signals"])


def test_high_jitter_fires_at_min_samples():
    """probe_count=5 is enough samples — the warning fires normally."""
    result = diagnose({"jitter_ms": 20.0, "probe_count": 5, "hubs": []})
    assert result["verdict"] == "High Jitter"
    assert result["severity"] == "warning"


def test_high_jitter_unchanged_at_mtr_default_samples():
    """probe_count=10 (mtr default cycles) keeps the existing warning behavior."""
    result = diagnose({"jitter_ms": 20.0, "probe_count": 10, "hubs": []})
    assert result["verdict"] == "High Jitter"
    assert result["severity"] == "warning"


def test_remote_clean_jitter_suppresses_local_high_jitter():
    """Clean near-target figures suppress a High Jitter warning sourced from the local trace."""
    result = diagnose({
        "jitter_ms": 20.0, "probe_count": 10, "hubs": [],
        "globalping": {"ping_jitter_ms": 1.2, "ping_loss_pct": 0.0, "ping_packets": 16},
    })
    assert result["verdict"] == "Healthy"
    assert not any(s["condition"] == "high_jitter" for s in result["signals"])
    notes = [s for s in result["signals"] if s["condition"] == "jitter_remote_clean"]
    assert notes and notes[0]["severity"] == "ok"
    assert "near-target" in notes[0]["detail"]


def test_remote_high_jitter_fires_citing_remote_figure():
    """Near-target jitter above the threshold fires High Jitter citing the remote value."""
    result = diagnose({
        "jitter_ms": 2.0, "probe_count": 10, "hubs": [],
        "globalping": {"ping_jitter_ms": 25.0, "ping_packets": 16},
    })
    assert result["verdict"] == "High Jitter"
    assert result["severity"] == "warning"
    sig = next(s for s in result["signals"] if s["condition"] == "high_jitter")
    assert "25.0" in sig["detail"]
    assert "Near-target" in sig["detail"]


def test_remote_loss_warning_fires_above_calibrated_threshold():
    """Near-target loss above the calibrated threshold emits a warning naming the source."""
    result = diagnose({
        "hubs": [],
        "globalping": {"ping_loss_pct": 8.0, "ping_jitter_ms": 1.0, "ping_packets": 16},
    })
    assert result["verdict"] == "Near-target Packet Loss"
    assert result["severity"] == "warning"
    sig = next(s for s in result["signals"] if s["condition"] == "remote_packet_loss")
    assert "Near-target" in sig["detail"]


def test_remote_jitter_suppression_does_not_hide_remote_loss():
    """Suppressing the jitter warning must not hide a genuine near-target loss warning."""
    result = diagnose({
        "jitter_ms": 20.0, "probe_count": 10, "hubs": [],
        "globalping": {"ping_jitter_ms": 1.0, "ping_loss_pct": 10.0, "ping_packets": 48},
    })
    conditions = [s["condition"] for s in result["signals"]]
    assert "high_jitter" not in conditions
    assert "remote_packet_loss" in conditions
    assert result["verdict"] == "Near-target Packet Loss"


def test_remote_figures_below_min_packets_fall_back_to_local():
    """Fewer than 5 remote packets is too small a sample — local behavior applies."""
    result = diagnose({
        "jitter_ms": 20.0, "probe_count": 10, "hubs": [],
        "globalping": {"ping_jitter_ms": 1.0, "ping_loss_pct": 0.0, "ping_packets": 3},
    })
    assert result["verdict"] == "High Jitter"
    assert result["severity"] == "warning"


def test_absent_or_malformed_remote_data_keeps_local_behavior():
    """Missing, None, empty, or partial globalping data degrades to the local-trace verdict."""
    for gp in (None, {}, "garbage", {"ping_rtt": {"avg": 4.2}}):
        result = diagnose({
            "jitter_ms": 20.0, "probe_count": 10, "hubs": [], "globalping": gp,
        })
        assert result["verdict"] == "High Jitter"
        assert result["severity"] == "warning"


def test_calibrated_loss_few_probes_no_alarm():
    """With probe_count < 20, 3% mid-path loss does not trigger Mid-path Packet Loss (threshold > 5%)."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 3.0},
        {"count": 3, "host": "8.8.8.8",    "Loss%": 0.0},
    ]
    result = diagnose({"hubs": hubs, "probe_count": 10})
    assert result["verdict"] == "Healthy"


def test_calibrated_loss_many_probes_strict_threshold():
    """With probe_count >= 100, 0.8% loss triggers Mid-path Packet Loss (threshold > 0.5%)."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 0.8},
        {"count": 3, "host": "8.8.8.8",    "Loss%": 0.8},
    ]
    result = diagnose({"hubs": hubs, "probe_count": 100})
    assert result["verdict"] == "Mid-path Packet Loss"
    assert result["severity"] == "warning"


def test_exception_input_returns_healthy():
    # bufferbloat_ms is a string — triggers TypeError in comparison, caught by except
    result = diagnose({"bufferbloat_ms": "not_a_number"})
    assert result["verdict"] == "Healthy"
    assert result["severity"] == "ok"


def test_pmtu_blackhole_triggers_critical():
    result = diagnose({"pmtu": {"blackhole": True, "mtu_floor_bytes": 64}})
    assert result["verdict"] == "PMTU Black-hole"
    assert result["severity"] == "critical"
    assert len(result["signals"]) > 0


def test_pmtu_no_blackhole_is_healthy():
    result = diagnose({"pmtu": {"blackhole": False, "mtu_floor_bytes": None}})
    assert result["verdict"] == "Healthy"


def test_route_flapping_warning():
    result = diagnose({"path_changes": 1})
    assert result["verdict"] == "Route Flapping"
    assert result["severity"] == "warning"
    assert len(result["signals"]) > 0


def test_route_flapping_zero_changes_is_healthy():
    result = diagnose({"path_changes": 0})
    assert result["verdict"] == "Healthy"


def test_tcp_latency_warning():
    result = diagnose({"tcp_connect_ms": 250})
    assert result["severity"] == "warning"
    assert any("tcp" in s["condition"] for s in result["signals"])


def test_tcp_latency_below_threshold_is_healthy():
    result = diagnose({"tcp_connect_ms": 150})
    assert result["verdict"] == "Healthy"


def test_tls_latency_warning():
    result = diagnose({"tls_handshake_ms": 600})
    assert result["severity"] == "warning"
    assert any("tls" in s["condition"] for s in result["signals"])


def test_tls_latency_below_threshold_is_healthy():
    result = diagnose({"tls_handshake_ms": 400})
    assert result["verdict"] == "Healthy"


def test_incomplete_path_with_stall_hop():
    """path_complete=False fires Incomplete Path warning and includes stall_hop in signals."""
    result = diagnose({"path_complete": False, "stall_hop": 12, "hubs": []})
    assert result["verdict"] == "Incomplete Path"
    assert result["severity"] == "warning"
    assert any("hop 12" in s["detail"] for s in result["signals"])
    assert "hop 12" in result["detail"]


def test_incomplete_path_without_stall_hop():
    """path_complete=False without stall_hop still fires Incomplete Path warning."""
    result = diagnose({"path_complete": False, "hubs": []})
    assert result["verdict"] == "Incomplete Path"
    assert result["severity"] == "warning"
    assert any(s["condition"] == "incomplete_path" for s in result["signals"])
    assert "stall_hop" not in result["signals"][0]["detail"]


def test_path_complete_none_is_healthy():
    """path_complete=None is treated as unknown — no Incomplete Path verdict."""
    result = diagnose({"path_complete": None, "hubs": []})
    assert result["verdict"] == "Healthy"


def test_path_complete_absent_is_healthy():
    """Missing path_complete key (asn subcommand) does not trigger Incomplete Path."""
    result = diagnose({"hubs": []})
    assert result["verdict"] == "Healthy"


def test_multiple_simultaneous_signals():
    """Two conditions present simultaneously both appear in signals list."""
    # bufferbloat_ms=50 triggers severe_bufferbloat (critical); jitter_ms=15 triggers high_jitter (warning)
    result = diagnose({"bufferbloat_ms": 50, "jitter_ms": 15.0, "hubs": []})
    assert len(result["signals"]) >= 2
    conditions = {s["condition"] for s in result["signals"]}
    assert "severe_bufferbloat" in conditions
    assert "high_jitter" in conditions
    # worst severity across all signals is critical
    assert result["severity"] == "critical"


def test_partial_results_set_when_probe_errors():
    """partial_results is True when probe_errors dict is non-empty."""
    result = diagnose({"probe_errors": {"iperf3": "timed out"}})
    assert result["partial_results"] is True


def test_partial_trace_timeout_reports_partial_results_with_path_data():
    """A timed-out trace that recovered partial hops still carries path data,
    and the recorded timeout makes diagnose() report partial_results."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 0.0},
    ]
    result = diagnose({
        "hubs": hubs,
        "as_path": ["AS65001", "AS65002"],
        "path_complete": False,
        "stall_hop": 2,
        "probe_errors": {"v4_trace": "timed out (partial path shown)"},
    })
    assert result["partial_results"] is True
    assert result["probe_errors"]["v4_trace"] == "timed out (partial path shown)"
    # The partial path still drives the normal incomplete-path analysis
    assert any(s["condition"] == "incomplete_path" for s in result["signals"])


def test_partial_results_false_when_no_probe_errors():
    """partial_results is False when probe_errors is absent or empty."""
    assert diagnose({})["partial_results"] is False
    assert diagnose({"probe_errors": {}})["partial_results"] is False


def test_icmp_filtered_path_all_stars():
    """path_complete=False with all-??? hubs produces icmp_filtered_path, severity ok."""
    hubs = [
        {"count": 1, "host": "???", "Loss%": 100.0},
        {"count": 2, "host": "???", "Loss%": 100.0},
        {"count": 3, "host": "???", "Loss%": 100.0},
    ]
    result = diagnose({"path_complete": False, "hubs": hubs})
    assert any(s["condition"] == "icmp_filtered_path" for s in result["signals"])
    icmp_signal = next(s for s in result["signals"] if s["condition"] == "icmp_filtered_path")
    assert icmp_signal["severity"] == "ok"


def test_icmp_filtered_path_trailing_stars():
    """path_complete=False with responsive hubs followed by ??? produces icmp_filtered_path, severity ok."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 0.0},
        {"count": 3, "host": "???",         "Loss%": 100.0},
        {"count": 4, "host": "???",         "Loss%": 100.0},
    ]
    result = diagnose({"path_complete": False, "hubs": hubs, "stall_hop": 2})
    assert any(s["condition"] == "icmp_filtered_path" for s in result["signals"])
    icmp_signal = next(s for s in result["signals"] if s["condition"] == "icmp_filtered_path")
    assert icmp_signal["severity"] == "ok"
    assert icmp_signal["evidence"]["filter_scope"] == "before_target_asn"
    assert "did not expose the target ASN" in icmp_signal["detail"]


def test_icmp_filtered_path_inside_target_asn_only_when_last_responsive_matches_target():
    hubs = [
        {"count": 1, "host": "192.168.1.1", "ASN": "AS64501", "Loss%": 0.0},
        {"count": 2, "host": "203.0.113.10", "ASN": "AS64500", "Loss%": 0.0},
        {"count": 3, "host": "???", "ASN": "AS???", "Loss%": 100.0},
    ]
    result = diagnose({"path_complete": False, "hubs": hubs, "stall_hop": 2, "target_asn": "AS64500"})

    icmp_signal = next(s for s in result["signals"] if s["condition"] == "icmp_filtered_path")
    assert icmp_signal["severity"] == "ok"
    assert icmp_signal["evidence"]["filter_scope"] == "target_asn"
    assert "inside the target ASN" in icmp_signal["detail"]


def test_incomplete_path_genuine_stall():
    """path_complete=False where last hub is responsive (stall_hop == max count) is still incomplete_path warning."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1",   "Loss%": 0.0},
        {"count": 3, "host": "10.0.0.2",   "Loss%": 0.0},
    ]
    result = diagnose({"path_complete": False, "hubs": hubs, "stall_hop": 3})
    assert any(s["condition"] == "incomplete_path" for s in result["signals"])
    inc_signal = next(s for s in result["signals"] if s["condition"] == "incomplete_path")
    assert inc_signal["severity"] == "warning"


def test_routing_loop_detected():
    """as_path with a repeated known ASN produces routing_loop warning."""
    result = diagnose({"as_path": ["AS1", "AS2", "AS3", "AS2"]})
    assert any(s["condition"] == "routing_loop" for s in result["signals"])
    loop_signal = next(s for s in result["signals"] if s["condition"] == "routing_loop")
    assert loop_signal["severity"] == "warning"
    assert result["verdict"] == "Routing Loop"


def test_routing_loop_no_repeat():
    """Unique AS path produces no routing_loop signal."""
    result = diagnose({"as_path": ["AS1", "AS2", "AS3", "AS4"]})
    assert not any(s["condition"] == "routing_loop" for s in result["signals"])


def test_remote_only_row_healthy():
    # A remote-only summary row: merged Globalping metrics plus optional RUM,
    # no hubs, no local trace, no throughput. Must produce a clean verdict
    # without raising and without spurious signals from absent local probes.
    row = {
        "asn": "AS64500",
        "name": "Remote Only ISP",
        "remote_only": True,
        "rum": None,
        "globalping": {
            "measurement_ids": {"ping": "p1", "mtr": "m1"},
            "ping_rtt": {"min": 5.0, "avg": 6.0, "max": 7.0},
            "ping_loss_pct": 0.0,
            "ping_jitter_ms": 1.2,
            "ping_packets": 48,
            "outbound_as_path": ["AS64500", "AS174"],
        },
    }
    result = diagnose(row)
    assert result["verdict"] == "Healthy"
    assert result["severity"] == "ok"
    assert result["signals"] == []


def test_remote_only_row_loss_sets_warning():
    # Globalping loss above threshold on a remote-only row must yield a warning
    # verdict so the row can raise the exit code.
    row = {
        "asn": "AS64500",
        "name": "Remote Only ISP",
        "remote_only": True,
        "globalping": {"ping_loss_pct": 12.5, "ping_jitter_ms": 1.0, "ping_packets": 48},
    }
    result = diagnose(row)
    assert result["verdict"] == "Near-target Packet Loss"
    assert result["severity"] == "warning"
