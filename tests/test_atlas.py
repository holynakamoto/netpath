from unittest.mock import patch, MagicMock

import requests as req_lib


def _anchors_response(anchors: list) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": anchors}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_find_anchors_in_asn_returns_probe_ids():
    """find_anchors_in_asn() extracts probe IDs from anchor records."""
    from netpath.atlas import find_anchors_in_asn
    resp = _anchors_response([
        {"id": 100, "probe": 1001, "asn_v4": 15169},
        {"id": 101, "probe": 1002, "asn_v4": 15169},
    ])
    with patch("netpath.atlas.requests.get", return_value=resp):
        result = find_anchors_in_asn("AS15169", "testkey")
    assert result == [1001, 1002]


def test_find_anchors_in_asn_strips_as_prefix():
    """find_anchors_in_asn() accepts 'AS15169' and strips the prefix before the API call."""
    from netpath.atlas import find_anchors_in_asn
    resp = _anchors_response([{"id": 100, "probe": 1001}])
    with patch("netpath.atlas.requests.get", return_value=resp) as mock_get:
        find_anchors_in_asn("AS15169", "testkey")
    params = mock_get.call_args[1]["params"]
    assert params["asn_v4"] == "15169"


def test_find_anchors_in_asn_skips_records_without_probe_field():
    """find_anchors_in_asn() skips anchor records that have no probe field."""
    from netpath.atlas import find_anchors_in_asn
    resp = _anchors_response([
        {"id": 100, "asn_v4": 15169},
        {"id": 101, "probe": 1002, "asn_v4": 15169},
    ])
    with patch("netpath.atlas.requests.get", return_value=resp):
        result = find_anchors_in_asn("AS15169", "testkey")
    assert result == [1002]


def test_find_anchors_in_asn_returns_empty_on_error():
    """find_anchors_in_asn() returns [] when the API raises."""
    from netpath.atlas import find_anchors_in_asn
    with patch("netpath.atlas.requests.get", side_effect=req_lib.RequestException("timeout")):
        result = find_anchors_in_asn("AS15169", "testkey")
    assert result == []


def test_find_anchors_in_asn_returns_empty_on_empty_results():
    """find_anchors_in_asn() returns [] when the API returns no results."""
    from netpath.atlas import find_anchors_in_asn
    resp = _anchors_response([])
    with patch("netpath.atlas.requests.get", return_value=resp):
        result = find_anchors_in_asn("AS15169", "testkey")
    assert result == []


def _page_response(results: list) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": results, "next": None}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_fetch_coverage_counts_probes_and_anchors_by_country():
    """fetch_coverage_by_country() reads country_code from probes and country from anchors."""
    from netpath.atlas import fetch_coverage_by_country

    def fake_get(url, **kwargs):
        if "/probes/" in url:
            return _page_response([
                {"id": 1, "country_code": "NL"},
                {"id": 2, "country_code": "NL"},
                {"id": 3, "country_code": "US"},
            ])
        return _page_response([{"id": 100, "country": "NL"}])

    with patch("netpath.atlas.requests.get", side_effect=fake_get):
        coverage = fetch_coverage_by_country("testkey")

    assert coverage == {
        "NL": {"probes": 2, "anchors": 1},
        "US": {"probes": 1, "anchors": 0},
    }


def test_fetch_coverage_surfaces_http_error_and_returns_partial():
    """fetch_coverage_by_country() warns instead of raising when a request 403s."""
    from netpath.atlas import fetch_coverage_by_country

    err = req_lib.HTTPError("403 Client Error")
    err.response = MagicMock(status_code=403)

    failing = MagicMock()
    failing.raise_for_status.side_effect = err

    with patch("netpath.atlas.requests.get", return_value=failing), \
         patch("netpath.atlas.console") as mock_console:
        mock_console.is_jupyter = False
        coverage = fetch_coverage_by_country("badkey")

    assert coverage == {}
    printed = " ".join(str(c.args[0]) for c in mock_console.print.call_args_list)
    assert "API key may be invalid" in printed
