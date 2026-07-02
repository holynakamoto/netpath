from unittest.mock import patch, call, MagicMock
import requests

from netpath.country import get_test_ip_for_asn, RIPE_ATLAS_PROBES
from netpath.cli import _worst_exit_code
from netpath import mtr as mtr_mod


def _atlas_response(probes: list) -> MagicMock:
    """Build a mock requests.Response for the Atlas probes API."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": probes}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_get_test_ip_uses_atlas_probe_when_available():
    """get_test_ip_for_asn() returns the Atlas probe's address_v4 when the API has a result."""
    atlas_resp = _atlas_response([{"id": 1, "asn_v4": 3741, "address_v4": "196.1.2.3"}])
    with patch("netpath.country.requests.get", return_value=atlas_resp):
        result = get_test_ip_for_asn("AS3741")
    assert result == "196.1.2.3"


def test_get_test_ip_returns_none_when_atlas_empty():
    """No connected Atlas probe means no test IP — the prefix-guessing fallback is gone."""
    atlas_resp = _atlas_response([])
    with patch("netpath.country.requests.get", return_value=atlas_resp) as mock_get:
        result = get_test_ip_for_asn("AS3741")

    assert result is None
    # Only the Atlas probes API may be queried — never announced prefixes.
    assert mock_get.call_count > 0
    for c in mock_get.call_args_list:
        assert c.args[0] == RIPE_ATLAS_PROBES


def test_get_test_ip_returns_none_on_atlas_error():
    """When the Atlas API raises RequestException, None is returned without raising."""
    with patch(
        "netpath.country.requests.get",
        side_effect=requests.RequestException("connection refused"),
    ):
        result = get_test_ip_for_asn("AS3741")
    assert result is None


def test_get_test_ip_returns_none_for_null_address_v4():
    """A probe with address_v4=None yields no test IP — no address is ever guessed."""
    atlas_resp = _atlas_response([{"id": 1, "asn_v4": 3741, "address_v4": None}])
    with patch("netpath.country.requests.get", return_value=atlas_resp):
        result = get_test_ip_for_asn("AS3741")
    assert result is None


def test_rows_without_verdict_do_not_affect_exit_code():
    """No-coverage and remote-only rows carry no verdict key and leave the exit code alone."""
    summary_rows = [
        {"asn": "AS100", "name": "Measured ISP", "verdict": {"severity": "ok"}},
        {"asn": "AS200", "name": "No Coverage ISP",
         "skip_reason": "no iperf3 server, Atlas probe, or usable Globalping coverage"},
        {"asn": "AS300", "name": "Remote Only ISP", "remote_only": True},
    ]
    verdicts = [row["verdict"] for row in summary_rows if row.get("verdict")]
    assert _worst_exit_code(verdicts) == 0

    with_warning = verdicts + [{"severity": "warning"}]
    assert _worst_exit_code(with_warning) == 1


def test_run_traceroute_prefer_tcp_calls_tcp_first():
    """When prefer_tcp=True, TCP-443 is attempted before UDP."""
    tcp_hub = [
        {"count": 1, "host": "1.2.3.4", "ASN": "AS???", "Loss%": 0.0,
         "Avg": 10.0, "Best": 9.0, "Wrst": 11.0, "StDev": 0.5,
         "p50": 10.0, "p95": 10.8, "p99": 11.0}
    ]
    with patch("netpath.mtr._run_traceroute_cmd", return_value=tcp_hub) as mock_cmd, \
         patch("netpath.mtr.cymru_bulk_lookup_rich", return_value={}):
        mtr_mod.run_traceroute("1.2.3.4", prefer_tcp=True)

    assert mock_cmd.call_args_list[0] == call("1.2.3.4", tcp=True, probes=5)


def test_run_traceroute_prefer_tcp_falls_back_to_udp_on_allstars():
    """When prefer_tcp=True and TCP returns all-stars, UDP is tried as fallback."""
    allstars = [
        {"count": 1, "host": "???", "ASN": "AS???", "Loss%": 100.0,
         "Avg": 0.0, "Best": 0.0, "Wrst": 0.0, "StDev": 0.0,
         "p50": None, "p95": None, "p99": None}
    ]
    udp_hub = [
        {"count": 1, "host": "1.2.3.4", "ASN": "AS???", "Loss%": 0.0,
         "Avg": 10.0, "Best": 9.0, "Wrst": 11.0, "StDev": 0.5,
         "p50": 10.0, "p95": 10.8, "p99": 11.0}
    ]
    with patch("netpath.mtr._run_traceroute_cmd", side_effect=[allstars, udp_hub]) as mock_cmd, \
         patch("netpath.mtr.cymru_bulk_lookup_rich", return_value={}):
        result = mtr_mod.run_traceroute("1.2.3.4", prefer_tcp=True)

    assert mock_cmd.call_args_list[0] == call("1.2.3.4", tcp=True, probes=5)
    assert mock_cmd.call_args_list[1] == call("1.2.3.4", tcp=False, probes=5)
    assert result[0]["host"] == "1.2.3.4"
