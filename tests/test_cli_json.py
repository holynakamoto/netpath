from netpath.cli_json import _json_recommendation


def test_recommendation_for_historical_segment_risk():
    verdict = {
        "signals": [
            {"condition": "historical_segment_risk", "severity": "warning"},
        ],
    }
    recommendation = _json_recommendation(verdict)
    assert "history of degraded performance" in recommendation


def test_recommendation_falls_back_when_no_signals():
    assert "No escalation needed" in _json_recommendation({"signals": []})
