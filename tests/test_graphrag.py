from unittest.mock import patch

from netpath import graphrag, monitor


def _snapshot(as_path, severity, timestamp="2026-01-01T00:00:00Z"):
    return {
        "as_path": as_path,
        "severity": severity,
        "timestamp": timestamp,
        "monitor_key": as_path[-1] if as_path else "unknown",
        "asn": as_path[-1] if as_path else "AS???",
    }


def test_retrieve_segment_facts_reuses_kg(tmp_path):
    for severity in ("critical", "critical", "ok"):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], severity), path=str(tmp_path))

    facts = graphrag.retrieve_segment_facts(["AS1", "AS2"], store_path=str(tmp_path))

    assert len(facts) == 1
    assert facts[0]["upstream"] == "AS1"
    assert facts[0]["downstream"] == "AS2"


def test_historical_context_without_provider_is_deterministic(tmp_path):
    for severity in ("critical", "critical", "ok"):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], severity), path=str(tmp_path))

    text = graphrag.historical_context(["AS1", "AS2"], store_path=str(tmp_path))

    assert "AS1 → AS2" in text
    assert "67%" in text


def test_historical_context_reports_no_history_plainly(tmp_path):
    text = graphrag.historical_context(["AS1", "AS2"], store_path=str(tmp_path))
    assert "No prior history" in text


def test_historical_context_never_calls_llm_without_a_provider(tmp_path):
    with patch("netpath.graphrag.llm_cli.run_schema_constrained") as run:
        graphrag.historical_context(["AS1", "AS2"], store_path=str(tmp_path))
    run.assert_not_called()


def test_historical_context_uses_generated_narrative_when_available(tmp_path):
    for severity in ("critical", "critical", "ok"):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], severity), path=str(tmp_path))

    with patch(
        "netpath.graphrag.llm_cli.run_schema_constrained",
        return_value={"narrative": "AS1 to AS2 has a rocky history."},
    ):
        text = graphrag.historical_context(["AS1", "AS2"], provider="claude", store_path=str(tmp_path))

    assert text == "AS1 to AS2 has a rocky history."


def test_historical_context_falls_back_when_generation_fails(tmp_path):
    for severity in ("critical", "critical", "ok"):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], severity), path=str(tmp_path))

    with patch("netpath.graphrag.llm_cli.run_schema_constrained", return_value=None):
        text = graphrag.historical_context(["AS1", "AS2"], provider="claude", store_path=str(tmp_path))

    assert "AS1 → AS2" in text


def test_historical_context_falls_back_on_empty_narrative(tmp_path):
    for severity in ("critical", "critical", "ok"):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], severity), path=str(tmp_path))

    with patch(
        "netpath.graphrag.llm_cli.run_schema_constrained",
        return_value={"narrative": "   "},
    ):
        text = graphrag.historical_context(["AS1", "AS2"], provider="claude", store_path=str(tmp_path))

    assert "AS1 → AS2" in text
