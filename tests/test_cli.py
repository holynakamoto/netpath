import json
from unittest.mock import patch

from typer.testing import CliRunner
from typer.main import get_command

from netpath import cli


def test_help_lists_product_commands():
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    for command in ("asn", "host", "explain", "monitor", "country", "aspath", "citypath", "target", "coverage"):
        assert command in result.output


def test_host_help_lists_trace_fusion_option():
    host = get_command(cli.app).commands["host"]
    option_names = {
        opt
        for param in host.params
        for opt in getattr(param, "opts", [])
    }

    assert "--trace-fusion" in option_names


def test_country_help_lists_remote_measurement_options():
    country = get_command(cli.app).commands["country"]
    option_names = {
        opt
        for param in country.params
        for opt in getattr(param, "opts", [])
    }

    assert "--gp-token" in option_names
    assert "--no-remote" in option_names
    assert "--atlas-key" not in option_names


def test_asn_exits_with_actionable_error_when_no_path_prober_exists():
    with patch("netpath.mtr.available", return_value=False), \
         patch("netpath.paris.detect", return_value=None), \
         patch("netpath.mtr.traceroute_available", return_value=False):
        result = CliRunner().invoke(cli.app, ["asn", "AS64500", "--json", "--no-throughput"])

    assert result.exit_code == 1
    assert "no path prober found" in result.output
    assert "mtr" in result.output
    assert "traceroute" in result.output


