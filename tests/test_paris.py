import json
from unittest.mock import patch

import pytest

from netpath import cli
from netpath.mtr import MtrPermissionError
from netpath.paris import (
    ParisError,
    _parse_dublin_outputs,
    _parse_scamper_output,
    detect,
    run,
)


def _dublin_hop(ttl, src=None, rtt_usec=None):
    hop = {"is_last": False, "nat_id": 0, "sent": {"ip": {"ttl": ttl, "dst": "203.0.113.9"}}}
    if src is not None:
        hop["received"] = {"ip": {"src": src, "ttl": 64}}
        hop["rtt_usec"] = rtt_usec
    else:
        hop["received"] = None
        hop["rtt_usec"] = None
    return hop


DUBLIN_RUN_1 = {"flows": {"33434": [
    _dublin_hop(1, "192.0.2.1", 1000),
    _dublin_hop(2, "198.51.100.1", 5000),
    _dublin_hop(3),
]}}

DUBLIN_RUN_2 = {"flows": {"33434": [
    _dublin_hop(1, "192.0.2.1", 3000),
    _dublin_hop(2),
    _dublin_hop(3),
]}}

SCAMPER_OUTPUT = "\n".join([
    json.dumps({"version": "0.1", "type": "cycle-start", "id": 1}),
    json.dumps({
        "type": "trace", "method": "icmp-paris", "dst": "203.0.113.9",
        "attempts": 3, "hop_count": 3, "stop_reason": "COMPLETED",
        "hops": [
            {"addr": "10.0.0.1", "probe_ttl": 1, "probe_id": 0, "rtt": 1.0},
            {"addr": "10.0.0.1", "probe_ttl": 1, "probe_id": 1, "rtt": 2.0},
            {"addr": "10.0.0.1", "probe_ttl": 1, "probe_id": 2, "rtt": 3.0},
            {"addr": "203.0.113.9", "probe_ttl": 3, "probe_id": 0, "rtt": 10.0},
            {"addr": "203.0.113.9", "probe_ttl": 3, "probe_id": 1, "rtt": 12.0},
        ],
    }),
    json.dumps({"type": "cycle-stop", "id": 1}),
])


# detect tests

def test_detect_prefers_dublin_traceroute():
    with patch("netpath.paris.shutil.which", side_effect=lambda b: f"/usr/local/bin/{b}"):
        assert detect() == "dublin-traceroute"


def test_detect_falls_back_to_scamper():
    with patch("netpath.paris.shutil.which",
               side_effect=lambda b: "/usr/local/bin/scamper" if b == "scamper" else None):
        assert detect() == "scamper"


def test_detect_returns_none_when_neither_installed():
    with patch("netpath.paris.shutil.which", return_value=None):
        assert detect() is None


# _parse_dublin_outputs tests

def test_parse_dublin_aggregates_runs_per_ttl():
    hubs = _parse_dublin_outputs([DUBLIN_RUN_1, DUBLIN_RUN_2], probes=2)
    assert len(hubs) == 3
    assert hubs[0]["count"] == 1
    assert hubs[0]["host"] == "192.0.2.1"
    assert hubs[0]["Loss%"] == 0.0
    assert hubs[0]["Avg"] == 2.0  # (1.0 + 3.0) ms / 2
    assert hubs[0]["Best"] == 1.0
    assert hubs[0]["Wrst"] == 3.0
    assert hubs[0]["StDev"] == pytest.approx(1.41, abs=0.01)
    assert hubs[0]["p50"] == 1.0
    assert hubs[0]["p95"] == 3.0
    assert hubs[0]["p99"] == 3.0


def test_parse_dublin_partial_reply_is_fractional_loss():
    hubs = _parse_dublin_outputs([DUBLIN_RUN_1, DUBLIN_RUN_2], probes=2)
    assert hubs[1]["host"] == "198.51.100.1"
    assert hubs[1]["Loss%"] == 50.0
    assert hubs[1]["Avg"] == 5.0
    assert hubs[1]["StDev"] == 0.0


def test_parse_dublin_unresponsive_hop_is_full_loss():
    hubs = _parse_dublin_outputs([DUBLIN_RUN_1, DUBLIN_RUN_2], probes=2)
    assert hubs[2]["host"] == "???"
    assert hubs[2]["Loss%"] == 100.0
    assert hubs[2]["p50"] is None


def test_parse_dublin_empty_payload_raises():
    with pytest.raises(ParisError):
        _parse_dublin_outputs([{"flows": {}}], probes=2)


# _parse_scamper_output tests

def test_parse_scamper_groups_replies_by_ttl():
    hubs = _parse_scamper_output(SCAMPER_OUTPUT)
    assert len(hubs) == 3
    assert hubs[0]["count"] == 1
    assert hubs[0]["host"] == "10.0.0.1"
    assert hubs[0]["Loss%"] == 0.0
    assert hubs[0]["Avg"] == 2.0
    assert hubs[0]["StDev"] == 1.0
    assert hubs[0]["p50"] == 2.0


