from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
from typing import Callable, Literal

MAX_DURATION_SECONDS = 30 * 60
DEFAULT_DURATION_SECONDS = 60
SNAPLEN = 128
MAX_CAPTURE_MIB = 25
_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")
_DURATION_RE = re.compile(r"\b(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m)\b", re.I)
_IP_RE = re.compile(r"(?<![\w:])(?:\d{1,3}\.){3}\d{1,3}(?![\w:])")
_PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "target_type": {"type": "string", "enum": ["process", "protocol", "interface_all"]},
        "target_value": {"type": "string", "maxLength": 80},
        "protocols": {
            "type": "array",
            "items": {"type": "string", "enum": ["tcp", "udp", "icmp", "icmp6"]},
            "maxItems": 4,
        },
        "hosts": {
            "type": "array",
            "items": {"type": "string", "maxLength": 45},
            "maxItems": 20,
        },
        "ports": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1, "maximum": 65535},
            "maxItems": 20,
        },
        "filter_description": {"type": "string", "maxLength": 160},
        "duration_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_DURATION_SECONDS,
        },
    },
    "required": [
        "target_type",
        "target_value",
        "protocols",
        "hosts",
        "ports",
        "filter_description",
        "duration_seconds",
    ],
    "additionalProperties": False,
}


class CapturePlanError(ValueError):
    pass


class CaptureExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureTarget:
    type: Literal["process", "protocol", "interface_all"]
    value: str


@dataclass(frozen=True)
class CaptureSpec:
    target: CaptureTarget
    interface: str
    protocols: tuple[str, ...]
    hosts: tuple[str, ...]
    ports: tuple[int, ...]
    filter_description: str
    duration_seconds: int
    privacy_level: Literal["headers_only"] = "headers_only"
    retention: Literal["delete_immediately"] = "delete_immediately"
    source_prompt: str = ""
    planner: Literal["deterministic", "llm"] = "deterministic"

    @property
    def filter_bpf(self) -> str:
        parts: list[str] = []
        if self.protocols:
            parts.append("(" + " or ".join(self.protocols) + ")")
        if self.hosts:
            parts.append("(" + " or ".join(f"host {host}" for host in self.hosts) + ")")
        if self.ports:
            parts.append("(" + " or ".join(f"port {port}" for port in self.ports) + ")")
        return " and ".join(parts) or "ip or ip6"

    def as_dict(self) -> dict:
        value = asdict(self)
        value["filter_bpf"] = self.filter_bpf
        return value


@dataclass(frozen=True)
class CaptureOutcome:
    report: dict
    deleted: bool
    capture_path: str | None


def _duration(prompt: str) -> int:
    match = _DURATION_RE.search(prompt)
    if not match:
        return DEFAULT_DURATION_SECONDS
    amount = int(match.group(1))
    seconds = amount * 60 if match.group(2).lower().startswith("m") else amount
    if seconds < 1 or seconds > MAX_DURATION_SECONDS:
        raise CapturePlanError(
            f"Capture duration must be between 1 second and {MAX_DURATION_SECONDS // 60} minutes."
        )
    return seconds


def default_interface() -> str:
    commands = (
        ["route", "-n", "get", "default"],
        ["ip", "route", "show", "default"],
    )
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode:
            continue
        match = re.search(r"(?:interface:\s*|dev\s+)([A-Za-z0-9_.:-]+)", result.stdout)
        if match:
            return match.group(1)
    return "en0" if sys_platform() == "darwin" else "any"


def sys_platform() -> str:
    import sys

    return sys.platform


def local_addresses() -> set[str]:
    addresses = {"127.0.0.1", "::1"}
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None):
            addresses.add(item[4][0].split("%", 1)[0])
    except socket.gaierror:
        pass
    return addresses


