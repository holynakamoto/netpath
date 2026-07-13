"""Privacy invariants — see docs/INVARIANTS.md.

These tests pin rules the system must never break, independent of any feature.
A failure here means a change violated a documented privacy promise; fix the
change, or deliberately amend both docs/INVARIANTS.md and this file.
"""

import ast
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import netpath
from netpath import globe, local_capture
from netpath.local_capture import CapturePlanError, CaptureSpec, CaptureTarget

SRC_DIR = Path(netpath.__file__).parent


def _valid_spec(**overrides) -> CaptureSpec:
    spec = CaptureSpec(
        target=CaptureTarget(type="protocol", value="dns"),
        interface="en0",
        protocols=("udp", "tcp"),
        hosts=(),
        ports=(53,),
        filter_description="Local DNS traffic over UDP or TCP port 53",
        duration_seconds=60,
    )
    return replace(spec, **overrides) if overrides else spec


class TestInv1CaptureBounds:
    """INV-1: a capture can never persist raw packets or run unbounded."""

    def test_privacy_bounds_are_not_quietly_relaxable(self):
        assert local_capture.SNAPLEN <= 128
        assert local_capture.MAX_CAPTURE_MIB <= 25
        assert local_capture.MAX_DURATION_SECONDS <= 30 * 60

    def test_only_delete_immediately_retention_is_executable(self):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(retention="keep"))

    def test_only_truncated_packets_privacy_level_is_executable(self):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(privacy_level="full_packets"))

    @pytest.mark.parametrize("duration", [0, -1, local_capture.MAX_DURATION_SECONDS + 1])
    def test_duration_outside_bounds_is_rejected(self, duration):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(duration_seconds=duration))

    def test_tcpdump_command_always_truncates_and_caps(self):
        with patch(
            "netpath.local_capture.shutil.which", return_value="/usr/sbin/tcpdump"
        ):
            command = local_capture.tcpdump_command(
                _valid_spec(), Path("/tmp/out.pcap"), privileged=False
            )

        def flag_value(flag: str) -> str:
            return command[command.index(flag) + 1]

        assert flag_value("-s") == str(local_capture.SNAPLEN)
        assert flag_value("-C") == str(local_capture.MAX_CAPTURE_MIB)
        assert flag_value("-W") == "1"
        assert all(isinstance(part, str) for part in command)


class TestInv2FilterFailsClosed:
    """INV-2: capture filters accept only literal IPs, known protocols, valid ports."""

    @pytest.mark.parametrize(
        "hosts",
        [("example.com",), ("8.8.8.8", "evil.example"), ("8.8.8.8; drop table",)],
    )
    def test_non_literal_ip_hosts_are_rejected(self, hosts):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(hosts=hosts))

    @pytest.mark.parametrize("protocols", [("gre",), ("udp", "sctp"), ("any",)])
    def test_unknown_protocols_are_rejected(self, protocols):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(protocols=protocols))

    @pytest.mark.parametrize("ports", [(0,), (65536,), (-1,)])
    def test_out_of_range_ports_are_rejected(self, ports):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(ports=ports))

    @pytest.mark.parametrize(
        "interface",
        ["en0; rm -rf /", "en0 -w /etc/passwd", "", "x" * 33, "en0\n"],
    )
    def test_malformed_interfaces_are_rejected(self, interface):
        with pytest.raises(CapturePlanError):
            local_capture.validate_spec(_valid_spec(interface=interface))

    def test_literal_ips_pass(self):
        spec = _valid_spec(hosts=("8.8.8.8", "2606:4700::1111"))
        assert local_capture.validate_spec(spec) is spec


class TestInv3NoPrivateEgress:
    """INV-3: private/loopback/link-local IPs never reach the geolocation API."""

    PRIVATE = [
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.1.1",
        "fe80::1",
        "fc00::1",
        "::1",
    ]

    def test_private_addresses_are_dropped_at_the_egress_point(self):
        response = Mock(
            ok=True,
            status_code=200,
            json=Mock(
                return_value=[
                    {"status": "success", "query": "8.8.8.8", "lat": 1.0, "lon": 2.0}
                ]
            ),
        )
        with patch("netpath.globe.requests.post", return_value=response) as post:
            globe.geolocate_hosts(self.PRIVATE + ["8.8.8.8"])

        assert post.call_count == 1
        sent = [entry["query"] for entry in post.call_args.kwargs["json"]]
        assert sent == ["8.8.8.8"]

    def test_all_private_input_makes_no_request_at_all(self):
        with patch("netpath.globe.requests.post") as post:
            assert globe.geolocate_hosts(self.PRIVATE) == {}
        post.assert_not_called()


def test_inv5_no_shell_execution():
    """INV-5: no subprocess command is ever built as a shell string."""
    offenders = []
    for source in sorted(SRC_DIR.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    offenders.append(f"{source.name}:{node.lineno} shell=…")
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in {"system", "popen"}
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                offenders.append(f"{source.name}:{node.lineno} os.{func.attr}")
    assert not offenders, "shell-string execution found:\n" + "\n".join(offenders)
