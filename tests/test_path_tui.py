import asyncio
from contextlib import nullcontext
import importlib
import sys
from unittest.mock import Mock, patch
import json
import os

import pytest
from textual.widgets import DataTable, Input, Static, TabbedContent

from netpath import dns as dns_mod, local_capture
from netpath.investigation import from_payload
from netpath.path_tui import (
    CaptureConfirmation,
    PathTui,
    build_command,
    build_structured_command,
    discover_baselines,
    parse_json_output,
)


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
        ("coverage", "10", "", ["coverage", "--top", "10"]),
        ("coverage", "US", "", ["coverage", "--country", "US"]),
        ("serve", "iperf.example.com", "5202", [
            "serve", "--setup-only", "--no-register-local", "--advertise-host", "iperf.example.com", "--port", "5202"
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


def test_build_structured_command_uses_explain_report_and_optional_snapshot():
    assert build_structured_command(
        "host",
        "api.example.com",
        baseline="/tmp/baseline.jsonl",
    ) == [
        sys.executable,
        "-m",
        "netpath",
        "explain",
        "api.example.com",
        "--json",
        "--baseline",
        "/tmp/baseline.jsonl",
    ]
    assert build_structured_command("dns", "example.com", "AAAA") == [
        sys.executable,
        "-m",
        "netpath",
        "dns",
        "example.com",
        "AAAA",
        "--json",
    ]
    assert build_structured_command(
        "dns",
        "example.com",
        "A",
        dns_timeout=8,
    )[-2:] == ["--timeout", "8"]
    assert build_structured_command("city", "Denver", "London")[3:] == [
        "citypath",
        "Denver",
        "London",
        "--json",
    ]
    assert build_structured_command("aspath", "AS64500", "AS64501")[3:] == [
        "aspath",
        "AS64500",
        "AS64501",
        "--json",
    ]


def test_parse_json_output_tolerates_dependency_note_before_payload():
    assert parse_json_output('mtr unavailable; using traceroute\n{"severity": "ok"}') == {
        "severity": "ok"
    }


def test_default_workbench_fits_an_80_column_terminal():
    async def exercise():
        app = PathTui()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for selector in ("#workspace", "#rail", "#content", "#form", "#verdict", "#tabs"):
                region = app.query_one(selector).region
                assert region.x >= 0
                assert region.x + region.width <= 80
                assert region.y + region.height <= 23
            assert app.query_one("#source", Input).border_title == "Target"
            assert app.query_one("#plan").display

    asyncio.run(exercise())


def test_every_form_control_stays_inside_its_row_at_80_columns():
    async def exercise():
        app = PathTui()
        async with app.run_test(size=(80, 24)) as pilot:
            for mode in (
                "explain",
                "dns",
                "city",
                "aspath",
                "asn",
                "country",
                "monitor",
                "capture",
                "target",
                "coverage",
                "serve",
            ):
                app._switch_mode(mode)
                await pilot.pause()
                controls = app.query_one("#controls").region
                for widget in app.query("#controls > *"):
                    if widget.display:
                        region = widget.region
                        assert region.y >= controls.y
                        assert region.y + region.height <= controls.y + controls.height
                        assert region.x + region.width <= controls.x + controls.width

    asyncio.run(exercise())


def test_narrow_path_result_collapses_chrome_and_exposes_hops():
    candidate = {
        "probe": "Denver",
        "reaches_target": True,
        "rtt_ms": 25.0,
        "path": ["AS64500", "AS64501"],
        "hop_points": [
            {
                "hop": index,
                "ip": f"192.0.2.{index}",
                "label": f"AS{64500 + index}",
                "rtt_ms": index * 5.0,
            }
            for index in range(1, 7)
        ],
    }
    payload = {
        "source_asn": "AS64500",
        "dest_asn": "AS64501",
        "target_ip": "203.0.113.2",
        "target_origin": "atlas",
        "optimal_path": candidate,
        "candidates": [candidate],
    }

    async def exercise():
        app = PathTui(mode="aspath")
        async with app.run_test(size=(80, 24)) as pilot:
            app._apply_result(payload)
            app.query_one("#tabs", TabbedContent).active = "path-tab"
            await pilot.pause()
            assert not app.query_one("#rail").display
            assert not app.query_one("#mode").display
            assert not app.query_one("#form").display
            assert not app.query_one("#candidates").display
            assert app.query_one("#hops", DataTable).region.height >= 10
            assert app.query_one("#hops", DataTable).row_count == 6
            verdict = app.query_one("#verdict", Static).render().plain
            assert "TARGET NETWORK OBSERVED" in verdict
            assert "destination ASN observed" in verdict

            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one("#mode").display
            assert app.query_one("#form").display

    asyncio.run(exercise())


def test_structured_result_renders_verdict_evidence_and_path_natively():
    payload = {
        "verdict": "Near-target Packet Loss",
        "severity": "warning",
        "confidence": "high",
        "culprit_asn": "AS64502",
        "detail": "Loss was reproduced near the destination.",
        "evidence": ["Remote loss was 2.0% across 30 packets."],
        "recommendation": "Escalate with the path evidence.",
        "path": [
            {
                "hop": 1,
                "host": "198.51.100.1",
                "asn": "AS64502",
                "avg_ms": 42.0,
                "loss_pct": 2.0,
            }
        ],
    }

    async def exercise():
        app = PathTui()
        async with app.run_test(size=(100, 30)) as pilot:
            app._apply_investigation(from_payload("host", "api.example.com", payload))
            await pilot.pause()
            verdict = app.query_one("#verdict", Static).render().plain
            findings = app.query_one("#findings", Static).render().plain
            assert "NEAR-TARGET PACKET LOSS" in verdict
            assert "AS64502" in verdict
            assert "api.example.com" in verdict
            assert "Remote loss was 2.0%" in findings
            assert app.query_one("#hops", DataTable).row_count == 1

    asyncio.run(exercise())


def test_dns_result_is_compact_and_separates_exceptions_from_conflicts():
    rows = [
        {
            "name": "Google",
            "location": "Anycast",
            "status": "ok",
            "values": ["216.198.79.1"],
            "elapsed_ms": 24,
            "min_ttl": 60,
        },
        {
            "name": "Cloudflare",
            "location": "Anycast",
            "status": "ok",
            "values": ["216.198.79.1"],
            "elapsed_ms": 30,
            "min_ttl": 55,
        },
        {
            "name": "Bezeq Intl",
            "location": "Israel",
            "status": "none",
            "values": [],
            "elapsed_ms": 1842,
            "min_ttl": None,
        },
    ]
    payload = {
        "domain": "dave.io",
        "record_type": "A",
        "summary": dns_mod.summarize_public_resolver_rows(rows),
        "resolvers": rows,
    }

    async def exercise():
        app = PathTui(mode="dns", source="dave.io", destination="A")
        async with app.run_test(size=(140, 32)) as pilot:
            app._apply_investigation(from_payload("dns", "dave.io", payload))
            await pilot.pause()

            verdict = app.query_one("#verdict", Static).render().plain
            findings = app.query_one("#findings", Static).render().plain
            table = app.query_one("#hops", DataTable)
            assert "MOSTLY CONSISTENT" in verdict
            assert "Assessment  resolver exception" in verdict
            assert "dave.io · A · 3 resolvers" in verdict
            assert not app.query_one("#form").display
            assert "ASSESSMENT" in findings
            assert "No conflicting record was confirmed" in findings
            assert "WHY WE THINK THIS" not in findings
            assert app.query_one("#tabs", TabbedContent).get_tab("path-tab").label.plain == "Resolvers"
            assert table.row_count == 3
            assert table.get_row_at(0)[0] == "Bezeq Intl"
            assert table.get_row_at(0)[2].plain == "NO ANSWER"

            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one("#form").display

    asyncio.run(exercise())


def test_trace_table_collapses_trailing_unanswered_hops():
    payload = {
        "verdict": "Healthy",
        "severity": "ok",
        "confidence": "high",
        "recommendation": "Keep monitoring.",
        "path": [
            {"hop": 1, "host": "192.168.1.1", "asn": "AS???", "avg_ms": 24.9, "loss_pct": 0.0},
            {"hop": 2, "host": "???", "asn": "AS???", "avg_ms": 0.0, "loss_pct": 100.0},
            {"hop": 3, "host": "206.224.66.82", "asn": "AS14593", "avg_ms": 32.5, "loss_pct": 0.0},
        ]
        + [
            {"hop": hop, "host": "???", "asn": "AS???", "avg_ms": 0.0, "loss_pct": 100.0}
            for hop in range(4, 31)
        ],
    }

    async def exercise():
        app = PathTui()
        async with app.run_test(size=(100, 30)) as pilot:
            app._apply_investigation(from_payload("host", "dave.io", payload))
            await pilot.pause()
            table = app.query_one("#hops", DataTable)
            assert table.row_count == 4  # three probed hops plus the summary row
            mid_path = [str(cell) for cell in table.get_row_at(1)]
            assert "* * *" in mid_path
            assert "no reply" in mid_path
            assert "0.0 ms" not in mid_path
            first = [str(cell) for cell in table.get_row_at(0)]
            assert "AS???" not in first
            summary = " ".join(str(cell) for cell in table.get_row_at(3))
            assert "+ 27 hops with no reply" in summary

    asyncio.run(exercise())


def test_editing_inputs_invalidates_the_visible_result_and_export():
    payload = {
        "verdict": "Healthy",
        "severity": "ok",
        "confidence": "high",
        "recommendation": "Keep monitoring.",
    }

    async def exercise():
        app = PathTui(source="old.example")
        async with app.run_test(size=(100, 30)) as pilot:
            app._apply_investigation(from_payload("host", "old.example", payload))
            await pilot.press("escape")
            app.query_one("#source", Input).value = "new.example"
            await pilot.pause()

            assert app.investigation_result is None
            assert app.outcome_available is False
            assert "READY TO INVESTIGATE" in app.query_one(
                "#verdict", Static
            ).render().plain
            assert "Inputs changed" in app.query_one("#status", Static).render().plain
            with patch("netpath.path_tui.investigation.save_bundle") as save:
                app.action_export_bundle()
            save.assert_not_called()

    asyncio.run(exercise())


def test_highlighted_candidate_drives_provenance_and_exported_path():
    first = {
        "probe": "Denver",
        "reaches_target": True,
        "path": ["AS64500", "AS64501"],
        "hop_points": [{"hop": 1, "ip": "192.0.2.1", "label": "AS64500"}],
    }
    second = {
        "probe": "London",
        "reaches_target": False,
        "path": ["AS64510", "AS64501"],
        "hop_points": [{"hop": 1, "ip": "192.0.2.2", "label": "AS64510"}],
    }
    payload = {
        "source_asn": "AS64500",
        "dest_asn": "AS64501",
        "target_ip": "203.0.113.2",
        "optimal_path": first,
        "candidates": [first, second],
    }

    async def exercise():
        app = PathTui(mode="aspath")
        async with app.run_test(size=(100, 30)) as pilot:
            app._apply_result(payload)
            app.query_one("#candidates", DataTable).move_cursor(row=1)
            await pilot.pause()

            verdict = app.query_one("#verdict", Static).render().plain
            assert "London" in verdict
            assert "INCOMPLETE SAMPLE" in verdict
            assert "partial trace" in verdict
            assert app.investigation_result is not None
            assert app.investigation_result.path[0]["ip"] == "192.0.2.2"
            assert app.investigation_result.raw["optimal_path"]["probe"] == "London"
            findings = app.query_one("#findings", Static).render().plain
            assert "selected sampled MTR did not expose" in findings
            assert "Compare another probe" in findings
            app.query_one("#tabs", TabbedContent).active = "raw-tab"
            await pilot.pause()
            raw = "\n".join(strip.text for strip in app.query_one("#console").lines)
            assert '"probe": "London"' in raw

    asyncio.run(exercise())


def test_expert_tool_scope_does_not_promise_a_normalized_bundle():
    async def exercise():
        app = PathTui(mode="asn")
        async with app.run_test(size=(100, 30)):
            findings = app.query_one("#findings", Static).render().plain
            assert "EXPERT TOOL" in findings
            assert "does not produce a normalized verdict" in findings

    asyncio.run(exercise())


def test_export_shortcut_works_while_target_input_has_focus():
    async def exercise():
        app = PathTui()
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.query_one("#source", Input).has_focus
            await pilot.press("f6")
            await pilot.pause()
            status = app.query_one("#status", Static).render().plain
            assert "Run a structured investigation" in status

    asyncio.run(exercise())


def test_diagnose_without_snapshot_passes_no_baseline():
    async def exercise():
        app = PathTui()
        async with app.run_test(size=(100, 30)) as pilot:
            app.query_one("#source", Input).value = "google.com"
            with patch.object(app, "run_structured_command") as run:
                app.action_run_measurement()
                await pilot.pause()
            mode, source, destination, baseline, run_id = run.call_args.args
            assert baseline == ""

    asyncio.run(exercise())


def test_cancelled_run_cannot_overwrite_or_finish_a_new_run():
    async def exercise():
        app = PathTui()
        async with app.run_test(size=(100, 30)):
            first = app._prepare_run()
            app._set_running(True)
            app.action_stop()

            second = app._prepare_run()
            app._set_running(True)
            app._apply_result_if_current(first, {"candidates": []})
            app._finish_run(first)

            assert app.result is None
            assert app.running is True
            assert app.run_generation == second
            app._finish_run(second)
            assert app.running is False

    asyncio.run(exercise())


def test_stop_replaces_the_running_verdict_with_cancelled_state():
    async def exercise():
        app = PathTui()
        async with app.run_test(size=(100, 30)):
            app._prepare_run()
            app._set_running(True)
            app.action_stop()

            verdict = app.query_one("#verdict", Static).render().plain
            findings = app.query_one("#findings", Static).render().plain
            assert "INVESTIGATION STOPPED" in verdict
            assert "collecting evidence" not in verdict
            assert "CANCELLED" in findings

    asyncio.run(exercise())


def test_cancelled_capture_plan_cannot_open_confirmation():
    spec = local_capture.plan_capture("watch DNS for 10 seconds", interface="en0")

    async def exercise():
        app = PathTui(mode="capture")
        async with app.run_test(size=(100, 30)):
            run_id = app._prepare_run()
            app._set_running(True)
            app.action_stop()
            app._capture_plan_ready(run_id, spec)
            assert not isinstance(app.screen, CaptureConfirmation)

    asyncio.run(exercise())


def test_globe_uses_highlighted_path_candidate():
    first = {
        "hop_points": [
            {"lat": 39.7, "lon": -104.9},
            {"lat": 40.7, "lon": -74.0},
        ]
    }
    second = {
        "hop_points": [
            {"lat": 39.7, "lon": -104.9},
            {"lat": 51.5, "lon": -0.1},
        ]
    }

    async def exercise():
        app = PathTui(mode="aspath")
        async with app.run_test(size=(100, 30)):
            app.result = {"optimal_path": first, "candidates": [first, second]}
            app.selected_candidate = 1
            with patch("netpath.path_tui.globe.render_aspath") as render:
                app.action_open_globe()
            assert render.call_args.args[0]["optimal_path"] is second

    asyncio.run(exercise())


def test_unmount_invalidates_run_and_terminates_owned_process():
    app = PathTui()
    process = Mock()
    process.poll.return_value = None
    app.process = process
    app.run_generation = 4

    app.on_unmount()

    assert app.cancel_requested is True
    assert app.run_generation == 5
    assert app.process is None
    process.terminate.assert_called_once_with()


def test_unmount_cleans_owned_group_even_when_leader_has_exited():
    app = PathTui()
    process = Mock()
    process.poll.return_value = 0
    app.process = process

    with patch("netpath.path_tui.processes.terminate_process_tree") as terminate:
        app.on_unmount()

    terminate.assert_called_once_with(process)


def test_tui_reads_globalping_token_for_default_launch(monkeypatch):
    monkeypatch.setenv("NETPATH_GLOBALPING_TOKEN", "test-token")

    assert PathTui().token == "test-token"


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


def test_capture_confirmation_prompts_for_sudo_then_runs():
    spec = local_capture.plan_capture("watch DNS for 10 seconds", interface="en0")
    app = PathTui()
    with (
        patch("netpath.path_tui.local_capture.capture_permission_cached", return_value=False),
        patch("netpath.path_tui.subprocess.run", return_value=Mock(returncode=0)) as sudo,
        patch.object(app, "suspend", return_value=nullcontext()),
        patch.object(app, "run_local_capture") as run_capture,
    ):
        app._capture_confirmed(spec, True)

    sudo.assert_called_once_with(["sudo", "-v"])
    run_capture.assert_called_once_with(spec)


def test_capture_confirmation_stops_when_sudo_is_denied():
    spec = local_capture.plan_capture("watch DNS for 10 seconds", interface="en0")
    app = PathTui()
    with (
        patch("netpath.path_tui.local_capture.capture_permission_cached", return_value=False),
        patch("netpath.path_tui.subprocess.run", return_value=Mock(returncode=1)),
        patch.object(app, "suspend", return_value=nullcontext()),
        patch.object(app, "_set_status") as status,
        patch.object(app, "run_local_capture") as run_capture,
    ):
        app._capture_confirmed(spec, True)

    run_capture.assert_not_called()
    status.assert_called_once_with(
        "Capture cancelled; administrator permission was not granted"
    )
