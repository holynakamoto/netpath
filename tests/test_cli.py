import json
from unittest.mock import patch

from typer.testing import CliRunner
from typer.main import get_command

from netpath import cli


def test_help_lists_product_commands():
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    for command in ("asn", "country", "aspath", "citypath", "target", "coverage"):
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
