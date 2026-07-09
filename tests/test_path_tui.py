import asyncio
import importlib
import sys
import json
import os

import pytest

from netpath import local_capture
from netpath.path_tui import CaptureConfirmation, PathTui, build_command, discover_baselines


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
        ("serve", "iperf.example.com", "5202", [
            "serve", "--setup-only", "--advertise-host", "iperf.example.com", "--port", "5202"
        ]),
    ],
)
def test_build_command(mode, primary, secondary, expected):
    assert build_command(mode, primary, secondary) == [
        sys.executable,
        "-m",
        "netpath",
        *expected,
    ]


def test_discover_baselines_uses_latest_snapshot_and_newest_file(tmp_path):
    older = tmp_path / "AS64500.jsonl"
    older.write_text(json.dumps({
        "asn": "AS64500",
        "target_host": "198.51.100.1",
        "timestamp": "2026-07-01T10:00:00+00:00",
    }) + "\n")
    newer = tmp_path / "AS64501_service.jsonl"
    newer.write_text("\n".join([
        json.dumps({"target_input": "old.example"}),
        json.dumps({
            "asn": "AS64501",
            "target_input": "service.example",
            "timestamp": "2026-07-08T12:30:00+00:00",
        }),
    ]) + "\n")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))

    options = discover_baselines(tmp_path)

    assert options[0][1] == str(newer)
    assert "service.example" in options[0][0]
    assert "AS64501" in options[0][0]


def test_discover_baselines_skips_malformed_files(tmp_path):
    (tmp_path / "broken.jsonl").write_text("{nope}\n")

    assert discover_baselines(tmp_path) == []


def test_capture_confirmation_stylesheet_loads():
    spec = local_capture.plan_capture("watch DNS for 10 seconds", interface="en0")

    async def exercise():
        app = PathTui()
        async with app.run_test() as pilot:
            app.push_screen(CaptureConfirmation(spec))
            await pilot.pause()
            assert isinstance(app.screen, CaptureConfirmation)

    asyncio.run(exercise())


def test_capture_planner_selector_defaults_from_environment(monkeypatch):
    import netpath.path_tui as path_tui

    monkeypatch.setenv("NETPATH_CAPTURE_PLANNER", "codex")
    reloaded = importlib.reload(path_tui)

    async def exercise():
        app = reloaded.PathTui(mode="capture")
        async with app.run_test():
            assert str(app.query_one("#planner").value) == "codex"

    try:
        asyncio.run(exercise())
    finally:
        monkeypatch.delenv("NETPATH_CAPTURE_PLANNER", raising=False)
        importlib.reload(path_tui)


def test_capture_planner_selector_defaults_to_codex(monkeypatch):
    import netpath.path_tui as path_tui

    monkeypatch.delenv("NETPATH_CAPTURE_PLANNER", raising=False)
    reloaded = importlib.reload(path_tui)

    async def exercise():
        app = reloaded.PathTui(mode="capture")
        async with app.run_test():
            assert str(app.query_one("#planner").value) == "codex"

    asyncio.run(exercise())