def _process_hosts(process_names: tuple[str, ...]) -> tuple[str, ...]:
    hosts: set[str] = set()
    for name in process_names:
        try:
            result = subprocess.run(
                ["lsof", "-nP", "-a", "-c", name, "-i"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in result.stdout.splitlines()[1:]:
            for candidate in re.findall(
                r"(?:->)?(\[[0-9a-fA-F:]+\]|(?:\d{1,3}\.){3}\d{1,3}):\d+",
                line,
            ):
                host = candidate.strip("[]")
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    continue
                if host not in local_addresses():
                    hosts.add(host)
    return tuple(sorted(hosts))


def plan_capture(
    prompt: str,
    interface: str | None = None,
    planner_provider: str | None = None,
) -> CaptureSpec:
    clean = " ".join(prompt.split())
    lower = clean.lower()
    if not clean:
        raise CapturePlanError("Describe the local traffic you want to capture.")
    if re.search(r"\b(playstation|xbox|smart\s*tv|console|other device)\b", lower):
        raise CapturePlanError(
            "That appears to be another device. Phase 1 can only capture traffic "
            "to or from this Mac."
        )

    mentioned_ips = []
    for candidate in _IP_RE.findall(clean):
        try:
            mentioned_ips.append(str(ipaddress.ip_address(candidate)))
        except ValueError:
            continue
    foreign = [ip for ip in mentioned_ips if ip not in local_addresses()]
    if foreign and re.search(r"\b(from|device|playstation|xbox|phone|tv|console)\b", lower):
        raise CapturePlanError(
            f"{foreign[0]} is another device. Phase 1 can only capture traffic to or from this Mac."
        )

    chosen_interface = interface or default_interface()
    duration = _duration(clean)
    if re.search(r"\b(dns|domain name|resolver|resolution)\b", lower):
        return validate_spec(CaptureSpec(
            target=CaptureTarget("protocol", "dns"),
            interface=chosen_interface,
            protocols=("udp", "tcp"),
            hosts=(),
            ports=(53,),
            filter_description="Local DNS traffic over UDP or TCP port 53",
            duration_seconds=duration,
            source_prompt=clean,
        ))
    if "zoom" in lower:
        hosts = _process_hosts(("zoom.us", "Zoom"))
        description = "Active Zoom endpoints" if hosts else "Local UDP traffic used by the active call"
        return validate_spec(CaptureSpec(
            target=CaptureTarget("process", "Zoom"),
            interface=chosen_interface,
            protocols=("udp",),
            hosts=hosts,
            ports=(),
            filter_description=description,
            duration_seconds=duration,
            source_prompt=clean,
        ))
    if re.search(
        r"\b(all (?:my )?(?:local )?traffic|this mac|this computer|my traffic|local traffic)\b",
        lower,
    ):
        return validate_spec(CaptureSpec(
            target=CaptureTarget("interface_all", chosen_interface),
            interface=chosen_interface,
            protocols=(),
            hosts=(),
            ports=(),
            filter_description="All IPv4 and IPv6 traffic visible to this Mac",
            duration_seconds=duration,
            source_prompt=clean,
        ))
    provider = (planner_provider or os.getenv("NETPATH_CAPTURE_PLANNER", "off")).lower()
    if provider in {"codex", "claude"}:
        return _plan_with_cli(provider, clean, chosen_interface, duration)
    raise CapturePlanError(
        "This request needs an AI planner. Set NETPATH_CAPTURE_PLANNER=codex or "
        "NETPATH_CAPTURE_PLANNER=claude to reuse that CLI's existing login. "
        "No traffic was captured."
    )


def _planner_prompt(user_prompt: str, duration: int) -> str:
    return (
        "Convert the user's request into a LOCAL packet-capture plan for traffic to or "
        "from this computer. Return only the requested schema. Never return commands or "
        "BPF. Use process for named desktop apps, protocol for named protocols, and "
        "interface_all only when explicitly requested. Hosts must be literal IPs; omit "
        "hosts when unknown. Ports may be empty for apps with dynamic connections. "
        f"Use {duration} seconds unless the user explicitly specifies another duration. "
        "Do not plan captures for another LAN device; describe that limitation in "
        "filter_description and use an empty target_value.\n\n"
        f"User request: {user_prompt}"
    )


def _plan_with_cli(
    provider: str,
    prompt: str,
    interface: str,
    duration: int,
) -> CaptureSpec:
    executable = shutil.which(provider)
    if not executable:
        raise CapturePlanError(
            f"The {provider} CLI is not installed. No traffic was captured."
        )
    schema = json.dumps(_PLANNER_SCHEMA, separators=(",", ":"))
    instruction = _planner_prompt(prompt, duration)
    try:
        if provider == "claude":
            command = [
                executable,
                "--print",
                "--safe-mode",
                "--tools",
                "",
                "--no-session-persistence",
                "--permission-mode",
                "dontAsk",
                "--output-format",
                "json",
                "--json-schema",
                schema,
                instruction,
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tempfile.gettempdir(),
            )
            payload = json.loads(result.stdout or "{}")
            planned = payload.get("structured_output") or payload.get("result") or payload
            if isinstance(planned, str):
                planned = json.loads(planned)
        else:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                encoding="utf-8",
                delete=False,
            ) as schema_file:
                schema_file.write(json.dumps(_PLANNER_SCHEMA))
                schema_path = schema_file.name
            try:
                result = subprocess.run(
                    [
                        executable,
                        "exec",
                        "--ephemeral",
                        "--sandbox",
                        "read-only",
                        "--ignore-user-config",
                        "--ignore-rules",
                        "--skip-git-repo-check",
                        "--cd",
                        tempfile.gettempdir(),
                        "--output-schema",
                        schema_path,
                        instruction,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                planned = json.loads(result.stdout or "{}")
            finally:
                Path(schema_path).unlink(missing_ok=True)
    except subprocess.TimeoutExpired as exc:
        raise CapturePlanError(f"The {provider} planner timed out. No traffic was captured.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CapturePlanError(
            f"The {provider} planner returned an invalid plan. No traffic was captured."
        ) from exc
    if result.returncode:
        detail = (result.stderr or "").strip().splitlines()
        message = detail[-1] if detail else "check that the CLI is signed in"
        raise CapturePlanError(f"The {provider} planner failed: {message}")
    if not isinstance(planned, dict):
        raise CapturePlanError(f"The {provider} planner returned an invalid plan.")
    if not planned.get("target_value"):
        raise CapturePlanError(
            planned.get("filter_description")
            or "That traffic is not visible from this Mac. No traffic was captured."
        )

    target_type = planned.get("target_type")
    target_value = str(planned.get("target_value", "")).strip()
    if target_type not in {"process", "protocol", "interface_all"}:
        raise CapturePlanError(f"The {provider} planner returned an invalid target type.")
    protocols = tuple(planned.get("protocols") or ())
    hosts = tuple(planned.get("hosts") or ())
    ports = tuple(planned.get("ports") or ())
    if target_type == "process":
        observed = _process_hosts((target_value, target_value.lower()))
        if not observed:
            raise CapturePlanError(
                f"No active network endpoints were found for {target_value}. "
                "Start the app and try again; no traffic was captured."
            )
        hosts = observed
        if not protocols:
            protocols = ("tcp", "udp")
    spec = CaptureSpec(
        target=CaptureTarget(target_type, target_value),
        interface=interface,
        protocols=protocols,
        hosts=hosts,
        ports=ports,
        filter_description=str(planned.get("filter_description") or target_value),
        duration_seconds=int(planned.get("duration_seconds") or duration),
        source_prompt=prompt,
        planner="llm",
    )
    return validate_spec(spec)


def validate_spec(spec: CaptureSpec) -> CaptureSpec:
    if not _INTERFACE_RE.fullmatch(spec.interface):
        raise CapturePlanError("Invalid capture interface.")
    if not 1 <= spec.duration_seconds <= MAX_DURATION_SECONDS:
        raise CapturePlanError("Capture duration is outside the allowed range.")
    if spec.privacy_level != "headers_only" or spec.retention != "delete_immediately":
        raise CapturePlanError("Phase 1 only permits headers-only, delete-immediately captures.")
    if any(proto not in {"tcp", "udp", "icmp", "icmp6"} for proto in spec.protocols):
        raise CapturePlanError("Unsupported capture protocol.")
    if any(not 1 <= port <= 65535 for port in spec.ports):
        raise CapturePlanError("Invalid capture port.")
    for host in spec.hosts:
        try:
            ipaddress.ip_address(host)
        except ValueError as exc:
            raise CapturePlanError("Capture hosts must be literal IP addresses.") from exc
    return spec


def tcpdump_command(spec: CaptureSpec, output: Path, *, privileged: bool | None = None) -> list[str]:
    validate_spec(spec)
    tcpdump = shutil.which("tcpdump")
    if not tcpdump:
        raise CaptureExecutionError("tcpdump is required for local capture.")
    if privileged is None:
        privileged = hasattr(os, "geteuid") and os.geteuid() != 0
    command = [tcpdump, "-n", "-U", "-i", spec.interface, "-s", str(SNAPLEN), "-C", str(MAX_CAPTURE_MIB), "-W", "1", "-w", str(output), spec.filter_bpf]
    return ["sudo", "-n", *command] if privileged else command


def _audit(spec: CaptureSpec, *, confirmed_at: str, deleted_at: str | None, error: str | None = None) -> None:
    path = Path("~/.netpath/captures/audit.jsonl").expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "spec": spec.as_dict(),
        "confirmed_at": confirmed_at,
        "deleted_at": deleted_at,
        "error": error,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def analyze_pcap(path: Path) -> dict:
    try:
        import dpkt
    except ImportError as exc:
        raise CaptureExecutionError("dpkt is required to analyze packet captures.") from exc

    if path.stat().st_size <= 24:
        return {
            "packets": 0,
            "captured_bytes": 0,
            "duration_seconds": 0,
            "average_mbps": 0,
            "estimated_jitter_ms": None,
            "tcp_retransmission_indicators": 0,
            "dns": {
                "completed_queries": 0,
                "median_latency_ms": None,
                "max_latency_ms": None,
                "unanswered_queries": 0,
            },
            "top_flows": [],
        }

    packet_count = 0
    wire_bytes = 0
    first_ts: float | None = None
    last_ts: float | None = None
    flows: Counter[tuple[str, str, int, int, str]] = Counter()
    arrivals: dict[tuple[str, str, int, int, str], list[float]] = defaultdict(list)
    dns_queries: dict[tuple[int, str, str], float] = {}
    dns_latencies: list[float] = []
    retransmissions = 0
    highest_seq: dict[tuple[str, str, int, int], int] = {}

    with path.open("rb") as handle:
        reader = dpkt.pcap.Reader(handle)
        for ts, raw in reader:
            packet_count += 1
            wire_bytes += len(raw)
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
            try:
                frame = dpkt.ethernet.Ethernet(raw)
                ip = frame.data
                if isinstance(ip, dpkt.ip.IP):
                    src, dst = socket.inet_ntop(socket.AF_INET, ip.src), socket.inet_ntop(socket.AF_INET, ip.dst)
                elif isinstance(ip, dpkt.ip6.IP6):
                    src, dst = socket.inet_ntop(socket.AF_INET6, ip.src), socket.inet_ntop(socket.AF_INET6, ip.dst)
                else:
                    continue
                transport = ip.data
                if isinstance(transport, dpkt.tcp.TCP):
                    proto, sport, dport = "tcp", transport.sport, transport.dport
                    key = (src, dst, sport, dport)
                    end_seq = transport.seq + len(transport.data)
                    if len(transport.data) and transport.seq < highest_seq.get(key, -1):
                        retransmissions += 1
                    highest_seq[key] = max(highest_seq.get(key, -1), end_seq)
                elif isinstance(transport, dpkt.udp.UDP):
                    proto, sport, dport = "udp", transport.sport, transport.dport
                else:
                    continue
                flow = (src, dst, sport, dport, proto)
                flows[flow] += len(raw)
                arrivals[flow].append(ts)
                if proto == "udp" and (sport == 53 or dport == 53):
                    try:
                        dns = dpkt.dns.DNS(transport.data)
                        name = dns.qd[0].name if dns.qd else ""
                        if dns.qr == dpkt.dns.DNS_Q:
                            dns_queries[(dns.id, src, name)] = ts
                        else:
                            started = dns_queries.get((dns.id, dst, name))
                            if started is not None:
                                dns_latencies.append((ts - started) * 1000)
                    except (dpkt.NeedData, dpkt.UnpackError):
                        pass
            except (ValueError, dpkt.NeedData, dpkt.UnpackError):
                continue

    elapsed = max((last_ts or 0) - (first_ts or 0), 0.001)
    jitter_samples = []
    for stamps in arrivals.values():
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        if len(gaps) > 1:
            mean = sum(gaps) / len(gaps)
            jitter_samples.append(sum(abs(gap - mean) for gap in gaps) / len(gaps) * 1000)
    top_flows = [
        {"source": src, "destination": dst, "source_port": sport, "destination_port": dport, "protocol": proto, "bytes": size}
        for (src, dst, sport, dport, proto), size in flows.most_common(10)
    ]
    dns_sorted = sorted(dns_latencies)
    return {
        "packets": packet_count,
        "captured_bytes": wire_bytes,
        "duration_seconds": round(elapsed, 3),
        "average_mbps": round((wire_bytes * 8 / elapsed) / 1_000_000, 3),
        "estimated_jitter_ms": round(sum(jitter_samples) / len(jitter_samples), 3) if jitter_samples else None,
        "tcp_retransmission_indicators": retransmissions,
        "dns": {
            "completed_queries": len(dns_sorted),
            "median_latency_ms": round(dns_sorted[len(dns_sorted) // 2], 3) if dns_sorted else None,
            "max_latency_ms": round(dns_sorted[-1], 3) if dns_sorted else None,
            "unanswered_queries": max(0, len(dns_queries) - len(dns_sorted)),
        },
        "top_flows": top_flows,
    }


def execute_capture(
    spec: CaptureSpec,
    *,
    analyzer: Callable[[Path], dict] = analyze_pcap,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> CaptureOutcome:
    confirmed_at = datetime.now(timezone.utc).isoformat()
    deleted_at: str | None = None
    error: str | None = None
    path: Path | None = None
    try:
        directory = Path("~/.netpath/captures").expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="capture-", suffix=".pcap", dir=directory)
        os.close(fd)
        path = Path(name)
        command = tcpdump_command(spec, path)
        process = popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            _, stderr = process.communicate(timeout=spec.duration_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            _, stderr = process.communicate(timeout=5)
        if process.returncode not in {0, -15}:
            detail = (stderr or "").strip().splitlines()[-1:] or ["capture failed"]
            if command[0] == "sudo":
                raise CaptureExecutionError(
                    "Packet capture needs permission. Run `sudo -v` in another terminal, then retry."
                )
            raise CaptureExecutionError(detail[0])
        report = analyzer(path)
        path.unlink(missing_ok=True)
        deleted_at = datetime.now(timezone.utc).isoformat()
        return CaptureOutcome(report=report, deleted=True, capture_path=None)
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        if path is not None and spec.retention == "delete_immediately":
            path.unlink(missing_ok=True)
            if deleted_at is None:
                deleted_at = datetime.now(timezone.utc).isoformat()
        _audit(spec, confirmed_at=confirmed_at, deleted_at=deleted_at, error=error)


def format_report(report: dict) -> str:
    dns = report.get("dns") or {}
    lines = [
        "Local capture analysis",
        f"Packets: {report.get('packets', 0):,}",
        f"Captured: {report.get('captured_bytes', 0):,} bytes over {report.get('duration_seconds', 0)}s",
        f"Average throughput: {report.get('average_mbps', 0)} Mbps",
        f"Estimated jitter: {report.get('estimated_jitter_ms') if report.get('estimated_jitter_ms') is not None else 'not enough samples'} ms",
        f"TCP retransmission indicators: {report.get('tcp_retransmission_indicators', 0)}",
    ]
    if dns.get("completed_queries") or dns.get("unanswered_queries"):
        lines.extend([
            "",
            "DNS",
            f"Completed queries: {dns.get('completed_queries', 0)}",
            f"Unanswered queries: {dns.get('unanswered_queries', 0)}",
            f"Median latency: {dns.get('median_latency_ms')} ms",
            f"Maximum latency: {dns.get('max_latency_ms')} ms",
        ])
    if report.get("top_flows"):
        lines.append("\nTop flows")
        for flow in report["top_flows"][:5]:
            lines.append(
                f"{flow['protocol'].upper()} {flow['source']}:{flow['source_port']} → "
                f"{flow['destination']}:{flow['destination_port']} · {flow['bytes']:,} bytes"
            )
    lines.append("\nRaw capture deleted.")
    return "\n".join(lines)
