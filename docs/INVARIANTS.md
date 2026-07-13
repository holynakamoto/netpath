# Invariants

Things netpath must never do, no matter what. Each invariant is enforced by an
automated check that runs in CI on every push and pull request (`pytest` in
`.github/workflows/ci.yml`), not by convention or review. If a change violates
one of these, CI fails. INV-1 through INV-5 are privacy promises; INV-6 through
INV-11 are operational-safety promises that make a green CI run trustworthy
without human review.

Changing an invariant is allowed — but it must be a deliberate edit to both the
rule here and its check, never a side effect of another change.

## INV-1 — A local capture can never persist raw packets or run unbounded

Every capture is truncated to 128-byte snapshots, capped at 25 MiB and 30
minutes, and the `.pcap` is deleted immediately after analysis — including when
analysis fails. No spec that requests anything else is executable.

- Enforced by: `validate_spec` and `tcpdump_command` in `src/netpath/local_capture.py`
- Checked by: `tests/test_invariants.py::TestInv1CaptureBounds`,
  plus deletion-on-failure behavior in
  `tests/test_local_capture.py::test_execute_deletes_capture_when_analysis_fails`

## INV-2 — A capture filter fails closed

Capture specs accept only literal IP addresses as hosts (never hostnames),
protocols from the fixed allowlist (`tcp`, `udp`, `icmp`, `icmp6`), ports in
1–65535, and interface names matching a strict pattern. Anything else raises
`CapturePlanError` before a command is ever built.

- Enforced by: `validate_spec` in `src/netpath/local_capture.py`
- Checked by: `tests/test_invariants.py::TestInv2FilterFailsClosed`

## INV-3 — A private IP address never leaves the machine

Private, loopback, and link-local addresses (the user's LAN topology) are never
sent to the external geolocation API or the Cymru whois service — and the whois
egress additionally drops anything that is not a literal IP, so an internal
hostname cannot leak either. The filters live at the egress points
(`geolocate_hosts`, `_public_ips`), so a new caller that forgets to pre-filter
cannot leak.

- Enforced by: `geolocate_hosts` in `src/netpath/globe.py` and `_public_ips`
  in `src/netpath/asn.py`
- Checked by: `tests/test_invariants.py::TestInv3NoPrivateEgress`

## INV-4 — A secret never appears in an exported incident bundle

Tokens, cookies, passwords, URL userinfo, and known credential shapes are
redacted from bundle JSON, Markdown, and filenames before anything is written
to disk.

- Enforced by: `_redact_value` / `_redact_text` / `_safe_slug` in
  `src/netpath/investigation.py`
- Checked by:
  `tests/test_investigation.py::test_render_and_save_bundle_are_useful_valid_and_redacted`

## INV-5 — A subprocess command is never built as a shell string

Every external command (mtr, traceroute, iperf3, tcpdump, scamper, …) is an
argv list. `shell=True`, `os.system`, and `os.popen` do not appear anywhere in
`src/netpath/`, so user-supplied targets can never be shell-interpolated.

- Enforced by: convention across all modules
- Checked by: `tests/test_invariants.py::test_inv5_no_shell_execution` (AST scan
  of every source file)

## INV-6 — An outbound HTTP request never runs without a timeout

Every `requests` call in `src/netpath/` passes an explicit `timeout=`, so a
slow or dead external service can never hang a diagnosis indefinitely.

- Enforced by: each call site
- Checked by: `tests/test_invariants.py::test_inv6_every_http_request_has_a_timeout`
  (AST scan of every source file)

## INV-7 — A hardcoded destination never points anywhere but an allowlisted host

Every hardcoded destination in `src/netpath/` resolves to a host on the
allowlist in the check, whatever form it takes: a URL literal (API endpoints,
CDN assets embedded in generated HTML, documentation links in help text), a
raw socket connect (the Cymru whois service), or a bare public-IP literal —
which may live only in the `PUBLIC_RESOLVERS` registry in `src/netpath/dns.py`.
Adding a new egress destination requires a deliberate edit to the allowlist or
that registry. Destinations the user supplies at runtime (measurement targets,
monitor webhooks, custom resolvers) are theirs to choose and are out of scope.

- Enforced by: the allowlist in the check and the `PUBLIC_RESOLVERS` registry
- Checked by: `tests/test_invariants.py::test_inv7_hardcoded_egress_hosts_are_allowlisted`

## INV-8 — Only allowlisted executables are ever spawned

`argv[0]` of every subprocess call is a known network-diagnosis binary (ping,
mtr, traceroute, dig, iperf3, tcpdump, lsof, sudo, scamper, dublin-traceroute,
route, ip). The few call sites that build `argv[0]` dynamically — the AI
planner CLIs resolved via `shutil.which`, the traceroute PATH fallback, and
the TUI re-invoking netpath via `sys.executable` — are individually approved
in the check, and a new dynamic call site fails it.

- Enforced by: literal argv lists at each call site
- Checked by: `tests/test_invariants.py::test_inv8_only_allowlisted_binaries_are_executed`

## INV-9 — sudo never prompts invisibly

Every sudo invocation either uses `-n` (fail instead of prompting) or is the
single visible consent check `sudo -v` that the TUI runs in the foreground
after telling the user why. A password prompt can never appear without the
user knowing what asked for it.

- Enforced by: `tcpdump_command` / `capture_permission_cached` in
  `src/netpath/local_capture.py` and the consent flow in `src/netpath/path_tui.py`
- Checked by: `tests/test_invariants.py::test_inv9_sudo_never_prompts_invisibly`

## INV-10 — The test suite proves behavior without the network

Any socket connection to a non-loopback address fails the test that attempted
it. A green run therefore never depended on live services, never leaked
anything to them, and stays green offline — which is what makes it safe to
trust CI instead of a human reviewer.

- Enforced by: the socket guard in `tests/conftest.py`
- Checked by: `tests/test_invariants.py::test_inv10_test_suite_cannot_reach_the_network`

## INV-11 — An invariant and its check can never drift apart

Every invariant documented here names a check that exists in the test suite,
numbering is contiguous, and every invariant referenced by a check is
documented here. Deleting a check or a doc section without its counterpart
fails CI.

- Enforced by: this file and `tests/test_invariants.py` together
- Checked by: `tests/test_invariants.py::test_inv11_invariant_docs_and_checks_stay_in_sync`

## INV-12 — A credential only flows to its own API

An `Authorization` header is only ever constructed inside the two API-client
modules (`globalping.py` for the Globalping token, `rum.py` for the Cloudflare
token), and INV-7 pins where those modules can send requests. A change that
attaches a token to any other request fails CI.

- Enforced by: header construction confined to `src/netpath/globalping.py`
  and `src/netpath/rum.py`
- Checked by: `tests/test_invariants.py::test_inv12_credentials_only_flow_from_their_own_api_client`

## INV-13 — The set of places that can write to disk is closed

Every call site that creates or modifies a file — `~/.netpath/` stores, the
capture audit log, redacted bundles, temp files — is individually approved in
the check. A new write site anywhere in `src/netpath/` fails CI until it is
deliberately added, and a removed site must be pruned from the approval list.

- Enforced by: the approved-site list in the check
- Checked by: `tests/test_invariants.py::test_inv13_file_writes_only_happen_at_approved_sites`
