from netpath.diagnosis import diagnose


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
    assert any("rate_limited_hops" in s for s in result["signals"])


def test_high_jitter_warning():
    """jitter_ms above JITTER_WARNING_MS triggers High Jitter warning."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "8.8.8.8",    "Loss%": 0.0},
    ]
    result = diagnose({"jitter_ms": 15.0, "hubs": hubs})
    assert result["verdict"] == "High Jitter"
    assert result["severity"] == "warning"
    assert any("jitter" in s.lower() for s in result["signals"])


def test_jitter_below_threshold_is_healthy():
    """jitter_ms at or below threshold does not trigger a warning."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "8.8.8.8",    "Loss%": 0.0},
    ]
    result = diagnose({"jitter_ms": 9.9, "hubs": hubs})
    assert result["verdict"] == "Healthy"


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
    assert any("tcp" in s.lower() for s in result["signals"])


def test_tcp_latency_below_threshold_is_healthy():
    result = diagnose({"tcp_connect_ms": 150})
    assert result["verdict"] == "Healthy"


def test_tls_latency_warning():
    result = diagnose({"tls_handshake_ms": 600})
    assert result["severity"] == "warning"
    assert any("tls" in s.lower() for s in result["signals"])


def test_tls_latency_below_threshold_is_healthy():
    result = diagnose({"tls_handshake_ms": 400})
    assert result["verdict"] == "Healthy"


def test_incomplete_path_with_stall_hop():
    """path_complete=False fires Incomplete Path warning and includes stall_hop in signals."""
    result = diagnose({"path_complete": False, "stall_hop": 12, "hubs": []})
    assert result["verdict"] == "Incomplete Path"
    assert result["severity"] == "warning"
    assert any("stall_hop=12" in s for s in result["signals"])
    assert "hop 12" in result["detail"]


def test_incomplete_path_without_stall_hop():
    """path_complete=False without stall_hop still fires Incomplete Path warning."""
    result = diagnose({"path_complete": False, "hubs": []})
    assert result["verdict"] == "Incomplete Path"
    assert result["severity"] == "warning"
    assert any("path_complete=False" in s for s in result["signals"])
    assert "stall_hop" not in result["signals"][0]


def test_path_complete_none_is_healthy():
    """path_complete=None is treated as unknown — no Incomplete Path verdict."""
    result = diagnose({"path_complete": None, "hubs": []})
    assert result["verdict"] == "Healthy"


def test_path_complete_absent_is_healthy():
    """Missing path_complete key (asn subcommand) does not trigger Incomplete Path."""
    result = diagnose({"hubs": []})
    assert result["verdict"] == "Healthy"
