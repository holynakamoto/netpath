---
defract:
  id: task-auditing-iperf3-ripe-atlas-endpoint-01kwfw7s6vws
  type: bug
  status: active
  stage: implementation
  phase: 0
  total_phases: 2
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

## Story Brief

# Auditing iperf3 + RIPE Atlas endpoint validity

# Auditing iperf3 + RIPE Atlas endpoint validity

## What We're Building

Two complementary improvements to how netpath selects and measures endpoints. First, we are fixing two bugs in the iperf3 server selection logic that cause country sweeps to silently skip valid servers and accept broken ones as healthy. Second, we are adding an opt-in RIPE Atlas measurement mode that schedules real traceroute and ping measurements from probes physically located inside each target network, replacing today's single-vantage outbound view with a true multi-region picture of each ISP's path characteristics.

## Expected Outcome

- Country sweeps consistently find and use working iperf3 servers rather than skipping valid ones because dead servers appeared first in the list
- Servers that accept a connection but cannot complete an iperf3 test are rejected during validation rather than being counted as healthy
- Users with a RIPE Atlas API key can run a country sweep and receive path data measured from inside each target network, not just from their own vantage point
- Each target network's paths are characterized from two directions: traffic leaving the ISP and traffic arriving at the ISP from the rest of the country
- Country sweeps that exceed the user's Atlas credit budget are refused or trimmed before any credits are spent
- The tool exits gracefully when a target network has no Atlas probes available, recording the gap without failing the whole sweep

## Phase Outcomes

- **Phase 1: Fix server selection** — Country sweeps reliably find and use working iperf3 servers; dead servers no longer block discovery of live ones, and servers that appear connectable but fail actual tests are caught and rejected before being used.
- **Phase 2: RIPE Atlas measurement mode** — Users with an Atlas API key gain an opt-in mode that measures each ISP's paths from probes physically inside those networks, surfacing inbound path quality that is invisible from a single external vantage point.

## Out of Scope

- Changes to single-ASN probe mode — only the country sweep gains the Atlas measurement path
- Scheduling Atlas measurements toward targets outside the country being swept
- A separate "fetch results later" command — Atlas polling runs inline within the same sweep command

## Scope Summary

**Size:** 12 requirements, 14 acceptance criteria, 2 implementation phases
**Key decisions:**
- iperf3 protocol validation during server selection uses a 1-second test measurement rather than extending the TCP socket check — deep validation without excessive latency
- RIPE Atlas integration lives in a new `atlas.py` module following the single-purpose measurement module convention
- Credit budget check runs before any measurements are scheduled; if the full sweep cost exceeds available credits the tool aborts before spending anything
**Biggest risk:** RIPE Atlas measurement latency — Atlas traceroutes can take 4–8 minutes to complete; polling inline may significantly extend the country sweep duration for users who opt in.

## Context

`servers.find_servers_in_asn()` in `src/netpath/servers.py` (lines 75–83) truncates its candidate list to `max_count` (default 3) before running the TCP liveness check, so if the first 3 candidates are all dead the function returns an empty list even when live servers exist later in the list. Separately, `_is_alive()` (lines 67–72) only verifies TCP connectivity via `socket.create_connection`; a server can pass that check but fail the actual iperf3 protocol handshake, causing `run_bidirectional()` to raise `RuntimeError` during the sweep. The country command currently has no RIPE Atlas integration; `country.py` already calls `_get_atlas_probe_ip()` to find probe IPs for fallback routing, so probe-discovery infrastructure is partially in place. All Atlas API calls can use the existing `_with_retry()` helper from `utils.py` and the `requests` library already in the runtime dependencies.

## Requirements

### Server Selection Bug Fixes

- R1: `find_servers_in_asn()` must run the liveness check across all ASN-matching candidates before truncating to `max_count`, so dead servers earlier in the list do not prevent live servers from being found. (Fix is in `src/netpath/servers.py` lines 75–83: move the `[:max_count]` slice after the liveness filter.)
- R2: The liveness check must verify the iperf3 protocol, not just TCP connectivity. A server that accepts a TCP connection but cannot complete an iperf3 exchange must be excluded. (Replace `_is_alive()` with `_is_iperf3_alive()` that runs `iperf3 -c host -p port -t 1 -J` with a 15-second timeout, treating a zero-exit-code JSON response as live.)
- R3: The iperf3 validation probe must use a 1-second duration and must not store or surface its bandwidth results — it only confirms the server is functional.
- R4: When `iperf3` is not in PATH (`iperf.available()` returns False), `_is_iperf3_alive()` must fall back to the existing TCP `socket.create_connection` check so environments without iperf3 are not broken.

