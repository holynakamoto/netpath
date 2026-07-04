import json
from unittest.mock import patch

from typer.testing import CliRunner
from typer.main import get_command

from netpath import cli


def test_help_lists_product_commands():
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    for command in ("asn", "monitor", "country", "aspath", "citypath", "target", "coverage"):
        assert command in result.output


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
        "verdict": {"severity": "ok", "verdict": "Healthy"},
        "pmtu": {"blackhole": False},
        "ecmp_paths": 1,
        "path_changes": 0,
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
    assert payload["verdict"]["severity"] == "ok"


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
