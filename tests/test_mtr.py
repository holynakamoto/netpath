from netpath.mtr import _all_stars, _parse_traceroute_output

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
