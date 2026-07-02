from unittest.mock import patch, MagicMock

import requests as req_lib


def _json_response(payload) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status.return_value = None
    mock_resp.status_code = 200
    return mock_resp


def _probe(asn: int, country: str) -> dict:
    return {"location": {"asn": asn, "country": country}}


# --- fetch_probes ---

def test_fetch_probes_returns_probe_list():
    """fetch_probes() returns the connected-probe inventory."""
    from netpath.globalping import fetch_probes
    probes = [_probe(15169, "US"), _probe(3741, "ZA")]
    with patch("netpath.globalping.requests.get", return_value=_json_response(probes)):
        result = fetch_probes()
    assert result == probes


def test_fetch_probes_returns_empty_on_error():
    """fetch_probes() returns [] when the API raises."""
    from netpath.globalping import fetch_probes
    with patch("netpath.globalping.requests.get",
               side_effect=req_lib.RequestException("down")):
        result = fetch_probes()
    assert result == []


def test_fetch_probes_sends_bearer_header_with_token():
    """fetch_probes() carries Authorization: Bearer when a token is set."""
    from netpath.globalping import fetch_probes
    with patch("netpath.globalping.requests.get",
               return_value=_json_response([])) as mock_get:
        fetch_probes(token="secret123")
    headers = mock_get.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer secret123"


def test_fetch_probes_sends_no_auth_header_without_token():
    """fetch_probes() sends no Authorization header when no token is set."""
    from netpath.globalping import fetch_probes
    with patch("netpath.globalping.requests.get",
               return_value=_json_response([])) as mock_get:
        fetch_probes()
    headers = mock_get.call_args[1]["headers"]
    assert "Authorization" not in headers


# --- coverage counting ---

def test_count_probes_by_asn_builds_map():
    """count_probes_by_asn() aggregates probe counts per ASN."""
    from netpath.globalping import count_probes_by_asn
    probes = [_probe(15169, "US"), _probe(15169, "DE"), _probe(3741, "ZA")]
    assert count_probes_by_asn(probes) == {15169: 2, 3741: 1}


def test_count_probes_by_asn_skips_missing_asn():
    """count_probes_by_asn() ignores probes without an ASN."""
    from netpath.globalping import count_probes_by_asn
    probes = [{"location": {"country": "US"}}, _probe(3741, "ZA")]
    assert count_probes_by_asn(probes) == {3741: 1}


def test_coverage_by_country_counts():
    """coverage_by_country() aggregates probe counts per country code."""
    from netpath.globalping import coverage_by_country
    probes = [_probe(15169, "US"), _probe(7922, "US"), _probe(3741, "ZA")]
    assert coverage_by_country(probes) == {"US": 2, "ZA": 1}


def test_coverage_by_country_empty_inventory():
    """coverage_by_country() returns {} for an empty inventory."""
    from netpath.globalping import coverage_by_country
    assert coverage_by_country([]) == {}


# --- schedule_measurements ---

def test_schedule_measurements_posts_ping_and_mtr():
    """schedule_measurements() creates a ping and an mtr measurement."""
    from netpath.globalping import schedule_measurements
    responses = [_json_response({"id": "ping-id-1", "probesCount": 3}),
                 _json_response({"id": "mtr-id-1", "probesCount": 3})]
    with patch("netpath.globalping.requests.post",
               side_effect=responses) as mock_post:
        result = schedule_measurements("AS15169", "8.8.8.8", "203.0.113.7")
    assert result == {"ping": "ping-id-1", "mtr": "mtr-id-1"}
    ping_body = mock_post.call_args_list[0][1]["json"]
    mtr_body = mock_post.call_args_list[1][1]["json"]
    assert ping_body["type"] == "ping"
    assert ping_body["target"] == "8.8.8.8"
    assert ping_body["locations"] == [{"magic": "AS15169"}]
    assert ping_body["limit"] == 3
    assert mtr_body["type"] == "mtr"
    assert mtr_body["target"] == "203.0.113.7"
    assert mtr_body["locations"] == [{"magic": "AS15169"}]


