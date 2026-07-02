from unittest.mock import patch, call, MagicMock
import requests

from netpath.country import get_test_ip_for_asn
from netpath import mtr as mtr_mod


def _atlas_response(probes: list) -> MagicMock:
    """Build a mock requests.Response for the Atlas probes API."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": probes}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _ripe_prefixes_response(prefixes: list) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"prefixes": prefixes}}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_get_test_ip_uses_atlas_probe_when_available():
    """get_test_ip_for_asn() returns the Atlas probe's address_v4 when the API has a result."""
    atlas_resp = _atlas_response([{"id": 1, "asn_v4": 3741, "address_v4": "196.1.2.3"}])
    with patch("netpath.country.requests.get", return_value=atlas_resp):
        result = get_test_ip_for_asn("AS3741")
    assert result == "196.1.2.3"


def test_get_test_ip_falls_through_to_prefix_when_atlas_empty():
    """When the Atlas API returns no probes, the prefix-based fallback is used."""
    atlas_resp = _atlas_response([])
    ripe_resp = _ripe_prefixes_response([{"prefix": "196.2.0.0/24"}])

    call_count = 0

    def side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return atlas_resp
        return ripe_resp

    with patch("netpath.country.requests.get", side_effect=side_effect):
        result = get_test_ip_for_asn("AS3741")

    import ipaddress
    expected = str(list(ipaddress.IPv4Network("196.2.0.0/24").hosts())[1])
    assert result == expected


def test_get_test_ip_falls_through_to_prefix_on_atlas_error():
    """When the Atlas API raises RequestException, the prefix fallback is used without raising."""
    ripe_resp = _ripe_prefixes_response([{"prefix": "196.3.0.0/24"}])

    call_count = 0

    def side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise requests.RequestException("connection refused")
        return ripe_resp

    with patch("netpath.country.requests.get", side_effect=side_effect):
        result = get_test_ip_for_asn("AS3741")

    import ipaddress
    expected = str(list(ipaddress.IPv4Network("196.3.0.0/24").hosts())[1])
    assert result == expected


def test_get_test_ip_skips_null_address_v4():
    """A probe with address_v4=None is skipped; the function falls through to prefix selection."""
    atlas_resp = _atlas_response([{"id": 1, "asn_v4": 3741, "address_v4": None}])
    ripe_resp = _ripe_prefixes_response([{"prefix": "196.4.0.0/24"}])

    call_count = 0

    def side_effect(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return atlas_resp
        return ripe_resp

    with patch("netpath.country.requests.get", side_effect=side_effect):
        result = get_test_ip_for_asn("AS3741")

    import ipaddress
    expected = str(list(ipaddress.IPv4Network("196.4.0.0/24").hosts())[1])
    assert result == expected


def test_get_test_ip_prefers_most_specific_prefix():
    """get_test_ip_for_asn() returns a host from the highest-prefixlen (most specific) prefix."""
    # Prefixes ordered least-specific first — the old code would pick /16, new code picks /24.
    prefixes = [
        {"prefix": "1.0.0.0/16"},
        {"prefix": "1.1.0.0/20"},
        {"prefix": "1.1.1.0/24"},
    ]
    mock_resp = {"data": {"prefixes": prefixes}}
    with patch("netpath.country.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_resp
        mock_get.return_value.raise_for_status.return_value = None
        result = get_test_ip_for_asn("AS12345")

    import ipaddress
    net_24 = ipaddress.IPv4Network("1.1.1.0/24", strict=False)
    expected = str(list(net_24.hosts())[1])  # 1.1.1.2
    assert result == expected


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
