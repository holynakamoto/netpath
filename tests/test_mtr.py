from unittest.mock import patch

from netpath.mtr import _all_stars, _compare_as_paths, _parse_traceroute_output, run_traceroute
from netpath.pmtu import probe as pmtu_probe

NORMAL_MULTI_HOP = """\
traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets
 1  192.168.1.1  1.234 ms  1.187 ms  1.120 ms
 2  10.0.0.1  5.432 ms  5.654 ms  5.891 ms
 3  8.8.8.8  10.123 ms  10.456 ms  10.789 ms
"""

ALL_STARS = """\
traceroute to 1.1.1.1 (1.1.1.1), 30 hops max, 60 byte packets
 1  * * *
 2  * * *
 3  * * *
"""

MIXED = """\
traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets
 1  192.168.1.1  1.234 ms  1.187 ms  1.120 ms
 2  * * *
 3  8.8.8.8  10.123 ms  10.456 ms  10.789 ms
"""

SINGLE_HOP = """\
 1  192.168.1.1  1.234 ms  1.187 ms  1.120 ms
"""

# macOS traceroute includes parenthesized IP after hostname
MACOS_FORMAT = """\
traceroute to 8.8.8.8 (8.8.8.8), 64 hops max, 52 byte packets
 1  192.168.1.1 (192.168.1.1)  1.234 ms  1.187 ms  1.120 ms
 2  10.0.0.1 (10.0.0.1)  5.432 ms  5.654 ms  5.891 ms
"""


# _parse_traceroute_output tests

def test_normal_multi_hop_parsed_correctly():
    hubs = _parse_traceroute_output(NORMAL_MULTI_HOP)
    assert len(hubs) == 3
    assert hubs[0]["host"] == "192.168.1.1"
    assert hubs[0]["count"] == 1
    assert hubs[0]["Loss%"] == 0.0
    assert hubs[0]["Avg"] > 0
    assert hubs[1]["host"] == "10.0.0.1"
    assert hubs[2]["host"] == "8.8.8.8"


def test_all_stars_path_parsed_as_filtered():
    hubs = _parse_traceroute_output(ALL_STARS)
    assert len(hubs) == 3
    assert all(h["host"] == "???" for h in hubs)
    assert all(h["Loss%"] == 100.0 for h in hubs)


def test_mixed_path_keeps_responding_hops():
    hubs = _parse_traceroute_output(MIXED)
    assert len(hubs) == 3
    assert hubs[0]["host"] == "192.168.1.1"
    assert hubs[1]["host"] == "???"
    assert hubs[1]["Loss%"] == 100.0
    assert hubs[2]["host"] == "8.8.8.8"


def test_single_hop_path():
    hubs = _parse_traceroute_output(SINGLE_HOP)
    assert len(hubs) == 1
    assert hubs[0]["host"] == "192.168.1.1"
    assert hubs[0]["count"] == 1
    assert hubs[0]["Loss%"] == 0.0


def test_macos_format_with_parenthesized_ip():
    hubs = _parse_traceroute_output(MACOS_FORMAT)
    assert len(hubs) == 2
    # First token is the host; parenthesized duplicate is discarded
    assert hubs[0]["host"] == "192.168.1.1"
    assert hubs[1]["host"] == "10.0.0.1"
    assert hubs[0]["Avg"] > 0


# _all_stars tests

def test_all_stars_returns_false_for_empty():
    assert _all_stars([]) is False


def test_all_stars_returns_true_when_all_filtered():
    hubs = [{"host": "???"}, {"host": "???"}, {"host": "???"}]
    assert _all_stars(hubs) is True


def test_all_stars_returns_false_for_mixed():
    hubs = [{"host": "192.168.1.1"}, {"host": "???"}]
    assert _all_stars(hubs) is False


# _compare_as_paths tests

