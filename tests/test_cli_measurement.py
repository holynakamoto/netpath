import pytest

from netpath import cli_measurement


def _result(severity=None, **extra):
    base = {"verdict": {"severity": severity} if severity else {}, "probe_errors": {}}
    base.update(extra)
    return base


@pytest.mark.parametrize("severity", ["warning", "critical"])
def test_should_escalate_true_for_non_ok_severity_with_real_asn(severity):
    assert cli_measurement._should_escalate_to_globalping(_result(severity), "AS64500")


def test_should_escalate_false_when_healthy():
    assert not cli_measurement._should_escalate_to_globalping(_result("ok"), "AS64500")


def test_should_escalate_false_without_a_real_target_asn():
    assert not cli_measurement._should_escalate_to_globalping(_result("critical"), "AS???")
    assert not cli_measurement._should_escalate_to_globalping(_result("critical"), None)


def test_should_escalate_false_when_verdict_missing():
    assert not cli_measurement._should_escalate_to_globalping({"probe_errors": {}}, "AS64500")


def test_escalate_populates_globalping_and_rediagnoses(monkeypatch):
    result = _result("warning", as_path=["AS1", "AS64500"], probe_count=50)

    monkeypatch.setattr(cli_measurement.globalping_mod, "get_public_ip", lambda: "203.0.113.5")
    monkeypatch.setattr(
        cli_measurement.globalping_mod, "schedule_measurements",
        lambda asn, target_ip, user_ip, token: {"ping": "ping-id", "mtr": "mtr-id"},
    )
    monkeypatch.setattr(
        cli_measurement.globalping_mod, "poll_until_done",
        lambda mids, token: {"ping-id": "finished", "mtr-id": "finished"},
    )
    monkeypatch.setattr(cli_measurement.globalping_mod, "fetch_results", lambda mid, token: [{"mid": mid}])
    monkeypatch.setattr(cli_measurement.globalping_mod, "parse_ping_rtt", lambda results: {"avg": 40.0})
    monkeypatch.setattr(
        cli_measurement.globalping_mod, "parse_ping_stats",
        lambda results: {"packets": 50, "loss_pct": 5.0, "jitter_ms": 2.0},
    )
    monkeypatch.setattr(cli_measurement.globalping_mod, "parse_mtr_as_path", lambda results: ["AS1", "AS64500"])

    cli_measurement._escalate_to_globalping(result, "203.0.113.10", "AS64500", None)

    assert result["globalping"]["ping_loss_pct"] == 5.0
    assert result["globalping"]["ping_jitter_ms"] == 2.0
    assert result["globalping"]["ping_packets"] == 50
    assert result["globalping"]["outbound_as_path"] == ["AS1", "AS64500"]
    assert any(s["condition"] == "remote_packet_loss" for s in result["verdict"]["signals"])


def test_escalate_records_probe_error_without_public_ip(monkeypatch):
    result = _result("warning")
    monkeypatch.setattr(cli_measurement.globalping_mod, "get_public_ip", lambda: None)

    cli_measurement._escalate_to_globalping(result, "203.0.113.10", "AS64500", None)

    assert "globalping" not in result
    assert "could not determine public IP" in result["probe_errors"]["globalping"]


def test_escalate_records_probe_error_on_schedule_failure(monkeypatch):
    result = _result("warning")
    monkeypatch.setattr(cli_measurement.globalping_mod, "get_public_ip", lambda: "203.0.113.5")

    def _raise(*args, **kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(cli_measurement.globalping_mod, "schedule_measurements", _raise)

    cli_measurement._escalate_to_globalping(result, "203.0.113.10", "AS64500", None)

    assert result["probe_errors"]["globalping"] == "rate limited"
    assert "globalping" not in result


def test_escalate_marks_timed_out_measurements(monkeypatch):
    result = _result("warning", as_path=[], probe_count=50)
    monkeypatch.setattr(cli_measurement.globalping_mod, "get_public_ip", lambda: "203.0.113.5")
    monkeypatch.setattr(
        cli_measurement.globalping_mod, "schedule_measurements",
        lambda asn, target_ip, user_ip, token: {"ping": "ping-id", "mtr": "mtr-id"},
    )
    monkeypatch.setattr(
        cli_measurement.globalping_mod, "poll_until_done",
        lambda mids, token: {"ping-id": "timed_out", "mtr-id": "timed_out"},
    )

    cli_measurement._escalate_to_globalping(result, "203.0.113.10", "AS64500", None)

    assert result["probe_errors"]["globalping"] == "timed out"
    assert result["globalping"] == {"measurement_ids": {"ping": "ping-id", "mtr": "mtr-id"}}
