# Privacy invariants

Things netpath must never do, no matter what. Each invariant is enforced by an
automated check that runs in CI on every push and pull request (`pytest` in
`.github/workflows/ci.yml`), not by convention or review. If a change violates
one of these, CI fails.

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
sent to the external geolocation API. The filter lives at the egress point
(`geolocate_hosts`), so a new caller that forgets to pre-filter cannot leak.

- Enforced by: `geolocate_hosts` in `src/netpath/globe.py`
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