def test_schedule_measurements_accepts_bare_asn_number():
    """schedule_measurements() normalises '15169' to magic 'AS15169'."""
    from netpath.globalping import schedule_measurements
    responses = [_json_response({"id": "p"}), _json_response({"id": "m"})]
    with patch("netpath.globalping.requests.post",
               side_effect=responses) as mock_post:
        schedule_measurements("15169", "8.8.8.8", "203.0.113.7")
    body = mock_post.call_args_list[0][1]["json"]
    assert body["locations"] == [{"magic": "AS15169"}]


def test_schedule_measurements_sends_bearer_header():
    """schedule_measurements() carries Authorization: Bearer when a token is set."""
    from netpath.globalping import schedule_measurements
    responses = [_json_response({"id": "p"}), _json_response({"id": "m"})]
    with patch("netpath.globalping.requests.post",
               side_effect=responses) as mock_post:
        schedule_measurements("AS15169", "8.8.8.8", "203.0.113.7", token="tok")
    for call in mock_post.call_args_list:
        assert call[1]["headers"]["Authorization"] == "Bearer tok"


def test_schedule_measurements_raises_on_no_matching_probes():
    """schedule_measurements() propagates HTTPError on a 422 (no probes)."""
    import pytest
    from netpath.globalping import schedule_measurements
    resp = MagicMock()
    resp.status_code = 422
    resp.raise_for_status.side_effect = req_lib.HTTPError("422", response=resp)
    with patch("netpath.globalping.requests.post", return_value=resp):
        with pytest.raises(req_lib.HTTPError):
            schedule_measurements("AS64500", "8.8.8.8", "203.0.113.7")


# --- poll_until_done ---

def test_poll_until_done_returns_terminal_statuses():
    """poll_until_done() records each measurement's status once it leaves in-progress."""
    from netpath.globalping import poll_until_done
    with patch("netpath.globalping.requests.get",
               return_value=_json_response({"status": "finished"})):
        result = poll_until_done(["m1", "m2"])
    assert result == {"m1": "finished", "m2": "finished"}


def test_poll_until_done_marks_stuck_measurements_timed_out():
    """poll_until_done() marks measurements still in-progress at the deadline as timed_out."""
    from netpath.globalping import poll_until_done
    with patch("netpath.globalping.requests.get",
               return_value=_json_response({"status": "in-progress"})):
        result = poll_until_done(["m1"], timeout=0)
    assert result == {"m1": "timed_out"}


# --- fetch_results ---

def test_fetch_results_returns_results_array():
    """fetch_results() extracts the per-probe results list."""
    from netpath.globalping import fetch_results
    payload = {"status": "finished", "results": [{"probe": {}, "result": {}}]}
    with patch("netpath.globalping.requests.get",
               return_value=_json_response(payload)):
        result = fetch_results("m1")
    assert result == [{"probe": {}, "result": {}}]


def test_fetch_results_returns_empty_on_error():
    """fetch_results() returns [] when the API raises."""
    from netpath.globalping import fetch_results
    with patch("netpath.globalping.requests.get",
               side_effect=req_lib.RequestException("down")):
        result = fetch_results("m1")
    assert result == []


# --- parse_ping_rtt ---

def test_parse_ping_rtt_aggregates_across_probes():
    """parse_ping_rtt() combines stats across probes: min of mins, mean of avgs, max of maxes."""
    from netpath.globalping import parse_ping_rtt
    results = [
        {"result": {"stats": {"min": 10.0, "avg": 12.0, "max": 15.0}}},
        {"result": {"stats": {"min": 8.0, "avg": 14.0, "max": 20.0}}},
    ]
    assert parse_ping_rtt(results) == {"min": 8.0, "avg": 13.0, "max": 20.0}