def test_parse_scamper_fills_gap_ttl_as_unresponsive():
    hubs = _parse_scamper_output(SCAMPER_OUTPUT)
    assert hubs[1]["count"] == 2
    assert hubs[1]["host"] == "???"
    assert hubs[1]["Loss%"] == 100.0


def test_parse_scamper_partial_replies_are_fractional_loss():
    hubs = _parse_scamper_output(SCAMPER_OUTPUT)
    assert hubs[2]["host"] == "203.0.113.9"
    assert hubs[2]["Loss%"] == pytest.approx(33.3, abs=0.1)
    assert hubs[2]["Avg"] == 11.0


def test_parse_scamper_without_trace_object_raises():
    with pytest.raises(ParisError):
        _parse_scamper_output(json.dumps({"type": "cycle-start"}))


# run tests

def test_run_without_binary_raises():
    with patch("netpath.paris.detect", return_value=None):
        with pytest.raises(ParisError):
            run("203.0.113.9")


def test_run_caps_probes_at_five():
    captured = {}

    def mock_dublin(host, probes):
        captured["probes"] = probes
        return [{"count": 1, "host": "192.0.2.1", "Loss%": 0.0}]

    with patch("netpath.paris._run_dublin", side_effect=mock_dublin), \
         patch("netpath.paris._enrich_names"):
        run("203.0.113.9", probes=10, binary="dublin-traceroute")
    assert captured["probes"] == 5


def test_run_scamper_builds_paris_command():
    captured = {}

    def mock_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": SCAMPER_OUTPUT, "stderr": ""})()

    with patch("netpath.paris.subprocess.run", side_effect=mock_run), \
         patch("netpath.paris._enrich_names"):
        run("203.0.113.9", probes=3, binary="scamper")
    trace_arg = captured["cmd"][captured["cmd"].index("-I") + 1]
    assert "icmp-paris" in trace_arg
    assert "-q 3" in trace_arg


def test_run_maps_permission_failure_to_paris_error():
    """A prober that exits non-zero (raw socket denied) raises ParisError, never leaks."""
    def mock_run(cmd, **kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "permission denied"})()

    with patch("netpath.paris.subprocess.run", side_effect=mock_run):
        with pytest.raises(ParisError):
            run("203.0.113.9", binary="scamper")


def test_run_maps_os_error_to_paris_error():
    def mock_run(cmd, **kwargs):
        raise OSError("no such file")

    with patch("netpath.paris.subprocess.run", side_effect=mock_run):
        with pytest.raises(ParisError):
            run("203.0.113.9", binary="scamper")


# cli fallback-chain tests

_PARIS_HUBS = [{"count": 1, "host": "192.0.2.1", "ASN": "AS???", "Loss%": 0.0,
                "Avg": 2.0, "Best": 1.0, "Wrst": 3.0, "StDev": 1.41,
                "p50": 1.0, "p95": 3.0, "p99": 3.0}]


def test_trace_uses_paris_when_mtr_permission_denied():
    with patch("netpath.mtr.run", side_effect=MtrPermissionError("denied")), \
         patch("netpath.paris.detect", return_value="dublin-traceroute"), \
         patch("netpath.paris.run", return_value=_PARIS_HUBS) as paris_run, \
         patch("netpath.mtr.run_traceroute") as traceroute:
        hubs, method = cli._trace("203.0.113.9", 10)
    assert method == "dublin-traceroute"
    assert hubs == _PARIS_HUBS
    paris_run.assert_called_once_with("203.0.113.9", probes=10, binary="dublin-traceroute")
    traceroute.assert_not_called()


def test_trace_uses_traceroute_when_no_paris_binary():
    with patch("netpath.mtr.run", side_effect=MtrPermissionError("denied")), \
         patch("netpath.paris.detect", return_value=None), \
         patch("netpath.mtr.run_traceroute", return_value=_PARIS_HUBS) as traceroute:
        hubs, method = cli._trace("203.0.113.9", 10)
    assert method == "traceroute"
    traceroute.assert_called_once()


def test_trace_falls_through_when_paris_fails():
    with patch("netpath.mtr.run", side_effect=MtrPermissionError("denied")), \
         patch("netpath.paris.detect", return_value="scamper"), \
         patch("netpath.paris.run", side_effect=ParisError("permission denied")), \
         patch("netpath.mtr.run_traceroute", return_value=_PARIS_HUBS) as traceroute:
        hubs, method = cli._trace("203.0.113.9", 10)
    assert method == "traceroute"
    traceroute.assert_called_once()


def test_trace_prefers_mtr_when_it_works():
    with patch("netpath.mtr.run", return_value=_PARIS_HUBS), \
         patch("netpath.paris.detect") as detect_mock:
        hubs, method = cli._trace("203.0.113.9", 10)
    assert method == "mtr"
    detect_mock.assert_not_called()
