"""Invariants — see docs/INVARIANTS.md.

These tests pin rules the system must never break, independent of any feature.
A failure here means a change violated a documented privacy or safety promise;
fix the change, or deliberately amend both docs/INVARIANTS.md and this file.
"""

import ast
import ipaddress
import os.path
import re
import socket
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import netpath
from netpath import asn, globe, local_capture
from netpath.local_capture import CapturePlanError, CaptureSpec, CaptureTarget

SRC_DIR = Path(netpath.__file__).parent
DOCS_FILE = Path(__file__).resolve().parents[1] / "docs" / "INVARIANTS.md"


@lru_cache(maxsize=1)
def _module_trees():
    return tuple(
        (source, ast.parse(source.read_text(encoding="utf-8"), filename=str(source)))
        for source in sorted(SRC_DIR.rglob("*.py"))
    )


def _enclosing_function_names(tree):
    """Map every node id to the name of its outermost enclosing function."""
    names = {}
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(func):
                names.setdefault(id(child), func.name)
    return names


def _list_head(node):
    """First element of a list literal: its string value, '<dynamic>', or None."""
    if isinstance(node, ast.List) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return "<dynamic>"
    return None


def _docstring_node_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


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

    def test_private_addresses_never_reach_the_whois_socket(self):
        mock_sock = Mock()
        mock_sock.recv.return_value = b""
        with patch("netpath.asn.socket.socket", return_value=mock_sock):
            asn.cymru_bulk_lookup(self.PRIVATE + ["8.8.8.8"])
            asn.cymru_bulk_lookup_rich(self.PRIVATE + ["8.8.8.8"])

        assert mock_sock.sendall.call_count == 2
        for call in mock_sock.sendall.call_args_list:
            payload = call.args[0].decode()
            assert "8.8.8.8" in payload
            for private in self.PRIVATE:
                assert private not in payload

    def test_hostnames_never_reach_the_whois_socket(self):
        """Internal hostnames are LAN topology too — only literal IPs go out."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b""
        with patch("netpath.asn.socket.socket", return_value=mock_sock):
            asn.cymru_bulk_lookup(["router.internal.lan", "8.8.8.8"])

        payload = mock_sock.sendall.call_args.args[0].decode()
        assert "8.8.8.8" in payload
        assert "router.internal.lan" not in payload

    def test_all_private_input_makes_no_whois_connection_at_all(self):
        with patch("netpath.asn.socket.socket") as sock:
            assert asn.cymru_bulk_lookup(self.PRIVATE) == {}
            assert asn.cymru_bulk_lookup_rich(self.PRIVATE) == {}
        sock.assert_not_called()


def test_inv5_no_shell_execution():
    """INV-5: no subprocess command is ever built as a shell string."""
    offenders = []
    for source, tree in _module_trees():
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


def test_inv6_every_http_request_has_a_timeout():
    """INV-6: every outbound HTTP request carries an explicit timeout."""
    verbs = {"get", "post", "put", "delete", "head", "patch", "request"}
    offenders = []
    for source, tree in _module_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in verbs
                and isinstance(func.value, ast.Name)
                and func.value.id == "requests"
                and not any(kw.arg == "timeout" for kw in node.keywords)
            ):
                offenders.append(f"{source.name}:{node.lineno} requests.{func.attr}")
    assert not offenders, "requests call without timeout:\n" + "\n".join(offenders)


# Hosts that may appear as a hardcoded destination anywhere in src/netpath/ —
# in a URL literal or a raw socket connect. Everything else — including
# measurement targets and monitor webhooks — must come from the user at
# runtime. Adding a host here is a deliberate egress decision.
ALLOWED_EGRESS_HOSTS = {
    # measurement and lookup APIs
    "api.globalping.io",
    "api.ipify.org",
    "stat.ripe.net",
    "atlas.ripe.net",
    "ip-api.com",
    "www.peeringdb.com",
    "api.cloudflare.com",
    "speed.cloudflare.com",
    "cloudflare-dns.com",
    "export.iperf3serverlist.net",
    "geocoding-api.open-meteo.com",
    # ASN attribution via bulk whois (raw TCP, port 43)
    "whois.cymru.com",
    # assets referenced from generated HTML (loaded by the user's browser)
    "unpkg.com",
    "cdn.plot.ly",
    # documentation links shown in help text
    "github.com",
    # PostHog analytics ingestion endpoint (default POSTHOG_HOST)
    "us.i.posthog.com",
}

_URL_HOST_RE = re.compile(r"https?://([A-Za-z0-9.-]+)")


def _is_public_ip(value):
    try:
        return ipaddress.ip_address(value.strip()).is_global
    except ValueError:
        return False


def test_inv7_hardcoded_egress_hosts_are_allowlisted():
    """INV-7: a hardcoded destination never points anywhere but an allowlisted
    host — whether it appears as a URL literal, a raw socket connect, or a
    bare public-IP literal (the dns.py resolver registry is the one approved
    home for those)."""
    from netpath.dns import PUBLIC_RESOLVERS

    resolver_ips = {resolver.ip for resolver in PUBLIC_RESOLVERS}
    connect_names = {"connect", "connect_ex", "create_connection"}
    offenders = []
    for source, tree in _module_trees():
        docstrings = _docstring_node_ids(tree)
        in_resolver_registry = source.name == "dns.py"
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                for host in _URL_HOST_RE.findall(node.value):
                    if host not in ALLOWED_EGRESS_HOSTS:
                        offenders.append(f"{source.name}:{node.lineno} url {host}")
                if _is_public_ip(node.value) and not (
                    in_resolver_registry and node.value in resolver_ips
                ):
                    offenders.append(
                        f"{source.name}:{node.lineno} public IP {node.value}"
                    )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in connect_names
                and node.args
                and isinstance(node.args[0], ast.Tuple)
                and node.args[0].elts
                and isinstance(node.args[0].elts[0], ast.Constant)
                and isinstance(node.args[0].elts[0].value, str)
                and node.args[0].elts[0].value not in ALLOWED_EGRESS_HOSTS
                and not node.args[0].elts[0].value.startswith("127.")
                and node.args[0].elts[0].value not in ("localhost", "::1", "")
            ):
                offenders.append(
                    f"{source.name}:{node.lineno} connect {node.args[0].elts[0].value}"
                )
    assert not offenders, "non-allowlisted destination:\n" + "\n".join(offenders)


# Binaries netpath may execute. argv[0] of every subprocess call must be one
# of these, unless the call site is individually approved below.
ALLOWED_BINARIES = {
    "ping",
    "mtr",
    "traceroute",
    "dig",
    "iperf3",
    "tcpdump",
    "lsof",
    "sudo",
    "scamper",
    "dublin-traceroute",
    "route",
    "ip",
}

# CLIs the capture planner may resolve via shutil.which — the user's own
# authenticated AI CLI, never a raw API endpoint.
PLANNER_CLIS = {"codex", "claude"}

# Call sites whose argv[0] cannot be resolved statically, each audited:
#   local_capture.default_interface  — iterates ["route" …] / ["ip" …] literals
#   local_capture._run_planner_command — argv from shutil.which(codex|claude),
#     validated upstream in plan_capture
#   mtr._run_traceroute_cmd — argv[0] from traceroute_path() (PATH or /usr/sbin)
#   path_tui.run_* — netpath re-invoking itself via sys.executable
APPROVED_DYNAMIC_ARGV_SITES = {
    ("local_capture.py", "default_interface"),
    ("local_capture.py", "_run_planner_command"),
    ("mtr.py", "_run_traceroute_cmd"),
    ("path_tui.py", "run_structured_command"),
    ("path_tui.py", "run_console_command"),
    ("path_tui.py", "run_country_command"),
}


def test_inv8_only_allowlisted_binaries_are_executed():
    """INV-8: argv[0] of every spawned process is a known binary."""
    spawn_names = {"run", "Popen", "check_output", "check_call", "call"}
    offenders = []
    dynamic_sites = set()
    for source, tree in _module_trees():
        function_of = _enclosing_function_names(tree)

        heads_by_name = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                head = _list_head(node.value)
                if head is not None:
                    scope = function_of.get(id(node), "<module>")
                    key = (scope, node.targets[0].id)
                    heads_by_name.setdefault(key, set()).add(head)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr in spawn_names
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                continue
            scope = function_of.get(id(node), "<module>")
            site = (source.name, scope)
            heads = set()
            if node.args:
                arg = node.args[0]
                head = _list_head(arg)
                if head is not None:
                    heads = {head}
                elif isinstance(arg, ast.Name):
                    heads = heads_by_name.get((scope, arg.id), {"<dynamic>"})
                else:
                    heads = {"<dynamic>"}
            else:
                heads = {"<dynamic>"}
            for head in heads:
                if head == "<dynamic>":
                    dynamic_sites.add(site)
                    if site not in APPROVED_DYNAMIC_ARGV_SITES:
                        offenders.append(
                            f"{source.name}:{node.lineno} dynamic argv in {scope}()"
                        )
                elif os.path.basename(head) not in ALLOWED_BINARIES:
                    offenders.append(f"{source.name}:{node.lineno} spawns {head!r}")

        # shutil.which with a literal name must also stay on the allowlist
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "which"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "shutil"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value not in ALLOWED_BINARIES | PLANNER_CLIS
            ):
                offenders.append(
                    f"{source.name}:{node.lineno} which({node.args[0].value!r})"
                )

    stale = APPROVED_DYNAMIC_ARGV_SITES - dynamic_sites
    assert not offenders, "unapproved executable:\n" + "\n".join(offenders)
    assert not stale, f"stale APPROVED_DYNAMIC_ARGV_SITES entries: {sorted(stale)}"


def test_inv9_sudo_never_prompts_invisibly():
    """INV-9: sudo is always non-interactive (-n) or the visible consent check."""
    offenders = []
    for source, tree in _module_trees():
        for node in ast.walk(tree):
            if _list_head(node) != "sudo":
                continue
            values = [
                elt.value if isinstance(elt, ast.Constant) else None
                for elt in node.elts
            ]
            visible_consent = values == ["sudo", "-v"]
            non_interactive = len(values) >= 2 and values[1] == "-n"
            if not (visible_consent or non_interactive):
                offenders.append(f"{source.name}:{node.lineno} {values}")
    assert not offenders, "sudo without -n or visible consent:\n" + "\n".join(offenders)


def test_inv10_test_suite_cannot_reach_the_network():
    """INV-10: the conftest guard refuses non-loopback connections."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.1)  # fail fast, not hang, if the guard is ever missing
    try:
        with pytest.raises(RuntimeError, match="INV-10"):
            sock.connect(("192.0.2.1", 80))  # TEST-NET-1: never routable
    finally:
        sock.close()