### RIPE Atlas Integration

- R5: The `country` subcommand must accept an `--atlas-key` option (string, optional). When omitted the sweep runs exactly as today. When provided, the sweep additionally schedules RIPE Atlas measurements for each target ASN.
- R6: Before scheduling any measurements, the tool must query the Atlas credits endpoint and calculate the total cost of the planned sweep (one ping + one traceroute per ASN with probes available). If the estimated cost exceeds available credits the sweep must abort with an explanatory message before any credits are spent.
- R7: For each target ASN, the tool must query the Atlas API for connected probes (`status=1`) inside that ASN and select up to 3. If no probes exist for an ASN, that ASN is skipped for Atlas measurements and `"atlas": "no probes available"` is recorded in that ASN's `probe_errors`.
- R8: For each ASN with available probes, the tool must schedule one ping measurement and one traceroute measurement as one-off Atlas measurements: ping toward the ASN's own test IP (inbound path) and traceroute toward the user's public IP (outbound path).
- R9: After scheduling, the tool must poll the Atlas API until all measurements reach `stopped` or `failed` status, with a 600-second timeout. Measurements not completing within the timeout are recorded in `probe_errors` as `"atlas": "timed out"` without failing the sweep.
- R10: Atlas measurement results — RTT statistics from ping and AS hop sequence from traceroute — must be merged into the per-ASN summary row, labeled to distinguish Atlas-sourced values from locally-measured ones.
- R11: All Atlas API calls must use the `_with_retry()` helper from `utils.py` and pass the key as the `Authorization: Key {atlas_key}` header.
- R12: A new `src/netpath/atlas.py` module must own all Atlas API logic: probe discovery, credit budget check, measurement scheduling, result polling, and result parsing. No Atlas API calls belong in `cli.py` or `country.py`.

## Acceptance Criteria

- [ ] Given an ASN with 5 candidates where the first 3 are dead and the last 2 are live, `find_servers_in_asn(asn, max_count=3)` returns the 2 live servers rather than an empty list. (Verified by unit test in `tests/test_servers.py` mocking `_is_iperf3_alive`.)
- [ ] A server that passes TCP connect but whose `iperf3 -t 1` returns a non-zero exit code is excluded from `find_servers_in_asn()` results. (Verified by unit test mocking `subprocess.run`.)
- [ ] The iperf3 validation probe uses a 1-second duration and does not appear in the function's return value or any side effects.
- [ ] When `iperf3` is not in PATH, `_is_iperf3_alive()` falls back to TCP connect and `find_servers_in_asn()` returns live servers as before.
- [ ] Running `netpath country ZA` without `--atlas-key` produces identical output to today's behavior (no regression).
- [ ] Running `netpath country ZA --atlas-key <key>` with insufficient credits prints a clear error and exits before creating any Atlas measurements.
- [ ] Running `netpath country ZA --atlas-key <key>` for an ASN with no Atlas probes records `"atlas": "no probes available"` in that ASN's probe errors and continues to the next ASN.
- [ ] Atlas measurement IDs are printed or logged so a user can look them up on the Atlas web interface.
- [ ] Atlas ping RTT statistics (min/avg/max) appear in the per-ASN summary when `--atlas-key` is provided, labeled to distinguish them from locally-measured latency.
- [ ] Atlas traceroute AS-hop sequences appear in the per-ASN summary when `--atlas-key` is provided, labeled as inbound or outbound path.
- [ ] Measurements not completing within 600 seconds are recorded as timed-out errors without hanging the sweep indefinitely.
- [ ] All Atlas API calls pass the key as `Authorization: Key {key}` and go through `_with_retry()`.
- [ ] `src/netpath/atlas.py` contains all Atlas API interaction; `cli.py` and `country.py` contain no direct Atlas API calls.
- [ ] `ruff check src tests` reports no errors after both phases.

## Implementation Phases

### Phase 1: Fix iperf3 server selection bugs
**Scope:** Move the `max_count` truncation after the liveness check in `find_servers_in_asn()`, and replace the TCP-only `_is_alive()` with an iperf3 protocol-level check that runs a 1-second test measurement, with a TCP fallback when iperf3 is absent.
**Files:**
- `src/netpath/servers.py` — reorder truncation after liveness, replace `_is_alive` with `_is_iperf3_alive` using `subprocess.run`, add TCP fallback when `iperf.available()` is False
- `tests/test_servers.py` — new test file covering corrected selection order and protocol-level rejection
**Verification:**
- [ ] `find_servers_in_asn` with mocked liveness returns servers from beyond the first `max_count` candidates when early ones are dead
- [ ] A server passing TCP connect but failing `iperf3 -t 1` is excluded from results
- [ ] When iperf3 is absent, `_is_iperf3_alive` falls back to TCP connect
- [ ] `pytest tests/test_servers.py` passes
- [ ] `ruff check src tests` passes
**Estimated effort:** Small

