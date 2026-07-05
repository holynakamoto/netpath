from unittest.mock import patch

from netpath import cli_measurement
from netpath import trace_fusion


def test_trace_fusion_merges_sources_variants_and_filtered_ranges():
    mtr_hubs = [
        {"count": 1, "host": "192.0.2.1", "ASN": "AS64501", "Loss%": 0.0, "Avg": 1.0, "Best": 1.0, "Wrst": 1.0},
        {"count": 2, "host": "???", "ASN": "AS???", "Loss%": 100.0, "Avg": 0.0, "Best": 0.0, "Wrst": 0.0},
        {"count": 3, "host": "198.51.100.3", "ASN": "AS64503", "Loss%": 0.0, "Avg": 8.0, "Best": 8.0, "Wrst": 8.0},
    ]
    paris_hubs = [
        {"count": 1, "host": "192.0.2.1", "ASN": "AS64501", "Loss%": 0.0, "Avg": 1.2, "Best": 1.2, "Wrst": 1.2},
        {"count": 2, "host": "203.0.113.2", "ASN": "AS64502", "Loss%": 0.0, "Avg": 4.0, "Best": 4.0, "Wrst": 4.0},
        {"count": 3, "host": "198.51.100.4", "ASN": "AS64504", "Loss%": 0.0, "Avg": 9.0, "Best": 9.0, "Wrst": 9.0},
    ]

    with patch("netpath.trace_fusion.mtr.available", return_value=True), \
         patch("netpath.trace_fusion.mtr.run", return_value=mtr_hubs), \
         patch("netpath.trace_fusion.paris.detect", return_value="scamper"), \
         patch("netpath.trace_fusion.paris.run", return_value=paris_hubs), \
         patch("netpath.trace_fusion.mtr.traceroute_path", return_value=None), \
         patch("netpath.trace_fusion.mtr._enrich_names"):
        hubs, metadata = trace_fusion.run("example.com", cycles=10)

    assert metadata["probes_per_method"] == trace_fusion.MAX_FUSION_PROBES
    assert metadata["filtered_ranges"] == []
    assert hubs[0]["host"] == "192.0.2.1"
    assert hubs[0]["sources"] == ["mtr", "scamper"]
    assert hubs[1]["host"] == "203.0.113.2"
    assert hubs[1]["sources"] == ["scamper"]
    assert {variant["host"] for variant in hubs[2]["variants"]} == {"198.51.100.3", "198.51.100.4"}


def test_trace_fusion_records_silent_hop_ranges():
    with patch("netpath.trace_fusion.mtr.available", return_value=True), \
         patch("netpath.trace_fusion.mtr.run", return_value=[
             {"count": 1, "host": "192.0.2.1", "ASN": "AS64501", "Loss%": 0.0, "Avg": 1.0},
             {"count": 2, "host": "???", "ASN": "AS???", "Loss%": 100.0, "Avg": 0.0},
             {"count": 3, "host": "???", "ASN": "AS???", "Loss%": 100.0, "Avg": 0.0},
         ]), \
         patch("netpath.trace_fusion.paris.detect", return_value=None), \
         patch("netpath.trace_fusion.mtr.traceroute_path", return_value=None), \
         patch("netpath.trace_fusion.mtr._enrich_names"):
        hubs, metadata = trace_fusion.run("example.com", cycles=3)

    assert hubs[1]["filtered"] is True
    assert hubs[2]["filtered"] is True
    assert metadata["filtered_ranges"] == [{"start": 2, "end": 3}]


def test_trace_fusion_raises_when_all_methods_fail():
    with patch("netpath.trace_fusion.mtr.available", return_value=True), \
         patch("netpath.trace_fusion.mtr.run", side_effect=RuntimeError("mtr failed")), \
         patch("netpath.trace_fusion.paris.detect", return_value=None), \
         patch("netpath.trace_fusion.mtr.traceroute_path", return_value=None):
        try:
            trace_fusion.run("example.com")
        except RuntimeError as exc:
            assert "mtr failed" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


def test_measure_records_trace_fusion_failure_on_trace_error_contract():
    with patch("netpath.cli_measurement.trace_fusion_mod.run", side_effect=RuntimeError("all failed")):
        result = cli_measurement._measure(
            "example.com",
            443,
            "AS64500",
            cycles=1,
            duration=1,
            skip_throughput=True,
            trace_fusion=True,
        )

    assert result["hubs"] == []
    assert result["probe_errors"]["v4_trace"] == "trace fusion: all failed"