def test_inv11_invariant_docs_and_checks_stay_in_sync():
    """INV-11: every documented invariant names a real check, and vice versa."""
    text = DOCS_FILE.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]

    documented = set()
    for section in sections:
        match = re.match(r"INV-(\d+)", section)
        assert match, f"section without an INV id: {section.splitlines()[0]!r}"
        documented.add(int(match.group(1)))
        assert "Checked by:" in section, f"INV-{match.group(1)} names no check"

    assert documented == set(range(1, max(documented) + 1)), (
        "invariant numbering must be contiguous from INV-1"
    )

    for filename, name in re.findall(r"tests/(\w+\.py)::(\w+)", text):
        referenced = Path(__file__).parent / filename
        assert referenced.exists(), f"docs reference missing file {filename}"
        assert name in referenced.read_text(encoding="utf-8"), (
            f"docs reference missing check {filename}::{name}"
        )

    mentioned = {
        int(number)
        for number in re.findall(r"INV-(\d+)", Path(__file__).read_text(encoding="utf-8"))
    }
    undocumented = mentioned - documented
    assert not undocumented, f"checks reference undocumented invariants: {undocumented}"


# The only modules that may attach a credential to an outbound request. Their
# destinations are pinned by INV-7, so a token can only reach its own API.
CREDENTIAL_BEARING_MODULES = {"globalping.py", "rum.py"}


