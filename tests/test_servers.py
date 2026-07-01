import json
from unittest.mock import patch, MagicMock

from netpath.servers import _tcp_alive, _is_iperf3_alive, find_servers_in_asn


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
