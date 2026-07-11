from pathlib import Path
import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from netpath import local_capture


def test_dns_prompt_builds_bounded_truncated_packet_plan():
    spec = local_capture.plan_capture(
        "Watch DNS traffic and explain unusual latency for 2 minutes",
        interface="en0",
    )

    assert spec.target.value == "dns"
    assert spec.duration_seconds == 120
    assert spec.filter_bpf == "(udp or tcp) and (port 53)"
    assert spec.privacy_level == "truncated_packets"
    assert spec.retention == "delete_immediately"


def test_zoom_prompt_uses_observed_endpoints():
    with patch(
        "netpath.local_capture._process_hosts",
        return_value=("3.7.35.1", "18.204.10.2"),
    ):
        spec = local_capture.plan_capture(
            "Capture my Zoom call for 5 minutes",
            interface="en0",
        )

    assert spec.duration_seconds == 300
    assert spec.filter_bpf == (
        "(udp) and (host 3.7.35.1 or host 18.204.10.2)"
    )


def test_other_device_request_fails_closed():
    with pytest.raises(local_capture.CapturePlanError, match="another device"):
        local_capture.plan_capture(
            "Analyze PlayStation traffic from 192.168.1.212",
            interface="en0",
        )


def test_unknown_prompt_fails_without_capture():
    with pytest.raises(local_capture.CapturePlanError, match="AI planner"):
        local_capture.plan_capture(
            "Figure out why everything feels odd",
            interface="en0",
            planner_provider="off",
        )


def test_codex_account_plans_named_app_with_schema_constrained_cli():
    response = Mock(
        returncode=0,
        stdout="""{
            "target_type": "process",
            "target_value": "Slack",
            "protocols": ["tcp", "udp"],
            "hosts": [],
            "ports": [],
            "filter_description": "Active Slack traffic",
            "duration_seconds": 60
        }""",
        stderr="",
    )
    with (
        patch("netpath.local_capture.shutil.which", return_value="/usr/local/bin/codex"),
        patch("netpath.local_capture._run_planner_command", return_value=response) as run,
        patch("netpath.local_capture._process_hosts", return_value=("44.237.180.172",)),
    ):
        spec = local_capture.plan_capture(
            "do a packet capture on my slack traffic",
            interface="en0",
            planner_provider="codex",
        )

    assert spec.target == local_capture.CaptureTarget("process", "Slack")
    assert spec.planner == "llm"
    assert spec.hosts == ("44.237.180.172",)
    command = run.call_args.args[0]
    assert command[:2] == ["/usr/local/bin/codex", "exec"]
    assert "--output-schema" in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--ignore-user-config" in command


def test_ai_process_plan_fails_when_app_has_no_active_endpoints():
    response = Mock(
        returncode=0,
        stdout="""{
            "target_type": "process",
            "target_value": "Slack",
            "protocols": ["tcp"],
            "hosts": [],
            "ports": [],
            "filter_description": "Slack traffic",
            "duration_seconds": 60
        }""",
        stderr="",
    )
    with (
        patch("netpath.local_capture.shutil.which", return_value="/usr/local/bin/codex"),
        patch("netpath.local_capture._run_planner_command", return_value=response),
        patch("netpath.local_capture._process_hosts", return_value=()),
    ):
        with pytest.raises(local_capture.CapturePlanError, match="Start the app"):
            local_capture.plan_capture(
                "capture Slack",
                interface="en0",
                planner_provider="codex",
            )


def test_planner_process_is_exposed_for_cancellation():
    process = Mock(returncode=0)
    process.communicate.return_value = ("planned", "")
    observed = []

    with patch("netpath.local_capture.subprocess.Popen", return_value=process):
        result = local_capture._run_planner_command(
            ["planner", "--json"],
            timeout=60,
            on_process=observed.append,
        )

    assert result.stdout == "planned"
    assert observed == [process, None]


def test_planner_uses_a_dedicated_process_group_without_an_observer():
    process = Mock(returncode=0)
    process.communicate.return_value = ("planned", "")

    with patch("netpath.local_capture.subprocess.Popen", return_value=process) as popen:
        result = local_capture._run_planner_command(["planner"], timeout=60)

    assert result.stdout == "planned"
    assert popen.call_args.kwargs["start_new_session"] is (os.name == "posix")


@pytest.mark.parametrize("duration", ["0 seconds", "31 minutes"])
def test_duration_limits(duration):
    with pytest.raises(local_capture.CapturePlanError, match="duration"):
        local_capture.plan_capture(f"watch my local traffic for {duration}", interface="en0")


def test_validation_rejects_injected_interface():
    spec = local_capture.CaptureSpec(
        target=local_capture.CaptureTarget("protocol", "dns"),
        interface="en0; touch /tmp/nope",
        protocols=("udp",),
        hosts=(),
        ports=(53,),
        filter_description="DNS",
        duration_seconds=10,
    )

    with pytest.raises(local_capture.CapturePlanError, match="interface"):
        local_capture.validate_spec(spec)