def test_inv12_credentials_only_flow_from_their_own_api_client():
    """INV-12: an Authorization header is only ever built inside an approved
    API-client module."""
    offenders = []
    seen_bearing = set()
    for source, tree in _module_trees():
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and ("Authorization" in node.value or node.value.startswith("Bearer"))
            ):
                continue
            if source.name in CREDENTIAL_BEARING_MODULES:
                seen_bearing.add(source.name)
            else:
                offenders.append(f"{source.name}:{node.lineno} {node.value!r}")
    assert not offenders, "credential header outside API clients:\n" + "\n".join(offenders)
    stale = CREDENTIAL_BEARING_MODULES - seen_bearing
    assert not stale, f"stale CREDENTIAL_BEARING_MODULES entries: {sorted(stale)}"


# Every call site that can create or modify a file, keyed (file, function).
# New write sites fail this check until deliberately approved here; the
# expected locations are ~/.netpath/, temp dirs, and user-chosen paths.
APPROVED_WRITE_SITES = {
    ("globe.py", "render"),  # globe HTML in a fresh temp dir
    ("globe.py", "render_aspath"),
    ("globe.py", "render_coverage"),
    ("investigation.py", "save_bundle"),  # redacted bundle, user-chosen dir
    ("local_capture.py", "_audit"),  # capture audit log in ~/.netpath/captures
    ("local_capture.py", "_plan_with_cli"),  # planner schema temp file
    ("local_capture.py", "execute_capture"),  # bounded pcap, deleted after use
    ("monitor.py", "append_snapshot"),  # snapshot store in ~/.netpath/monitor
    ("paris.py", "_run_dublin"),  # dublin-traceroute temp working dir
    ("registry.py", "do_POST"),  # opt-in registry server's own store
    ("serve.py", "register_local"),  # ~/.netpath/servers.json
    ("analytics.py", "_get_install_id"),  # anonymous install UUID in ~/.netpath/
}