def test_asn_json_contract_contains_stable_top_level_keys():
    measurement = {
        "hubs": [
            {
                "count": 1,
                "host": "192.0.2.1",
                "ASN": "AS64500",
                "Loss%": 0.0,
                "Avg": 1.2,
                "Best": 1.0,
                "Wrst": 1.4,
                "p50": 1.2,
                "p95": 1.4,
                "p99": 1.4,
            }
        ],
        "verdict": {"severity": "ok", "verdict": "Healthy", "signals": []},
        "pmtu": {"blackhole": False},
        "dns": {"lookup_ms": 12.0, "answers": [{"type": "A", "address": "203.0.113.10"}]},
        "http_edge": {"status_code": 200, "ttfb_ms": 80.0},
        "geo_path": {"country_hops": ["US"], "total_geodesic_km": 0.0},
        "ecmp_paths": 1,
        "path_changes": 0,
        "probe_count": 3,
    }
    with patch("netpath.cli._check_deps", return_value=True), \
         patch("netpath.cli.servers.find_servers_in_asn", return_value=[
             {"HOST": "203.0.113.10", "port": 5201}
         ]), \
         patch("netpath.cli._run_test", return_value=measurement):
        result = CliRunner().invoke(cli.app, ["asn", "AS64500", "--json", "--no-throughput"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["asn"] == "AS64500"
    assert payload["target_host"] == "203.0.113.10"
    assert payload["target"] == {
        "type": "asn",
        "asn": "AS64500",
        "host": "203.0.113.10",
        "port": 5201,
    }
    assert payload["probes"]["local"]["sample_size"] == 3
    assert payload["path"][0] == {
        "hop": 1,
        "host": "192.0.2.1",
        "asn": "AS64500",
        "loss_pct": 0.0,
        "avg_ms": 1.2,
        "best_ms": 1.0,
        "worst_ms": 1.4,
        "p50_ms": 1.2,
        "p95_ms": 1.4,
        "p99_ms": 1.4,
    }
    assert payload["throughput"] is None
    assert payload["dns"]["lookup_ms"] == 12.0
    assert payload["http_edge"]["status_code"] == 200
    assert payload["geo_path"]["country_hops"] == ["US"]
    assert payload["verdict"]["severity"] == "ok"
    assert payload["confidence"] == "high"
    assert payload["evidence"] == []
    assert "No escalation needed" in payload["recommendation"]


def test_host_json_uses_exact_endpoint_without_asn_target_selection():
    endpoint = {
        "input": "zoom.example",
        "hostname": "zoom.example",
        "ip": "203.0.113.10",
        "asn": "AS64500",
        "prefix": "203.0.113.0/24",
        "name": "Example Video",
    }
    measurement = {
        "hubs": [
            {
                "count": 1,
                "host": "203.0.113.1",
                "ASN": "AS64500",
                "Loss%": 0.0,
                "Avg": 5.0,
                "Best": 4.0,
                "Wrst": 6.0,
                "p50": 5.0,
                "p95": 6.0,
                "p99": 6.0,
            }
        ],
        "verdict": {
            "severity": "warning",
            "verdict": "TCP Latency",
            "detail": "TCP connect latency of 250 ms exceeds the 200 ms threshold.",
            "signals": [
                {
                    "condition": "tcp_latency",
                    "severity": "warning",
                    "detail": "TCP connect latency of 250 ms exceeds the 200 ms threshold.",
                    "source": "tcp",
                    "confidence": "high",
                    "evidence": {"tcp_connect_ms": 250.0, "threshold_ms": 200.0},
                }
            ],
        },
    }
    with patch("netpath.cli.targets_mod.resolve_endpoint", return_value=endpoint), \
         patch("netpath.cli._check_deps", return_value=True), \
         patch("netpath.cli._run_test", return_value=measurement) as run_test:
        result = CliRunner().invoke(cli.app, ["host", "zoom.example", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["target_input"] == "zoom.example"
    assert payload["resolved_ip"] == "203.0.113.10"
    assert payload["target_asn"] == "AS64500"
    assert payload["target"] == {
        "type": "host",
        "input": "zoom.example",
        "host": "zoom.example",
        "resolved_ip": "203.0.113.10",
        "asn": "AS64500",
        "name": "Example Video",
        "prefix": "203.0.113.0/24",
    }
    assert payload["confidence"] == "high"
    assert payload["evidence"][0]["condition"] == "tcp_latency"
    assert payload["evidence"][0]["evidence"]["tcp_connect_ms"] == 250.0
    assert "destination application edge" in payload["recommendation"]
    run_test.assert_called_once()
    assert run_test.call_args.kwargs["host"] == "203.0.113.10"
    assert run_test.call_args.kwargs["service_host"] == "zoom.example"
    assert run_test.call_args.kwargs["target_asn"] == "AS64500"
    assert run_test.call_args.kwargs["skip_throughput"] is True


def test_explain_json_returns_culprit_and_ticket_summary(tmp_path):
    endpoint = {
        "input": "zoom.example",
        "hostname": "zoom.example",
        "ip": "203.0.113.10",
        "asn": "AS64500",
        "prefix": "203.0.113.0/24",
        "name": "Example Video",
    }
    baseline = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "asn": "AS64500",
        "target_host": "203.0.113.10",
        "as_path": ["AS64501", "AS64500"],
        "last_rtt_ms": 20.0,
        "p95_rtt_ms": 22.0,
        "loss_pct": 0.0,
        "severity": "ok",
        "verdict": "Healthy",
    }
    baseline_file = tmp_path / "baseline.jsonl"
    baseline_file.write_text(json.dumps(baseline) + "\n")
    measurement = {
        "target_input": "zoom.example",
        "target_host": "203.0.113.10",
        "resolved_ip": "203.0.113.10",
        "target_asn": "AS64500",
        "target_name": "Example Video",
        "path": [
            {"hop": 1, "host": "198.51.100.1", "asn": "AS64502", "loss_pct": 0.0, "avg_ms": 10.0, "p95_ms": 12.0},
            {"hop": 2, "host": "203.0.113.10", "asn": "AS64500", "loss_pct": 2.0, "avg_ms": 70.0, "p95_ms": 80.0},
        ],
        "throughput": None,
        "jitter_ms": 12.0,
        "verdict": {
            "severity": "warning",
            "verdict": "Near-target Packet Loss",
            "detail": "Near-target measurement from probes inside the target network shows 2.0% packet loss.",
            "signals": [
                {
                    "condition": "remote_packet_loss",
                    "severity": "warning",
                    "source": "remote_globalping",
                    "confidence": "high",
                    "detail": "Near-target measurement from probes inside the target network shows 2.0% packet loss.",
                    "evidence": {
                        "remote_loss_pct": 2.0,
                        "loss_threshold_pct": 1.0,
                        "remote_packets": 30,
                    },
                    "sample_size": 30,
                }
            ],
        },
        "probes": {"globalping": {"ping_packets": 30}},
    }
    with patch("netpath.cli.targets_mod.resolve_endpoint", return_value=endpoint), \
         patch("netpath.cli._check_deps", return_value=True), \
         patch("netpath.cli._collect_endpoint_json", return_value=measurement):
        result = CliRunner().invoke(
            cli.app,
            ["explain", "zoom.example", "--baseline", str(baseline_file), "--json"],
        )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["destination"] == "zoom.example"
    assert payload["culprit_asn"] == "AS64502"
    assert payload["culprit_scope"] == "route-change"
    assert payload["target"]["asn"] == "AS64500"
    assert payload["path"][1]["asn"] == "AS64500"
    assert payload["probes"]["globalping"]["ping_packets"] == 30
    assert "AS path changed" in payload["baseline_changes"][0]
    assert payload["recommendation"] == payload["recommended_action"]
    assert payload["evidence_details"][0]["condition"] == "remote_packet_loss"
    assert payload["evidence_details"][0]["sample_size"] == 30
    assert "remote_loss_pct" in payload["evidence"][0]
    assert "Requested action" in payload["ticket_summary"]


def test_explain_report_construction_reuses_signal_evidence_for_culprit():
    measurement = {
        "target_input": "app.example",
        "target_host": "203.0.113.20",
        "resolved_ip": "203.0.113.20",
        "target_asn": "AS64520",
        "path": [
            {"hop": 1, "host": "192.0.2.1", "asn": "AS64500", "loss_pct": 0.0},
            {"hop": 2, "host": "198.51.100.2", "asn": "AS64510", "loss_pct": 7.0},
            {"hop": 3, "host": "203.0.113.20", "asn": "AS64520", "loss_pct": 7.0},
        ],
        "verdict": {
            "severity": "warning",
            "verdict": "Mid-path Packet Loss",
            "detail": "Packet loss of 7.0% detected at 198.51.100.2.",
            "signals": [
                {
                    "condition": "mid_path_packet_loss",
                    "severity": "warning",
                    "detail": "Packet loss of 7.0% detected at 198.51.100.2.",
                    "source": "local_trace",
                    "confidence": "medium",
                    "evidence": {
                        "loss_hop": {
                            "hop_index": 2,
                            "host": "198.51.100.2",
                            "asn": "AS64510",
                            "loss_pct": 7.0,
                        },
                        "downstream_clean": False,
                    },
                    "sample_size": 5,
                }
            ],
        },
    }

    report = cli.explain_mod.build_report(destination="app.example", result=measurement)

    assert report["culprit_asn"] == "AS64510"
    assert report["confidence"] == "medium"
    assert report["evidence_details"][0]["evidence"]["loss_hop"]["asn"] == "AS64510"
    assert "downstream_clean" in report["evidence"][0]


def test_explain_json_reports_malformed_baseline(tmp_path):
    endpoint = {
        "input": "zoom.example",
        "hostname": "zoom.example",
        "ip": "203.0.113.10",
        "asn": "AS64500",
        "prefix": "203.0.113.0/24",
        "name": "Example Video",
    }
    baseline_file = tmp_path / "baseline.jsonl"
    baseline_file.write_text("{not-json}\n")

    with patch("netpath.cli.targets_mod.resolve_endpoint", return_value=endpoint):
        result = CliRunner().invoke(
            cli.app,
            ["explain", "zoom.example", "--baseline", str(baseline_file), "--json"],
        )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert "not valid JSON/JSONL" in payload["error"]


def test_monitor_persists_first_snapshot(tmp_path):
    measurement = {
        "asn": "AS64500",
        "target_host": "203.0.113.10",
        "path": [
            {
                "hop": 1,
                "host": "192.0.2.1",
                "asn": "AS64501",
                "loss_pct": 0.0,
                "avg_ms": 10.0,
                "p95_ms": 12.0,
            },
            {
                "hop": 2,
                "host": "203.0.113.10",
                "asn": "AS64500",
                "loss_pct": 0.0,
                "avg_ms": 20.0,
                "p95_ms": 22.0,
            },
        ],
        "throughput": {"download_mbps": 100.0, "upload_mbps": 20.0},
        "jitter_ms": 1.0,
        "path_changes": 0,
        "verdict": {"severity": "ok", "verdict": "Healthy"},
    }
    with patch("netpath.cli._check_deps", return_value=True), \
         patch("netpath.cli._collect_asn_json", return_value=measurement):
        result = CliRunner().invoke(
            cli.app,
            ["monitor", "AS64500", "--store", str(tmp_path), "--no-throughput"],
        )

    assert result.exit_code == 0
    assert "No previous baseline" in result.output
    history = tmp_path / "AS64500.jsonl"
    payload = json.loads(history.read_text().strip())
    assert payload["asn"] == "AS64500"
    assert payload["as_path"] == ["AS64501", "AS64500"]


def test_monitor_target_override_persists_endpoint_specific_history(tmp_path):
    endpoint = {
        "input": "zoom.example",
        "hostname": "zoom.example",
        "ip": "203.0.113.10",
        "asn": "AS64501",
        "prefix": "203.0.113.0/24",
        "name": "Example Video",
    }
    measurement = {
        "target_input": "zoom.example",
        "target_host": "203.0.113.10",
        "resolved_ip": "203.0.113.10",
        "target_asn": "AS64501",
        "target_name": "Example Video",
        "path": [
            {
                "hop": 1,
                "host": "203.0.113.1",
                "asn": "AS64501",
                "loss_pct": 0.0,
                "avg_ms": 10.0,
                "p95_ms": 12.0,
            },
        ],
        "throughput": None,
        "verdict": {"severity": "ok", "verdict": "Healthy"},
    }
    with patch("netpath.cli._check_deps", return_value=True), \
         patch("netpath.cli.targets_mod.resolve_endpoint", return_value=endpoint), \
         patch("netpath.cli._collect_endpoint_json", return_value=measurement):
        result = CliRunner().invoke(
            cli.app,
            [
                "monitor", "AS64500",
                "--target", "zoom.example",
                "--store", str(tmp_path),
                "--no-throughput",
            ],
        )

    assert result.exit_code == 0
    history = tmp_path / "AS64500_zoom.example-_203.0.113.10.jsonl"
    payload = json.loads(history.read_text().strip())
    assert payload["asn"] == "AS64500"
    assert payload["monitor_key"] == "AS64500:zoom.example->203.0.113.10"
    assert payload["target_input"] == "zoom.example"
    assert payload["target_asn"] == "AS64501"


def test_monitor_reports_regression_and_can_fail(tmp_path):
    previous = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "asn": "AS64500",
        "target_host": "203.0.113.10",
        "as_path": ["AS64501", "AS64500"],
        "last_rtt_ms": 20.0,
        "p95_rtt_ms": 22.0,
        "loss_pct": 0.0,
        "download_mbps": 100.0,
        "severity": "ok",
        "verdict": "Healthy",
    }
    (tmp_path / "AS64500.jsonl").write_text(json.dumps(previous) + "\n")
    measurement = {
        "asn": "AS64500",
        "target_host": "203.0.113.10",
        "path": [
            {"hop": 1, "host": "198.51.100.1", "asn": "AS64502", "loss_pct": 0.0, "avg_ms": 20.0, "p95_ms": 24.0},
            {"hop": 2, "host": "203.0.113.10", "asn": "AS64500", "loss_pct": 2.5, "avg_ms": 60.0, "p95_ms": 70.0},
        ],
        "throughput": {"download_mbps": 40.0},
        "verdict": {"severity": "warning", "verdict": "Near-target Packet Loss"},
    }
    with patch("netpath.cli._check_deps", return_value=True), \
         patch("netpath.cli._collect_asn_json", return_value=measurement):
        result = CliRunner().invoke(
            cli.app,
            [
                "monitor", "AS64500",
                "--store", str(tmp_path),
                "--no-throughput",
                "--fail-on-regression",
            ],
        )

    assert result.exit_code == 2
    assert "AS path changed" in result.output
    assert "RTT regression" in result.output
    assert "Packet loss increased" in result.output