def test_compare_as_paths_ecmp_two_distinct_paths():
    """Two passes with different ASN at hop 3 → ecmp_paths=2, path_changes=1."""
    hubset_a = [
        {"count": 1, "host": "192.168.1.1", "ASN": "AS65001"},
        {"count": 2, "host": "10.0.0.1",    "ASN": "AS65002"},
        {"count": 3, "host": "203.0.113.1",  "ASN": "AS65003"},
    ]
    hubset_b = [
        {"count": 1, "host": "192.168.1.1", "ASN": "AS65001"},
        {"count": 2, "host": "10.0.0.2",    "ASN": "AS65002"},
        {"count": 3, "host": "203.0.114.1",  "ASN": "AS65004"},
    ]
    result = _compare_as_paths([hubset_a, hubset_b])
    assert result["ecmp_paths"] == 2
    assert result["path_changes"] == 1


def test_compare_as_paths_identical_passes():
    """Three identical passes → ecmp_paths=1, path_changes=0."""
    hubs = [
        {"count": 1, "host": "192.168.1.1", "ASN": "AS65001"},
        {"count": 2, "host": "8.8.8.8",    "ASN": "AS15169"},
    ]
    result = _compare_as_paths([hubs, hubs, hubs])
    assert result["ecmp_paths"] == 1
    assert result["path_changes"] == 0


def test_compare_as_paths_empty():
    result = _compare_as_paths([])
    assert result["ecmp_paths"] == 1
    assert result["path_changes"] == 0


# run_traceroute probe-count tests

def _run_traceroute_capturing_cmd(probes):
    captured = {}

    def mock_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["timeout"] = kwargs.get("timeout")
        return type("R", (), {"returncode": 0, "stdout": NORMAL_MULTI_HOP, "stderr": ""})()

    with patch("netpath.mtr.subprocess.run", side_effect=mock_run), \
         patch("netpath.mtr._enrich_names"):
        run_traceroute("8.8.8.8", probes=probes)
    return captured


def test_run_traceroute_threads_probe_count():
    """probes=3 is passed through to the traceroute command as -q 3."""
    captured = _run_traceroute_capturing_cmd(3)
    q_idx = captured["cmd"].index("-q")
    assert captured["cmd"][q_idx + 1] == "3"


def test_run_traceroute_caps_probe_count_at_five():
    """probes=10 is capped to -q 5 to bound runtime."""
    captured = _run_traceroute_capturing_cmd(10)
    q_idx = captured["cmd"].index("-q")
    assert captured["cmd"][q_idx + 1] == "5"


def test_run_traceroute_timeout_scales_with_probes():
    """The subprocess timeout grows with the effective probe count."""
    timeout_3 = _run_traceroute_capturing_cmd(3)["timeout"]
    timeout_5 = _run_traceroute_capturing_cmd(10)["timeout"]
    assert timeout_3 is not None and timeout_5 is not None
    assert timeout_5 > timeout_3


# pmtu.probe tests

def test_pmtu_blackhole_large_fails_small_succeeds():
    """Large ping fails (exit 2), small ping succeeds (exit 0) → blackhole=True."""
    def mock_run(cmd, **kwargs):
        size = int(cmd[cmd.index("-s") + 1])
        rc = 2 if size == 1472 else 0
        return type("R", (), {"returncode": rc})()

    with patch("netpath.pmtu.subprocess.run", side_effect=mock_run):
        result = pmtu_probe("203.0.113.1")
    assert result["blackhole"] is True
    assert result["mtu_floor_bytes"] == 64


def test_pmtu_all_probes_fail_no_blackhole():
    """All pings fail → cannot confirm blackhole → blackhole=False, mtu_floor_bytes=None."""
    def mock_run(cmd, **kwargs):
        return type("R", (), {"returncode": 2})()

    with patch("netpath.pmtu.subprocess.run", side_effect=mock_run):
        result = pmtu_probe("203.0.113.1")
    assert result["blackhole"] is False
    assert result["mtu_floor_bytes"] is None


def test_pmtu_subprocess_raises_no_exception():
    """subprocess.run raising OSError does not propagate — returns safe default."""
    def mock_run(cmd, **kwargs):
        raise OSError("permission denied")

    with patch("netpath.pmtu.subprocess.run", side_effect=mock_run):
        result = pmtu_probe("203.0.113.1")
    assert result["blackhole"] is False
    assert result["mtu_floor_bytes"] is None