# .replace/.rename are excluded: they collide with str methods, and a rename's
# content was already written through one of these calls anyway.
_WRITE_ATTRS = {
    "write_text",
    "write_bytes",
    "mkdir",
    "makedirs",
    "mkstemp",
    "mkdtemp",
}
_TEMPFILE_FACTORIES = {"NamedTemporaryFile", "TemporaryDirectory"}


def _is_write_call(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr in _WRITE_ATTRS or func.attr in _TEMPFILE_FACTORIES:
            return True
        if func.attr == "open":  # Path.open — check mode like builtin open
            return _open_mode_writes(node)
    if isinstance(func, ast.Name) and func.id == "open":
        return _open_mode_writes(node)
    return False


def _open_mode_writes(node):
    mode = None
    if len(node.args) > 1:
        mode = node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode = keyword.value
    if mode is None:
        return False  # default mode is read-only
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(flag in mode.value for flag in "wax+")
    return True  # dynamic mode — fail closed, approve the site if legitimate


def test_inv13_file_writes_only_happen_at_approved_sites():
    """INV-13: the set of places that can write to disk is closed."""
    sites = set()
    for source, tree in _module_trees():
        function_of = _enclosing_function_names(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_write_call(node):
                sites.add((source.name, function_of.get(id(node), "<module>")))

    unapproved = sites - APPROVED_WRITE_SITES
    stale = APPROVED_WRITE_SITES - sites
    assert not unapproved, "unapproved write sites:\n" + "\n".join(
        f"{name}:{scope}" for name, scope in sorted(unapproved)
    )
    assert not stale, f"stale APPROVED_WRITE_SITES entries: {sorted(stale)}"