def test_tcpdump_command_is_fixed_argv(tmp_path):
    spec = local_capture.plan_capture("watch dns for 10 seconds", interface="en0")

    with patch("netpath.local_capture.shutil.which", return_value="/usr/sbin/tcpdump"):
        command = local_capture.tcpdump_command(
            spec,
            tmp_path / "capture.pcap",
            privileged=False,
        )

    assert command[:9] == [
        "/usr/sbin/tcpdump",
        "-n",
        "-U",
        "-i",
        "en0",
        "-s",
        "128",
        "-C",
        "25",
    ]
    assert command[-1] == "(udp or tcp) and (port 53)"


def test_capture_permission_accepts_cached_sudo():
    runner = Mock(return_value=Mock(returncode=0))
    with (
        patch("netpath.local_capture.os.geteuid", return_value=501),
        patch("netpath.local_capture.shutil.which", return_value="/usr/bin/sudo"),
    ):
        assert local_capture.capture_permission_cached(runner) is True

    assert runner.call_args.args[0] == ["sudo", "-n", "-v"]


def test_capture_permission_rejects_missing_cache():
    runner = Mock(return_value=Mock(returncode=1))
    with (
        patch("netpath.local_capture.os.geteuid", return_value=501),
        patch("netpath.local_capture.shutil.which", return_value="/usr/bin/sudo"),
    ):
        assert local_capture.capture_permission_cached(runner) is False


def test_execute_deletes_capture_after_analysis(tmp_path):
    spec = local_capture.plan_capture("watch dns for 1 second", interface="en0")
    process = Mock(returncode=-15)
    process.communicate.side_effect = [
        subprocess.TimeoutExpired("tcpdump", 1),
        ("", ""),
    ]
    seen: list[Path] = []

    def analyze(path: Path) -> dict:
        assert path.exists()
        seen.append(path)
        return {"packets": 1}

    with (
        patch("netpath.local_capture.Path.expanduser", return_value=tmp_path),
        patch("netpath.local_capture.tcpdump_command", return_value=["tcpdump"]),
        patch("netpath.local_capture._audit"),
    ):
        outcome = local_capture.execute_capture(
            spec,
            analyzer=analyze,
            popen=Mock(return_value=process),
        )

    assert outcome.deleted is True
    assert seen and not seen[0].exists()


def test_execute_exposes_capture_process_for_cancellation(tmp_path):
    spec = local_capture.plan_capture("watch dns for 1 second", interface="en0")
    process = Mock(returncode=0)
    process.communicate.return_value = ("", "")
    observed = []

    with (
        patch("netpath.local_capture.Path.expanduser", return_value=tmp_path),
        patch("netpath.local_capture.tcpdump_command", return_value=["tcpdump"]),
        patch("netpath.local_capture._audit"),
    ):
        local_capture.execute_capture(
            spec,
            analyzer=lambda _path: {"packets": 0},
            popen=Mock(return_value=process),
            on_process=observed.append,
        )

    assert observed == [process, None]


def test_capture_cleanup_does_not_depend_on_process_observer(tmp_path):
    spec = local_capture.plan_capture("watch dns for 1 second", interface="en0")
    process = Mock(returncode=0)
    process.communicate.return_value = ("", "")
    observer = Mock(side_effect=RuntimeError("UI already closed"))

    with (
        patch("netpath.local_capture.Path.expanduser", return_value=tmp_path),
        patch("netpath.local_capture.tcpdump_command", return_value=["tcpdump"]),
        patch("netpath.local_capture._audit"),
    ):
        outcome = local_capture.execute_capture(
            spec,
            analyzer=lambda _path: {"packets": 0},
            popen=Mock(return_value=process),
            on_process=observer,
        )

    assert outcome.deleted is True
    assert list(tmp_path.glob("*.pcap")) == []


def test_execute_deletes_capture_when_analysis_fails(tmp_path):
    spec = local_capture.plan_capture("watch dns for 1 second", interface="en0")
    process = Mock(returncode=-15)
    process.communicate.side_effect = [
        subprocess.TimeoutExpired("tcpdump", 1),
        ("", ""),
    ]
    seen: list[Path] = []

    def fail(path: Path) -> dict:
        seen.append(path)
        raise RuntimeError("analysis failed")

    with (
        patch("netpath.local_capture.Path.expanduser", return_value=tmp_path),
        patch("netpath.local_capture.tcpdump_command", return_value=["tcpdump"]),
        patch("netpath.local_capture._audit"),
    ):
        with pytest.raises(RuntimeError, match="analysis failed"):
            local_capture.execute_capture(
                spec,
                analyzer=fail,
                popen=Mock(return_value=process),
            )

    assert seen and not seen[0].exists()
