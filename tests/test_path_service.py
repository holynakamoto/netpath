from unittest.mock import patch

import pytest

from netpath import path_service


def test_measure_aspath_reuses_path_pipeline():
    target = {"ip": "203.0.113.9", "origin": "atlas", "asn": "AS64501"}
    statuses = {"ping-id": "finished", "mtr-id": "finished"}
    with patch("netpath.path_service.globalping.fetch_probes", return_value=[
        {"network": {"asn": 64500}}
    ]), patch(
        "netpath.path_service.globalping.count_probes_by_asn", return_value={64500: 1}
    ), patch(
        "netpath.path_service.targets.discover_target", return_value=target
    ), patch(
        "netpath.path_service.globalping.schedule_path_measurements",
        return_value={"ping": "ping-id", "mtr": "mtr-id"},
    ), patch(
        "netpath.path_service.globalping.poll_until_done", return_value=statuses
    ), patch("netpath.path_service._merge_globalping_path_results") as merge, patch(
        "netpath.path_service._apply_path_json_contract", side_effect=lambda value: value
    ):
        result = path_service.measure_aspath("64500", "64501")

    assert result["source_asn"] == "AS64500"
    assert result["dest_asn"] == "AS64501"
    assert result["target_ip"] == "203.0.113.9"
    merge.assert_called_once()


def test_measure_aspath_rejects_uncovered_source():
    with patch(
        "netpath.path_service.globalping.fetch_probes", return_value=[]
    ), patch(
        "netpath.path_service.globalping.count_probes_by_asn", return_value={}
    ):
        with pytest.raises(RuntimeError, match="No connected Globalping probes"):
            path_service.measure_aspath("AS64500", "AS64501")


def test_measure_citypath_uses_geocoded_source_and_atlas_target():
    source = {"name": "Denver", "country_code": "US"}
    dest = {"name": "Tel Aviv", "country_code": "IL"}
    target = {"ip": "203.0.113.9", "origin": "atlas", "asn": "AS64501"}
    with patch(
        "netpath.path_service.targets.geocode_city", side_effect=[source, dest]
    ), patch(
        "netpath.path_service.targets.atlas_target_near_city", return_value=target
    ), patch(
        "netpath.path_service.globalping.schedule_location_path_measurements",
        return_value={"ping": "ping-id", "mtr": "mtr-id"},
    ) as schedule, patch(
        "netpath.path_service.globalping.poll_until_done",
        return_value={"ping-id": "finished", "mtr-id": "finished"},
    ), patch("netpath.path_service._merge_globalping_path_results"), patch(
        "netpath.path_service._apply_path_json_contract", side_effect=lambda value: value
    ):
        result = path_service.measure_citypath("Denver", "Tel Aviv")

    assert result["source_asn"] == "Denver, US"
    assert result["dest_asn"] == "Tel Aviv, IL"
    schedule.assert_called_once_with(
        {"name": "Denver", "city": "Denver", "country": "US"},
        "203.0.113.9",
        None,
    )
