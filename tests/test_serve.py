import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from netpath import serve


IDENTITY = {
    "ip": "203.0.113.7",
    "host": "203.0.113.7",
    "asn": "AS64501",
    "prefix": "203.0.113.0/24",
    "country": "GB",
    "name": "EXAMPLE-NET",
}


def test_detect_identity_uses_cymru_attribution():
    with patch("netpath.serve.get_public_ip", return_value="203.0.113.7"), \
         patch("netpath.serve.cymru_bulk_lookup_rich", return_value={
             "203.0.113.7": {"asn": "AS64501", "prefix": "203.0.113.0/24",
                             "country": "GB", "name": "EXAMPLE-NET"},
         }):
        identity = serve.detect_identity()
    assert identity == IDENTITY


def test_detect_identity_prefers_advertise_host():
    with patch("netpath.serve.get_public_ip", return_value="203.0.113.7"), \
         patch("netpath.serve.cymru_bulk_lookup_rich", return_value={}):
        identity = serve.detect_identity("iperf.example.com")
    assert identity["host"] == "iperf.example.com"
    assert identity["ip"] == "203.0.113.7"


def test_detect_identity_handles_offline_host():
    with patch("netpath.serve.get_public_ip", return_value=None):
        identity = serve.detect_identity()
    assert identity["host"] is None
    assert identity["asn"] is None


def test_build_entry_matches_public_list_schema():
    entry = serve.build_entry(IDENTITY, port=5202, site="London DC3")
    assert entry == {
        "IP/HOST": "203.0.113.7",
        "PORT": "5202",
        "OPTIONS": "-R, -u",
        "GB/S": "",
        "CONTINENT": "",
        "COUNTRY": "GB",
        "SITE": "London DC3",
        "PROVIDER": "EXAMPLE-NET",
    }


@pytest.mark.parametrize("port", [0, 65536])
def test_build_entry_rejects_invalid_port(port):
    with pytest.raises(ValueError, match="port must be between"):
        serve.build_entry(IDENTITY, port=port)


def test_register_local_prepends_and_replaces_same_host_port(tmp_path):
    path = tmp_path / "servers.json"
    serve.register_local({"IP/HOST": "other.example", "PORT": "5201"}, path)
    serve.register_local({"IP/HOST": "mine.example", "PORT": "5201", "SITE": "old"}, path)
    serve.register_local({"IP/HOST": "mine.example", "PORT": "5201", "SITE": "new"}, path)

    entries = json.loads(path.read_text())
    assert [(e["IP/HOST"], e.get("SITE")) for e in entries] == [
        ("mine.example", "new"),
        ("other.example", None),
    ]


def test_register_local_recovers_from_corrupt_file(tmp_path):
    path = tmp_path / "servers.json"
    path.write_text("{not json")
    serve.register_local({"IP/HOST": "mine.example", "PORT": "5201"}, path)
    assert json.loads(path.read_text())[0]["IP/HOST"] == "mine.example"
    assert path.stat().st_mode & 0o777 == 0o600


def test_srv_record_format():
    record = serve.srv_record("example.com", "iperf.example.com", 5201)
    assert record == "_netpath-iperf3._tcp.example.com. 3600 IN SRV 0 0 5201 iperf.example.com."


def test_suggest_srv_domain():
    assert serve.suggest_srv_domain("203.0.113.7") is None
    assert serve.suggest_srv_domain("example.com") == "example.com"
    assert serve.suggest_srv_domain("iperf.eu.example.com") == "eu.example.com"
    assert serve.suggest_srv_domain("localhost") is None


def test_emit_asset_substitutes_port():
    unit = serve.emit_asset("systemd", port=9201)
    assert "iperf3 -s -p 9201" in unit
    assert "5201" not in unit


@pytest.mark.parametrize("name", sorted(serve.DEPLOY_ASSETS))
def test_all_deploy_assets_are_packaged(name):
    assert serve.emit_asset(name).strip()


def test_emit_asset_rejects_unknown_name():
    with pytest.raises(KeyError):
        serve.emit_asset("kubernetes")


def test_announce_posts_entry():
    with patch("netpath.serve.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        serve.announce("https://registry.example/register", {"IP/HOST": "mine.example"})
    mock_post.assert_called_once_with(
        "https://registry.example/register",
        json={"IP/HOST": "mine.example"},
        timeout=15,
    )


def test_check_public_reachability_uses_completed_globalping_measurement():
    parsed = {"reachable": True, "reachable_probes": 2, "total_probes": 3, "probes": []}
    with patch(
        "netpath.serve.globalping.schedule_tcp_ping", return_value="measurement-id"
    ), patch(
        "netpath.serve.globalping.poll_until_done",
        return_value={"measurement-id": "finished"},
    ), patch(
        "netpath.serve.globalping.fetch_results", return_value=[{"result": {}}]
    ), patch(
        "netpath.serve.globalping.parse_tcp_reachability", return_value=parsed
    ):
        result = serve.check_public_reachability("iperf.example", 5201, "token")

    assert result["measurement_id"] == "measurement-id"
    assert result["reachable"] is True


def test_public_submission_url_prefills_server_request():
    entry = serve.build_entry(
        IDENTITY,
        site="Denver, CO",
        speed="1 Gbps",
        continent="North America",
    )

    url = serve.public_submission_url(entry)
    query = parse_qs(urlparse(url).query)

    assert query["template"] == ["new-iperf3-server-request.md"]
    assert query["title"] == ["[New Server]: 203.0.113.7"]
    assert "**IP / Hostname:** 203.0.113.7" in query["body"][0]
    assert "**Site:** Denver, CO" in query["body"][0]


def test_run_server_terminates_child_when_publish_callback_fails():
    process = MagicMock()
    with patch("netpath.serve.iperf_mod.available", return_value=True), \
         patch("netpath.serve.subprocess.Popen", return_value=process):
        with pytest.raises(RuntimeError, match="blocked"):
            serve.run_server(
                5201,
                on_started=lambda: (_ for _ in ()).throw(RuntimeError("blocked")),
            )

    process.terminate.assert_called_once()
    process.wait.assert_called_once()


def test_registry_tcp_check_rejects_private_resolution():
    from netpath.deploy import registry

    private = [(registry.socket.AF_INET, registry.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 5201))]
    with patch("netpath.deploy.registry.socket.getaddrinfo", return_value=private), \
         patch("netpath.deploy.registry.socket.socket") as socket_factory:
        assert registry._tcp_alive("attacker.example", 5201) is False

    socket_factory.assert_not_called()


def test_registry_tcp_check_connects_to_pinned_public_address():
    from netpath.deploy import registry

    public = [(registry.socket.AF_INET, registry.socket.SOCK_STREAM, 6, "", ("8.8.8.8", 5201))]
    with patch("netpath.deploy.registry.socket.getaddrinfo", return_value=public), \
         patch("netpath.deploy.registry.socket.socket") as socket_factory:
        connection = socket_factory.return_value.__enter__.return_value
        assert registry._tcp_alive("iperf.example", 5201) is True

    connection.connect.assert_called_once_with(("8.8.8.8", 5201))
