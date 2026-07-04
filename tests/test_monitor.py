import json

from netpath import monitor


def test_snapshot_from_result_extracts_monitor_metrics():
    result = {
        "path": [
            {"host": "192.0.2.1", "asn": "AS64501", "avg_ms": 5.0, "p95_ms": 6.0, "loss_pct": 0.0},
            {"host": "203.0.113.1", "asn": "AS64500", "avg_ms": 25.0, "p95_ms": 30.0, "loss_pct": 1.0},
        ],
        "throughput": {"download_mbps": 80.0, "upload_mbps": 10.0},
        "jitter_ms": 2.0,
        "path_changes": 0,
        "verdict": {"verdict": "Healthy", "severity": "ok"},
    }

    snapshot = monitor.snapshot_from_result(result, asn="AS64500", target_host="203.0.113.1")

    assert snapshot["as_path"] == ["AS64501", "AS64500"]
    assert snapshot["last_rtt_ms"] == 25.0
    assert snapshot["p95_rtt_ms"] == 30.0
    assert snapshot["loss_pct"] == 1.0
    assert snapshot["download_mbps"] == 80.0


def test_compare_snapshots_reports_core_regressions():
    previous = {
        "as_path": ["AS1", "AS2"],
        "p95_rtt_ms": 20.0,
        "loss_pct": 0.0,
        "download_mbps": 100.0,
        "severity": "ok",
    }
    current = {
        "as_path": ["AS1", "AS3", "AS2"],
        "p95_rtt_ms": 55.0,
        "loss_pct": 2.0,
        "download_mbps": 50.0,
        "severity": "warning",
        "verdict": "Near-target Packet Loss",
    }

    changes = monitor.compare_snapshots(previous, current)

    assert any("AS path changed" in change for change in changes)
    assert any("RTT regression" in change for change in changes)
    assert any("Packet loss increased" in change for change in changes)
    assert any("Download throughput dropped" in change for change in changes)
    assert any("Verdict worsened" in change for change in changes)


def test_history_round_trip(tmp_path):
    snapshot = {"asn": "AS64500", "timestamp": "now", "as_path": ["AS64500"]}

    path = monitor.append_snapshot(snapshot, str(tmp_path))

    assert path == tmp_path / "AS64500.jsonl"
    assert json.loads(path.read_text()) == snapshot
    assert monitor.load_latest("AS64500", str(tmp_path)) == snapshot
