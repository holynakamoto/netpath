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


def test_resolve_endpoint_resolves_hostname_and_enriches_asn():
    with patch("netpath.targets.socket.getaddrinfo", return_value=[
        (None, None, None, "", ("203.0.113.10", 0)),
    ]), patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
        "203.0.113.10": {
            "asn": "AS64500",
            "prefix": "203.0.113.0/24",
            "name": "Example Video",
        },
    }):
        result = targets.resolve_endpoint("zoom.example")

    assert result["input"] == "zoom.example"
    assert result["hostname"] == "zoom.example"
    assert result["ip"] == "203.0.113.10"
    assert result["asn"] == "AS64500"
    assert result["prefix"] == "203.0.113.0/24"


def test_resolve_endpoint_accepts_ip_without_dns_lookup():
    with patch("netpath.targets.socket.getaddrinfo") as getaddrinfo, \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
             "203.0.113.10": {"asn": "AS64500"},
         }):
        result = targets.resolve_endpoint("203.0.113.10")

    assert result["hostname"] is None
    assert result["ip"] == "203.0.113.10"
    assert result["asn"] == "AS64500"
    getaddrinfo.assert_not_called()


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


def test_geocode_city_returns_first_result():
    resp = _response({
        "results": [{
            "name": "Tel Aviv",
            "country": "Israel",
            "country_code": "IL",
            "admin1": "Tel Aviv",
            "latitude": 32.08088,
            "longitude": 34.78057,
            "timezone": "Asia/Jerusalem",
        }]
    })
    with patch("netpath.targets.requests.get", return_value=resp):
        result = targets.geocode_city("Tel Aviv")

    assert result["name"] == "Tel Aviv"
    assert result["country_code"] == "IL"
    assert result["lat"] == 32.08088


_TEL_AVIV = {"name": "Tel Aviv", "country_code": "IL", "lat": 32.08088, "lon": 34.78057}


def _atlas_probes_response() -> MagicMock:
    return _response({
        "results": [
            {
                "id": 1,
                "address_v4": "192.0.2.20",
                "asn_v4": 64520,
                "geometry": {"coordinates": [35.0, 32.5]},
            },
            {
                "id": 2,
                "address_v4": "192.0.2.10",
                "asn_v4": 64510,
                "geometry": {"coordinates": [34.7805, 32.0815]},
            },
        ]
    })


def test_atlas_target_near_city_picks_nearest_ipv4_probe():
    with patch("netpath.targets.requests.get", return_value=_atlas_probes_response()), \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
             "192.0.2.20": {"country": "IL"},
             "192.0.2.10": {"country": "IL"},
         }):
        result = targets.atlas_target_near_city(_TEL_AVIV)

    assert result["ip"] == "192.0.2.10"
    assert result["origin"] == "atlas-city"
    assert result["asn"] == "AS64510"
    assert result["distance_km"] < 1
    assert result["confidence"] == "high"
    assert "registry country verified" in result["reason"]


def test_atlas_target_near_city_skips_probe_registered_in_another_country():
    with patch("netpath.targets.requests.get", return_value=_atlas_probes_response()), \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
             "192.0.2.10": {"country": "AU"},
             "192.0.2.20": {"country": "IL"},
         }):
        result = targets.atlas_target_near_city(_TEL_AVIV)

    assert result["ip"] == "192.0.2.20"
    assert result["confidence"] == "high"


def test_atlas_target_near_city_returns_none_when_no_probe_validates():
    with patch("netpath.targets.requests.get", return_value=_atlas_probes_response()), \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
             "192.0.2.10": {"country": "AU"},
             "192.0.2.20": {"country": "AU"},
         }):
        result = targets.atlas_target_near_city(_TEL_AVIV)

    assert result is None


def test_atlas_target_near_city_falls_back_unverified_when_cymru_fails():
    with patch("netpath.targets.requests.get", return_value=_atlas_probes_response()), \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={}):
        result = targets.atlas_target_near_city(_TEL_AVIV)

    assert result["ip"] == "192.0.2.10"
    assert result["confidence"] == "medium"
    assert "registry country unverified" in result["reason"]


def test_atlas_target_near_city_follows_pagination():
    first = _response({
        "results": [{
            "id": 1,
            "address_v4": "192.0.2.20",
            "asn_v4": 64520,
            "geometry": {"coordinates": [35.0, 32.5]},
        }],
        "next": "https://atlas.ripe.net/api/v2/probes/?page=2",
    })
    second = _atlas_probes_response()
    with patch("netpath.targets.requests.get", side_effect=[first, second]) as get, \
         patch("netpath.targets.cymru_bulk_lookup_rich", return_value={
             "192.0.2.20": {"country": "IL"},
             "192.0.2.10": {"country": "IL"},
         }):
        result = targets.atlas_target_near_city(_TEL_AVIV)

    assert get.call_count == 2
    assert get.call_args.args[0] == "https://atlas.ripe.net/api/v2/probes/?page=2"
    assert result["ip"] == "192.0.2.10"
