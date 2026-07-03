from unittest.mock import MagicMock, patch

from netpath import targets


def _response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


def test_discover_target_prefers_iperf3_server():
    with patch("netpath.targets.servers.find_servers_in_asn", return_value=[
        {"HOST": "203.0.113.10", "port": 5201},
    ]), patch("netpath.targets.country_mod.get_test_target_for_asn") as atlas:
        result = targets.discover_target("AS64500")

    assert result["ip"] == "203.0.113.10"
    assert result["origin"] == "iperf3"
    assert result["confidence"] == "high"
    atlas.assert_not_called()


def test_discover_target_uses_user_target_and_reports_cymru_mismatch():
    with patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
        "198.51.100.10": {"asn": "AS64501", "prefix": "198.51.100.0/24"},
    }):
        result = targets.discover_target("AS64500", user_target="198.51.100.10")

    assert result["ip"] == "198.51.100.10"
    assert result["origin"] == "user"
    assert result["confidence"] == "low"
    assert "AS64501" in result["reason"]


def test_discover_target_falls_back_to_validated_announced_prefix_sample():
    ripe = _response({
        "data": {
            "prefixes": [
                {"prefix": "8.8.4.0/24"},
                {"prefix": "9.9.9.0/24"},
            ]
        }
    })

    def fake_cymru(ips):
        return {
            ip: {"asn": "AS64500", "prefix": "8.8.4.0/24"}
            for ip in ips
            if ip.startswith("8.8.4.")
        }

    def fake_tcp(ip, port, timeout=1.5):
        if ip == "8.8.4.1" and port == 443:
            return "open"
        return None

    with patch("netpath.targets.servers.find_servers_in_asn", return_value=[]), \
         patch("netpath.targets.country_mod.get_test_target_for_asn", return_value=(None, None)), \
         patch("netpath.targets.requests.get", return_value=ripe), \
         patch("netpath.targets.cymru_bulk_lookup_rich", side_effect=fake_cymru), \
         patch("netpath.targets._tcp_status", side_effect=fake_tcp):
        result = targets.discover_target("AS64500")

    assert result["ip"] == "8.8.4.1"
    assert result["origin"] == "ripe-prefix"
    assert result["confidence"] == "medium"
    assert result["port"] == 443


def test_discover_target_returns_low_confidence_routed_sample_without_tcp_liveness():
    ripe = _response({"data": {"prefixes": [{"prefix": "8.8.4.0/24"}]}})

    with patch("netpath.targets.servers.find_servers_in_asn", return_value=[]), \
         patch("netpath.targets.country_mod.get_test_target_for_asn", return_value=(None, None)), \
         patch("netpath.targets.requests.get", return_value=ripe), \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
             "8.8.4.1": {"asn": "AS64500", "prefix": "8.8.4.0/24"},
             "8.8.4.128": {"asn": "AS64500", "prefix": "8.8.4.0/24"},
             "8.8.4.254": {"asn": "AS64500", "prefix": "8.8.4.0/24"},
         }), \
         patch("netpath.targets._tcp_status", return_value=None):
        result = targets.discover_target("AS64500")

    assert result["ip"] == "8.8.4.1"
    assert result["origin"] == "ripe-prefix"
    assert result["confidence"] == "low"
    assert "no TCP liveness" in result["reason"]
