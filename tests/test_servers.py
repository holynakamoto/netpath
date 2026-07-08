import json
from unittest.mock import patch, MagicMock

import pytest
import requests

from netpath import servers
from netpath.servers import (
    _doh_srv_query,
    _fetch_and_resolve,
    _is_iperf3_alive,
    _tcp_alive,
    find_advertised_server,
    find_servers_in_asn,
)


def test_tcp_alive_returns_false_on_oserror():
    with patch("netpath.servers.socket.create_connection", side_effect=OSError("refused")):
        assert _tcp_alive("192.0.2.1", 5201) is False


def test_tcp_alive_returns_true_on_success():
    with patch("netpath.servers.socket.create_connection") as m:
        m.return_value.__enter__ = lambda s: s
        m.return_value.__exit__ = lambda s, *a: None
        m.return_value.close = lambda: None
        assert _tcp_alive("192.0.2.1", 5201) is True


def test_is_iperf3_alive_true_on_zero_exit_valid_json():
    good_output = json.dumps({"end": {"sum_sent": {"bits_per_second": 100}}})
    with patch("netpath.servers._iperf") as mock_iperf, \
         patch("netpath.servers.subprocess.run") as mock_run:
        mock_iperf.available.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout=good_output, stderr="")
        assert _is_iperf3_alive("192.0.2.1", 5201) is True


def test_is_iperf3_alive_false_on_nonzero_exit():
    error_output = json.dumps({"error": "unable to connect"})
    with patch("netpath.servers._iperf") as mock_iperf, \
         patch("netpath.servers.subprocess.run") as mock_run:
        mock_iperf.available.return_value = True
        mock_run.return_value = MagicMock(returncode=1, stdout=error_output, stderr="")
        assert _is_iperf3_alive("192.0.2.1", 5201) is False


def test_is_iperf3_alive_false_when_json_has_error_field():
    error_output = json.dumps({"error": "iperf3: error - unable to connect to server: Connection refused"})
    with patch("netpath.servers._iperf") as mock_iperf, \
         patch("netpath.servers.subprocess.run") as mock_run:
        mock_iperf.available.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout=error_output, stderr="")
        assert _is_iperf3_alive("192.0.2.1", 5201) is False


def test_is_iperf3_alive_falls_back_to_tcp_when_iperf3_absent():
    with patch("netpath.servers._iperf") as mock_iperf, \
         patch("netpath.servers._tcp_alive") as mock_tcp:
        mock_iperf.available.return_value = False
        mock_tcp.return_value = True
        result = _is_iperf3_alive("192.0.2.1", 5201)
        mock_tcp.assert_called_once_with("192.0.2.1", 5201)
        assert result is True


def test_is_iperf3_alive_false_on_timeout():
    import subprocess
    with patch("netpath.servers._iperf") as mock_iperf, \
         patch("netpath.servers.subprocess.run", side_effect=subprocess.TimeoutExpired("iperf3", 15)):
        mock_iperf.available.return_value = True
        assert _is_iperf3_alive("192.0.2.1", 5201) is False


def _make_server(asn: str, ip: str) -> dict:
    return {"asn": asn, "ip": ip, "port": 5201, "HOST": ip}


def test_find_servers_in_asn_checks_all_candidates_before_truncating():
    """Dead servers earlier in the list do not prevent live servers from being returned."""
    servers = [
        _make_server("AS64501", f"dead{i}.example" ) for i in range(3)
    ] + [
        _make_server("AS64501", "live1.example"),
        _make_server("AS64501", "live2.example"),
    ]
    # first 3 are dead, last 2 are alive
    def liveness(ip, port):
        return ip in ("live1.example", "live2.example")

    with patch("netpath.servers._fetch_and_resolve", return_value=servers), \
         patch("netpath.servers._is_iperf3_alive", side_effect=liveness):
        result = find_servers_in_asn("AS64501", max_count=3)

    assert len(result) == 2
    assert all(s["ip"] in ("live1.example", "live2.example") for s in result)


def test_find_servers_in_asn_respects_max_count_after_filter():
    """max_count truncation applies after liveness filter, not before."""
    servers = [_make_server("AS64501", f"live{i}.example") for i in range(5)]

    with patch("netpath.servers._fetch_and_resolve", return_value=servers), \
         patch("netpath.servers._is_iperf3_alive", return_value=True):
        result = find_servers_in_asn("AS64501", max_count=3)

    assert len(result) == 3


def test_find_servers_in_asn_excludes_server_failing_iperf3_protocol():
    """A server passing TCP connect but failing iperf3 -t 1 is excluded."""
    servers = [
        _make_server("AS64501", "tcp-only.example"),
        _make_server("AS64501", "good.example"),
    ]

    def liveness(ip, port):
        return ip == "good.example"

    with patch("netpath.servers._fetch_and_resolve", return_value=servers), \
         patch("netpath.servers._is_iperf3_alive", side_effect=liveness):
        result = find_servers_in_asn("AS64501", max_count=3)

    assert len(result) == 1
    assert result[0]["ip"] == "good.example"


# ── source merging (local registry / custom URLs / public list) ──────────────

@pytest.fixture
def _no_cache():
    servers._resolved_cache = None
    yield
    servers._resolved_cache = None


def _entry(host: str) -> dict:
    return {"IP/HOST": host, "PORT": "5201"}


def _resolve_passthrough(hosts):
    return {h: f"ip-{h}" for h in hosts}


