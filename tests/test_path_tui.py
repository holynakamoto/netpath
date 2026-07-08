import sys

import pytest

from netpath.path_tui import build_command


@pytest.mark.parametrize(
    ("mode", "primary", "secondary", "expected"),
    [
        ("host", "example.com", "yes", ["host", "example.com", "--throughput"]),
        ("asn", "AS15169", "2", ["asn", "AS15169", "--count", "2"]),
        ("country", "IL", "5", ["country", "IL", "--top", "5"]),
        ("dns", "example.com", "AAAA", ["dns", "example.com", "AAAA", "--once"]),
        ("explain", "example.com", "", ["explain", "example.com"]),
        ("monitor", "AS15169", "example.com", ["monitor", "AS15169", "--runs", "1", "--target", "example.com"]),
        ("target", "AS7018", "1.1.1.1", ["target", "AS7018", "--target", "1.1.1.1"]),
        ("coverage", "", "", ["coverage", "--top", "50"]),
    ],
)
def test_build_command(mode, primary, secondary, expected):
    assert build_command(mode, primary, secondary) == [
        sys.executable,
        "-m",
        "netpath",
        *expected,
    ]