### Phase 2: RIPE Atlas measurement mode
**Scope:** Add `--atlas-key` to the country subcommand and implement the full Atlas flow — credit budget check, probe discovery, measurement scheduling, result polling, and result display — in a new `atlas.py` module.
**Files:**
- `src/netpath/atlas.py` — new module: `check_budget()`, `find_probes_in_asn()`, `schedule_measurements()`, `poll_until_done()`, `parse_results()`
- `src/netpath/cli.py` — add `--atlas-key` option to `country` command; wire Atlas flow into per-ASN loop; merge Atlas results into summary rows
- `src/netpath/display.py` — extend per-ASN summary to render Atlas RTT and AS-path fields when present, conditionally so the non-Atlas layout is unchanged
**Verification:**
- [ ] `netpath country ZA` without `--atlas-key` produces identical output (no regression)
- [ ] Credit budget refusal exits before any measurements are created
- [ ] No-probe ASNs record `atlas` key in `probe_errors` and sweep continues
- [ ] Atlas RTT and AS-path values appear in per-ASN summary when key is provided
- [ ] Measurements not completing within 600 s are recorded as timed-out errors
- [ ] `ruff check src tests` passes
**Estimated effort:** Large

## Edge Cases

- All servers for an ASN fail the new iperf3 protocol check: `find_servers_in_asn` returns `[]` and the country command falls back to the existing traceroute-only path — no change to downstream behavior.
- RIPE Atlas API returns HTTP 429: `_with_retry()` handles backoff; if all retries exhaust, that ASN's Atlas measurements are recorded in `probe_errors` and the sweep continues.
- Atlas measurement completes with all probes reporting errors (e.g., ICMP blocked): results are surfaced as partial with a warning, not treated as a fatal error.
- Country sweep with `--top 50` and `--atlas-key`: budget check must account for all 50 ASNs; if cost exceeds credits the tool aborts before spending anything — it does not silently run a subset.
- iperf3 binary absent at validation time: `_is_iperf3_alive` falls back to TCP connect, preserving today's behavior for environments without iperf3 installed.

## Technical Notes

- The iperf3 validation in Phase 1 calls `subprocess.run(["iperf3", "-c", ip, "-p", str(port), "-t", "1", "-J"], timeout=15, capture_output=True)`. Zero exit code and parseable JSON with no `error` field constitutes "alive." Non-zero exit or unparseable output constitutes "dead."
- RIPE Atlas REST API v4 base URL: `https://atlas.ripe.net/api/v4/`. Relevant endpoints — credits: `/api/v4/credits/`; probe search: `/api/v4/probes/?asn_v4={asn_number}&status=1`; measurement create: `/api/v4/measurements/`; measurement status: `/api/v4/measurements/{id}/`.
- Measurement types: `traceroute` (TCP, port 80, Paris ID 6, one-off) and `ping` (3 packets, one-off). Use `is_oneoff: true` to avoid recurring charges.
- The user's public IP for outbound measurements can be obtained via `_with_retry` against `https://api.ipify.org?format=json`; cache it once per sweep run.
- Atlas traceroute JSON result shape: `result[].result[].hop[].result[].from` for AS path reconstruction. Cymru bulk lookup can resolve the hop IPs to ASNs, reusing the existing `cymru_bulk_lookup` function from `asn.py`.
- `display.py` changes must be additive and conditional — render Atlas columns only when Atlas result keys are present in the summary dict, so the non-Atlas table layout is pixel-identical to today.

### Dependencies

- RIPE Atlas REST API — no new Python package required; `requests` is already in runtime deps
- `iperf3` binary — already a system prerequisite; Phase 1 validation degrades gracefully when absent

## Implementation Notes

## Phase 1: Fix iperf3 server selection bugs

### Changes

