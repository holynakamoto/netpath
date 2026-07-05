from unittest.mock import Mock, patch

from netpath import dns, edge, geo, pmtu
from netpath.diagnosis import diagnose


def test_dns_measure_reports_lookup_answers_and_resolvers():
    fake_infos = [
        (dns.socket.AF_INET, None, None, None, ("203.0.113.10", 0)),
        (dns.socket.AF_INET6, None, None, None, ("2001:db8::10", 0)),
    ]
    with patch("netpath.dns._resolver_ips", return_value=["192.0.2.53"]), \
         patch("netpath.dns.socket.getaddrinfo", return_value=fake_infos), \
         patch("netpath.dns._dig_answers", return_value=[
             {"name": "app.example", "type": "A", "ttl": 60, "value": "203.0.113.10"},
             {"name": "app.example", "type": "CNAME", "ttl": 60, "value": "edge.example"},
         ]):
        result = dns.measure("app.example")

    assert result["resolver_ips"] == ["192.0.2.53"]
    assert result["answers"][0] == {"type": "A", "address": "203.0.113.10", "ttl": 60}
    assert result["dual_stack"] is True
    assert result["cnames"] == [{"name": "app.example", "value": "edge.example"}]
    assert result["lookup_ms"] is not None


def test_pmtu_binary_search_reports_effective_mtu():
    def fake_run(cmd, **kwargs):
        size = int(cmd[cmd.index("-s") + 1])
        return Mock(returncode=0 if size <= 1200 else 1)

    with patch("netpath.pmtu.subprocess.run", side_effect=fake_run):
        result = pmtu.probe("203.0.113.10")

    assert result["blackhole"] is True
    assert result["mtu_floor_bytes"] == 64
    assert result["max_payload_bytes"] == 1200
    assert result["effective_mtu_bytes"] == 1228


def test_geo_path_flags_multi_country_trombone():
    hubs = [
        {"count": 1, "host": "8.8.8.8", "ASN": "AS1", "Avg": 5.0},
        {"count": 2, "host": "1.1.1.1", "ASN": "AS2", "Avg": 70.0},
        {"count": 3, "host": "9.9.9.9", "ASN": "AS3", "Avg": 120.0},
    ]
    geo_rows = {
        "8.8.8.8": {"lat": 37.8, "lon": -122.4, "country_code": "US", "city": "San Francisco"},
        "1.1.1.1": {"lat": 51.5, "lon": -0.1, "country_code": "GB", "city": "London"},
        "9.9.9.9": {"lat": 35.7, "lon": 139.7, "country_code": "JP", "city": "Tokyo"},
    }
    with patch("netpath.geo.globe.geolocate_hosts", return_value=geo_rows):
        result = geo.analyze_path(hubs)

    assert result["country_hops"] == ["US", "GB", "JP"]
    assert result["total_geodesic_km"] > 10000
    assert "multi_country_trombone" in result["warnings"]


def test_edge_measure_parses_status_ttfb_and_certificate():
    class FakeSock:
        def __init__(self):
            self.sent = b""

        def sendall(self, data):
            self.sent += data

        def recv(self, size):
            return b"HTTP/1.1 200 OK\r\nServer: test\r\n\r\n"

        def getpeercert(self):
            return {
                "notAfter": "Jan 01 00:00:00 2099 GMT",
                "subjectAltName": (("DNS", "app.example"),),
            }

        def close(self):
            pass

    ctx = Mock()
    ctx.wrap_socket.return_value = FakeSock()
    with patch("netpath.edge.socket.create_connection", return_value=FakeSock()), \
         patch("netpath.edge.ssl.create_default_context", return_value=ctx):
        result = edge.measure("app.example")

    assert result["status_code"] == 200
    assert result["ttfb_ms"] is not None
    assert result["server"] == "test"
    assert result["certificate"]["days_until_expiry"] > 0
    assert result["certificate"]["san_dns"] == ["app.example"]


def test_diagnose_warns_on_dns_and_http_edge_latency():
    verdict = diagnose({
        "dns": {"lookup_ms": 300.0, "resolver_ips": ["192.0.2.53"]},
        "http_edge": {"ttfb_ms": 1200.0, "status_code": 200, "redirect_count": 0},
    })

    assert verdict["severity"] == "warning"
    assert {signal["condition"] for signal in verdict["signals"]} >= {"dns_latency", "http_ttfb_latency"}
