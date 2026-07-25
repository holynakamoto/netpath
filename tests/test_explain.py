from netpath import explain


def _result(**extra):
    base = {
        "path": [
            {"hop": 1, "host": "10.0.0.1", "asn": "AS1", "loss_pct": 0.0, "avg_ms": 5.0},
            {"hop": 2, "host": "203.0.113.1", "asn": "AS2", "loss_pct": 0.0, "avg_ms": 20.0},
        ],
        "verdict": {"verdict": "Healthy", "severity": "ok", "detail": "", "signals": []},
        "target_asn": "AS2",
        "target_host": "example.com",
    }
    base.update(extra)
    return base


def test_as_path_from_result_dedupes_and_skips_unknown():
    result = _result(path=[
        {"asn": "AS1"}, {"asn": "AS1"}, {"asn": "AS???"}, {"asn": "AS2"},
    ])
    assert explain.as_path_from_result(result) == ["AS1", "AS2"]


def test_build_report_includes_historical_context_field():
    report = explain.build_report(
        destination="example.com",
        result=_result(),
        historical_context="AS1 → AS2 showed degraded performance in 67% of 3 prior diagnoses.",
    )
    assert report["historical_context"] == "AS1 → AS2 showed degraded performance in 67% of 3 prior diagnoses."
    assert "Historical context: AS1 → AS2" in report["ticket_summary"]


def test_build_report_omits_historical_context_when_not_given():
    report = explain.build_report(destination="example.com", result=_result())
    assert report["historical_context"] is None
    assert "Historical context:" not in report["ticket_summary"]
