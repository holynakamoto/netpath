from unittest.mock import MagicMock, patch

from netpath import telemetry


def test_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_STATE_PATH", tmp_path / "telemetry.json")
    assert telemetry.is_enabled() is False
    assert telemetry.status()["enabled"] is False


def test_set_enabled_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_STATE_PATH", tmp_path / "telemetry.json")
    telemetry.set_enabled(True)
    assert telemetry.is_enabled() is True
    telemetry.set_enabled(False)
    assert telemetry.is_enabled() is False


def test_capture_noops_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_STATE_PATH", tmp_path / "telemetry.json")
    monkeypatch.setenv("NETPATH_TELEMETRY_KEY", "phc_fake")
    with patch("netpath.telemetry._get_client") as get_client:
        telemetry.capture("ping", "success")
    get_client.assert_not_called()


def test_capture_noops_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_STATE_PATH", tmp_path / "telemetry.json")
    monkeypatch.setattr(telemetry, "_client", None)
    monkeypatch.setattr(telemetry, "_client_unavailable", False)
    monkeypatch.delenv("NETPATH_TELEMETRY_KEY", raising=False)
    telemetry.set_enabled(True)
    assert telemetry._get_client() is None


def test_capture_sends_only_check_type_and_result(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_STATE_PATH", tmp_path / "telemetry.json")
    monkeypatch.setenv("NETPATH_TELEMETRY_KEY", "phc_fake")
    telemetry.set_enabled(True)

    fake_client = MagicMock()
    with patch("netpath.telemetry._get_client", return_value=fake_client):
        telemetry.capture("ping", "success")

    fake_client.capture.assert_called_once()
    _, kwargs = fake_client.capture.call_args
    assert kwargs["event"] == "diagnostic_run"
    assert kwargs["properties"] == {"check_type": "ping", "result": "success"}
    assert isinstance(kwargs["distinct_id"], str) and kwargs["distinct_id"]


def test_get_client_builds_posthog_with_key_and_host(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_client", None)
    monkeypatch.setattr(telemetry, "_client_unavailable", False)
    monkeypatch.setenv("NETPATH_TELEMETRY_KEY", "phc_fake")
    fake_posthog_cls = MagicMock()
    fake_posthog_module = MagicMock(Posthog=fake_posthog_cls)
    with patch.dict("sys.modules", {"posthog": fake_posthog_module}):
        telemetry._get_client()
    fake_posthog_cls.assert_called_once_with("phc_fake", host="https://us.i.posthog.com")


def test_client_id_persists_across_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_STATE_PATH", tmp_path / "telemetry.json")
    first = telemetry._client_id()
    second = telemetry._client_id()
    assert first == second