**`src/netpath/servers.py`**
- Added module-level import of `from . import iperf as _iperf`
- Added `json` and `subprocess` stdlib imports
- Renamed `_is_alive` to `_tcp_alive` (TCP-only check, kept for fallback use)
- Added `_is_iperf3_alive(ip, port)`: runs `iperf3 -c ip -p port -t 1 -J` with 15s timeout; zero exit code + parseable JSON with no `error` field = alive; falls back to `_tcp_alive` when `iperf.available()` returns False
- `find_servers_in_asn`: moved `[:max_count]` truncation after the liveness filter; liveness now uses `_is_iperf3_alive`

**`tests/test_servers.py`** (rewritten)
- `test_tcp_alive_returns_false_on_oserror` — TCP fallback behaves correctly on error
- `test_tcp_alive_returns_true_on_success` — TCP fallback succeeds
- `test_is_iperf3_alive_true_on_zero_exit_valid_json` — happy path
- `test_is_iperf3_alive_false_on_nonzero_exit` — rejected on non-zero exit
- `test_is_iperf3_alive_false_when_json_has_error_field` — rejected when JSON contains `error` key
- `test_is_iperf3_alive_falls_back_to_tcp_when_iperf3_absent` — TCP fallback when iperf3 absent
- `test_is_iperf3_alive_false_on_timeout` — TimeoutExpired returns False
- `test_find_servers_in_asn_checks_all_candidates_before_truncating` — 5 candidates, first 3 dead, returns 2 live
- `test_find_servers_in_asn_respects_max_count_after_filter` — 5 live servers, max_count=3 returns 3
- `test_find_servers_in_asn_excludes_server_failing_iperf3_protocol` — TCP-only server excluded

### Result
70/70 tests pass. ruff reports no errors.

## Phase 2: RIPE Atlas measurement mode

### Changes

**`src/netpath/atlas.py`** (new)
- `get_public_ip()`: fetches caller's IPv4 via ipify, used once per sweep as the traceroute target
- `find_probes_in_asn(asn, atlas_key)`: queries Atlas v4 probes endpoint with `asn_v4` + `status=1`, returns up to 3 probe IDs; returns `[]` on any failure
- `check_budget(probes_by_asn, atlas_key)`: sums probe counts × (PING_CREDITS=1 + TRACE_CREDITS=10), queries `/api/v4/credits/`, returns `(sufficient, cost, balance)`
- `schedule_measurements(probe_ids, target_ip, user_ip, atlas_key)`: two sequential POST requests — ping to `target_ip`, traceroute (TCP/80, paris=6) to `user_ip`; returns `{"ping": id, "traceroute": id}`; raises on API error
- `poll_until_done(measurement_ids, atlas_key, timeout=600)`: polls with 30-second sleep intervals; terminal statuses: stopped, forced to stop, no suitable probes, failed, denied; returns `{id: status_name}` with `"timed_out"` for stragglers
- `fetch_results(measurement_id, atlas_key)`: fetches `/api/v4/measurements/{id}/results/`; returns `[]` on failure
- `parse_ping_rtt(results)`: extracts RTTs from `result[probe].result[pkt].rtt`, returns `{min, avg, max}` or None
- `parse_traceroute_as_path(results)`: collects unique hop IPs, resolves via `cymru_bulk_lookup`, walks first probe's hop list to build deduplicated AS sequence

**`src/netpath/cli.py`**
- Added `atlas as atlas_mod` import
- Added `_set_atlas_error(rows, asn, msg)` module-level helper
- Added `--atlas-key` / `NETPATH_ATLAS_KEY` option to `country` command
- Pre-sweep: discovers Atlas probes for all target ASNs, gets user's public IP, checks credit budget (aborts if insufficient)
- Per-ASN loop: tracks test IP per ASN (`_atlas_test_ips`) as ping target for Atlas measurements
- Post-sweep: schedules ping + traceroute for each ASN with probes (prints measurement IDs), polls all measurements with 600-second timeout, fetches + parses results, merges `atlas` dict into each summary row
- No-probe and timed-out ASNs get `probe_errors["atlas"]` set

**`src/netpath/display.py`**
- Added `_render_atlas_subrow(r, is_last_in_group)`: prints optional indented `[Atlas] RTT X ms avg, AS-path` line beneath each ISP row; no-op when `r.get("atlas")` is absent
- Called in `country_summary` for both complete and incomplete path rows
- Non-Atlas layout is pixel-identical (function is a no-op when Atlas key was not used)

### Decisions
- Probe discovery runs before the regular sweep so the budget check uses exact probe counts
- All Atlas measurements are scheduled after the regular sweep completes, then polled in one shared 600-second window — faster than per-ASN schedule+poll

### Result
70/70 tests pass. ruff reports no errors.