def test_fetch_and_resolve_prefers_local_and_custom_over_public(_no_cache):
    """Self-hosted entries come first and shadow public entries for the same host."""
    with patch("netpath.servers._load_local_registry", return_value=[_entry("mine.example")]), \
         patch("netpath.servers._fetch_extra_lists", return_value=[_entry("org.example"), _entry("mine.example")]), \
         patch("netpath.servers._fetch_public_list", return_value=[_entry("public.example"), _entry("mine.example")]), \
         patch("netpath.servers.resolve_hosts_parallel", side_effect=_resolve_passthrough), \
         patch("netpath.servers.cymru_bulk_lookup", return_value={}):
        result = _fetch_and_resolve()

    hosts = [s["HOST"] for s in result]
    assert hosts == ["mine.example", "org.example", "public.example"]
    assert [s["source"] for s in result] == ["local", "custom", "public"]


def test_fetch_and_resolve_keeps_same_host_on_distinct_ports(_no_cache):
    with patch("netpath.servers._load_local_registry", return_value=[
        {"IP/HOST": "mine.example", "PORT": "5201"},
        {"IP/HOST": "mine.example", "PORT": "5202"},
    ]), patch(
        "netpath.servers._fetch_extra_lists", return_value=[]
    ), patch(
        "netpath.servers._fetch_public_list", return_value=[]
    ), patch(
        "netpath.servers.resolve_hosts_parallel", side_effect=_resolve_passthrough
    ), patch(
        "netpath.servers.cymru_bulk_lookup", return_value={}
    ):
        result = _fetch_and_resolve()

    assert [(server["HOST"], server["port"]) for server in result] == [
        ("mine.example", 5201),
        ("mine.example", 5202),
    ]


def test_fetch_and_resolve_survives_public_list_outage_with_local_servers(_no_cache):
    def public_raises(have_other_sources):
        assert have_other_sources
        return []

    with patch("netpath.servers._load_local_registry", return_value=[_entry("mine.example")]), \
         patch("netpath.servers._fetch_extra_lists", return_value=[]), \
         patch("netpath.servers._fetch_public_list", side_effect=public_raises), \
         patch("netpath.servers.resolve_hosts_parallel", side_effect=_resolve_passthrough), \
         patch("netpath.servers.cymru_bulk_lookup", return_value={}):
        result = _fetch_and_resolve()

    assert [s["HOST"] for s in result] == ["mine.example"]


def test_fetch_public_list_raises_without_other_sources(_no_cache):
    with patch("netpath.servers.requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.raises(requests.ConnectionError):
            servers._fetch_public_list(have_other_sources=False)


def test_fetch_public_list_warns_and_continues_with_other_sources(_no_cache):
    with patch("netpath.servers.requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.warns(UserWarning, match="public iperf3 server list unavailable"):
            assert servers._fetch_public_list(have_other_sources=True) == []


def test_load_local_registry_missing_file_is_empty(tmp_path):
    with patch("netpath.servers.LOCAL_REGISTRY_PATH", tmp_path / "servers.json"):
        assert servers._load_local_registry() == []


def test_fetch_extra_lists_reads_env_urls(monkeypatch):
    monkeypatch.setenv(servers.EXTRA_SERVERS_ENV, "https://a.example/list.json, https://b.example/list.json")
    responses = {
        "https://a.example/list.json": [_entry("a.example")],
        "https://b.example/list.json": {"servers": [_entry("b.example")]},
    }

    def fake_get(url, timeout):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = responses[url]
        resp.raise_for_status = lambda: None
        return resp

    with patch("netpath.servers.requests.get", side_effect=fake_get):
        result = servers._fetch_extra_lists()

    assert [e["IP/HOST"] for e in result] == ["a.example", "b.example"]


# ── DNS SRV advertisement ─────────────────────────────────────────────────────

def _doh_response(answers):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"Answer": answers}
    return resp


def test_doh_srv_query_parses_and_sorts_records():
    answers = [
        {"type": 33, "data": "10 5 5202 backup.example.com."},
        {"type": 33, "data": "0 10 5201 iperf.example.com."},
        {"type": 46, "data": "not-an-srv-record"},
        {"type": 33, "data": "malformed"},
    ]
    with patch("netpath.servers.requests.get", return_value=_doh_response(answers)):
        records = _doh_srv_query("_netpath-iperf3._tcp.example.com")

    assert [r["host"] for r in records] == ["iperf.example.com", "backup.example.com"]
    assert records[0]["port"] == 5201


def test_doh_srv_query_rejects_out_of_range_port():
    answers = [{"type": 33, "data": "0 10 70000 iperf.example.com."}]
    with patch("netpath.servers.requests.get", return_value=_doh_response(answers)):
        assert _doh_srv_query("_netpath-iperf3._tcp.example.com") == []


def test_find_advertised_server_uses_exact_domain():
    calls = []

    def fake_query(name):
        calls.append(name)
        if name == "_netpath-iperf3._tcp.media.eu.example.com":
            return [{"priority": 0, "weight": 0, "port": 5201, "host": "iperf.example.com"}]
        return []

    with patch("netpath.servers._doh_srv_query", side_effect=fake_query):
        result = find_advertised_server("media.eu.example.com")

    assert result == {
        "host": "iperf.example.com",
        "port": 5201,
        "domain": "media.eu.example.com",
    }
    assert calls == ["_netpath-iperf3._tcp.media.eu.example.com"]


def test_find_advertised_server_returns_none_without_records():
    with patch("netpath.servers._doh_srv_query", return_value=[]):
        assert find_advertised_server("example.com") is None


def test_find_advertised_server_tolerates_doh_failure():
    with patch("netpath.servers._doh_srv_query", side_effect=requests.ConnectionError("blocked")):
        assert find_advertised_server("example.com") is None