def test_parse_ping_rtt_skips_probes_with_null_stats():
    """parse_ping_rtt() ignores probes whose stats are null (100% loss)."""
    from netpath.globalping import parse_ping_rtt
    results = [
        {"result": {"stats": {"min": None, "avg": None, "max": None}}},
        {"result": {"stats": {"min": 5.0, "avg": 6.0, "max": 7.0}}},
    ]
    assert parse_ping_rtt(results) == {"min": 5.0, "avg": 6.0, "max": 7.0}


def test_parse_ping_rtt_returns_none_when_no_valid_stats():
    """parse_ping_rtt() returns None on empty or all-lost results."""
    from netpath.globalping import parse_ping_rtt
    assert parse_ping_rtt([]) is None
    assert parse_ping_rtt(
        [{"result": {"stats": {"min": None, "avg": None, "max": None}}}]
    ) is None


# --- parse_mtr_as_path ---

def _mtr_result(hops: list[dict]) -> dict:
    return {"result": {"hops": hops}}


def test_parse_mtr_as_path_dedupes_consecutive_asns():
    """parse_mtr_as_path() collapses consecutive hops in the same AS."""
    from netpath.globalping import parse_mtr_as_path
    results = [_mtr_result([
        {"asn": [3741], "resolvedHostname": None},
        {"asn": [3741], "resolvedHostname": None},
        {"asn": [174], "resolvedHostname": None},
        {"asn": [15169], "resolvedHostname": None},
    ])]
    assert parse_mtr_as_path(results) == ["AS3741", "AS174", "AS15169"]


def test_parse_mtr_as_path_labels_with_hostname_domain():
    """parse_mtr_as_path() appends the registered domain from the hop hostname."""
    from netpath.globalping import parse_mtr_as_path
    results = [_mtr_result([
        {"asn": [174], "resolvedHostname": "be3084.ccr41.jfk02.atlas.cogentco.com"},
        {"asn": [15169], "resolvedHostname": None},
    ])]
    assert parse_mtr_as_path(results) == ["AS174 (cogentco.com)", "AS15169"]


def test_parse_mtr_as_path_skips_hops_without_asn():
    """parse_mtr_as_path() skips non-responding hops (empty asn list)."""
    from netpath.globalping import parse_mtr_as_path
    results = [_mtr_result([
        {"asn": [], "resolvedHostname": None},
        {"asn": [174], "resolvedHostname": None},
        {"asn": []},
        {"asn": [174], "resolvedHostname": None},
    ])]
    assert parse_mtr_as_path(results) == ["AS174"]


def test_parse_mtr_as_path_falls_through_to_next_probe():
    """parse_mtr_as_path() uses the next probe when the first has no usable hops."""
    from netpath.globalping import parse_mtr_as_path
    results = [
        _mtr_result([{"asn": [], "resolvedHostname": None}]),
        _mtr_result([{"asn": [7922], "resolvedHostname": None}]),
    ]
    assert parse_mtr_as_path(results) == ["AS7922"]


def test_parse_mtr_as_path_returns_empty_on_no_results():
    """parse_mtr_as_path() returns [] on empty input."""
    from netpath.globalping import parse_mtr_as_path
    assert parse_mtr_as_path([]) == []


# --- get_public_ip ---

def test_get_public_ip_returns_ip():
    """get_public_ip() extracts the ip field from the ipify response."""
    from netpath.globalping import get_public_ip
    with patch("netpath.globalping.requests.get",
               return_value=_json_response({"ip": "203.0.113.7"})):
        assert get_public_ip() == "203.0.113.7"


def test_get_public_ip_returns_none_on_error():
    """get_public_ip() returns None when ipify is unreachable."""
    from netpath.globalping import get_public_ip
    with patch("netpath.globalping.requests.get",
               side_effect=req_lib.RequestException("down")):
        assert get_public_ip() is None
