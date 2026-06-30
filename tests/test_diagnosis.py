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
    hubs = [
        {"count": 1, "host": "192.168.1.1", "Loss%": 0.0},
        {"count": 2, "host": "10.0.0.1", "Loss%": 10.0},
        {"count": 3, "host": "8.8.8.8", "Loss%": 0.0},
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


def test_exception_input_returns_healthy():
    # bufferbloat_ms is a string — triggers TypeError in comparison, caught by except
    result = diagnose({"bufferbloat_ms": "not_a_number"})
    assert result["verdict"] == "Healthy"
    assert result["severity"] == "ok"
