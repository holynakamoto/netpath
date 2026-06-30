from unittest.mock import patch, call

from netpath.country import get_test_ip_for_asn
from netpath import mtr as mtr_mod


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
         patch("netpath.mtr.cymru_bulk_lookup", return_value={}):
        mtr_mod.run_traceroute("1.2.3.4", prefer_tcp=True)

    assert mock_cmd.call_args_list[0] == call("1.2.3.4", tcp=True)


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
         patch("netpath.mtr.cymru_bulk_lookup", return_value={}):
        result = mtr_mod.run_traceroute("1.2.3.4", prefer_tcp=True)

    assert mock_cmd.call_args_list[0] == call("1.2.3.4", tcp=True)
    assert mock_cmd.call_args_list[1] == call("1.2.3.4", tcp=False)
    assert result[0]["host"] == "1.2.3.4"
