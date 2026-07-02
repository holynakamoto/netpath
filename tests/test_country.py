from unittest.mock import patch, call, MagicMock
import requests

from netpath.country import (
    get_test_ip_for_asn,
    get_test_target_for_asn,
    RIPE_ATLAS_PROBES,
)
from netpath import ixp as ixp_mod
from netpath.cli import _worst_exit_code
from netpath import mtr as mtr_mod


def _atlas_response(probes: list) -> MagicMock:
    """Build a mock requests.Response for the Atlas probes API."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": probes}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _netixlan_response(records: list) -> MagicMock:
    """Build a mock requests.Response for the PeeringDB netixlan API."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": records}
    return mock_resp


def test_get_test_ip_uses_atlas_probe_when_available():
    """get_test_ip_for_asn() returns the Atlas probe's address_v4 when the API has a result."""
    atlas_resp = _atlas_response([{"id": 1, "asn_v4": 3741, "address_v4": "196.1.2.3"}])
    with patch("netpath.country.requests.get", return_value=atlas_resp):
        ip, origin = get_test_target_for_asn("AS3741")
    assert (ip, origin) == ("196.1.2.3", "atlas")


def test_get_test_ip_returns_none_when_atlas_empty():
    """No Atlas probe and no PeeringDB presence means no test IP — no prefix guessing."""
    atlas_resp = _atlas_response([])
    with patch("netpath.country.requests.get", return_value=atlas_resp) as mock_get, \
         patch("netpath.country.ixp.netixlan_ipv4_for_asn", return_value=None):
        result = get_test_ip_for_asn("AS3741")

    assert result is None
    # Only the Atlas probes API may be queried on the RIPE side — never announced prefixes.
    assert mock_get.call_count > 0
    for c in mock_get.call_args_list:
        assert c.args[0] == RIPE_ATLAS_PROBES


def test_get_test_ip_returns_none_on_atlas_error():
    """When the Atlas API raises RequestException, PeeringDB is tried; None if it too is empty."""
    with patch(
        "netpath.country.requests.get",
        side_effect=requests.RequestException("connection refused"),
    ), patch("netpath.country.ixp.netixlan_ipv4_for_asn", return_value=None):
        result = get_test_ip_for_asn("AS3741")
    assert result is None


def test_get_test_ip_returns_none_for_null_address_v4():
    """A probe with address_v4=None yields no test IP — no address is ever guessed."""
    atlas_resp = _atlas_response([{"id": 1, "asn_v4": 3741, "address_v4": None}])
    with patch("netpath.country.requests.get", return_value=atlas_resp), \
         patch("netpath.country.ixp.netixlan_ipv4_for_asn", return_value=None):
        result = get_test_ip_for_asn("AS3741")
    assert result is None


def test_get_test_ip_falls_back_to_peeringdb_netixlan():
    """When no Atlas probe exists, a PeeringDB netixlan IPv4 is used as the target."""
    ixp_mod._NETIXLAN_CACHE.clear()
    atlas_resp = _atlas_response([])  # no Atlas probe
    netixlan_resp = _netixlan_response([
        {"ipaddr4": None, "ipaddr6": "2001:db8::1"},   # skipped: no IPv4
        {"ipaddr4": "80.249.208.100", "ipaddr6": "2001:7f8:1::a500:3356:1"},
    ])
    with patch("netpath.country.requests.get", return_value=atlas_resp), \
         patch("netpath.ixp.requests.get", return_value=netixlan_resp):
        ip, origin = get_test_target_for_asn("AS3356")
        # get_test_ip_for_asn exposes the same IPv4 via its plain-string contract
        # (served from the per-ASN cache populated by the call above).
        plain_ip = get_test_ip_for_asn("AS3356")

    assert ip == "80.249.208.100"
    assert origin == "peeringdb"
    assert plain_ip == "80.249.208.100"


def test_get_test_ip_no_peeringdb_presence_unchanged():
    """An ASN absent from PeeringDB netixlan behaves exactly as before — None."""
    ixp_mod._NETIXLAN_CACHE.clear()
    atlas_resp = _atlas_response([])  # no Atlas probe
    netixlan_resp = _netixlan_response([])  # no PeeringDB records
    with patch("netpath.country.requests.get", return_value=atlas_resp), \
         patch("netpath.ixp.requests.get", return_value=netixlan_resp):
        ip, origin = get_test_target_for_asn("AS64500")

    assert ip is None
    assert origin is None


def test_netixlan_ipv4_caches_per_asn():
    """netixlan_ipv4_for_asn caches the PeeringDB response per-ASN in process."""
    ixp_mod._NETIXLAN_CACHE.clear()
    netixlan_resp = _netixlan_response([{"ipaddr4": "185.1.2.3", "ipaddr6": None}])
    with patch("netpath.ixp.requests.get", return_value=netixlan_resp) as mock_get:
        first = ixp_mod.netixlan_ipv4_for_asn("AS3356")
        second = ixp_mod.netixlan_ipv4_for_asn("AS3356")

    assert first == second == "185.1.2.3"
    assert mock_get.call_count == 1  # second lookup served from cache


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
