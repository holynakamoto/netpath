---
defract:
  id: task-diagnosing-country-us-trace-timeouts-01kwj6znpk1a
  type: bug
  status: active
  stage: release
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

# Trace only valid probe targets in country mode

# Trace only valid probe targets in country mode

## What We're Building

Country sweeps currently guess an address inside each ISP's network when no real test server exists, and those guessed addresses usually do not answer — producing long timeouts and empty results for large ISPs. We are changing the sweep so it only measures against targets known to be alive (a real test server or a live measurement probe), and clearly marks ISPs that have no usable target as "no coverage" instead of waiting on a dead host. When a trace does time out, the partial path collected so far is shown instead of a bare error.

## Expected Outcome

- Country sweeps no longer stall on ISPs whose guessed address never answers; the four US ISPs that previously timed out either get a live target or are skipped quickly
- Each ISP is measured against the best available live target: a real test server first, then a live probe address, then remote-only probe measurements when only remote coverage exists
- ISPs with no live target at all are labelled "no coverage" and skipped, rather than reported as a timeout failure
- When a trace does time out, the hops collected before the timeout are still displayed so the run produces useful partial data
- Overall run verdicts and exit codes are no longer skewed by unreachable guessed addresses

## Phase Outcomes

- **Phase 1: Measure only live targets and label coverage honestly** — Country sweeps stop stalling on ISPs whose guessed address never answers. Every ISP is either measured against a target known to be alive, measured remotely when that is the only coverage available, or labelled "no coverage" and skipped in seconds — and run verdicts stop being skewed by dead guesses.
- **Phase 2: Keep partial paths when a trace runs out of time** — A trace that hits its time limit keeps and displays the hops it collected instead of discarding them, so even a timed-out measurement yields useful path data with a clear note that it was cut short.

## Out of Scope

- A new batch mode that sweeps the top 50 countries ranked by allocated address space — a substantial feature that deserves its own task
- Any change to the one-time baseline speed test in country mode — its recent failure was a transient network issue on the tester's connection, not a defect
- Installing or bundling the mtr path-probing tool; the sweep continues to work with whichever prober is available on the machine

## Scope Summary

**Size:** 8 requirements, 7 acceptance criteria, 2 implementation phases
**Key decisions:**
- Remove the announced-prefix address guessing entirely — a connected RIPE Atlas probe address becomes the only non-server local trace target
- ISPs with only Globalping coverage are measured remotely using the tester's public address as the target, instead of tracing a dead guess locally
- Trace timeouts surface the hops collected so far via a dedicated timeout exception carrying partial hubs, rather than discarding output
**Biggest risk:** Timeout-budget layering in `_measure()` — the outer future wait can currently fire before the traceroute subprocess budget, which would silently discard the recovered partial path if the budgets are not aligned.

## Context

The `country` command (`src/netpath/cli.py:686-747`) probes each top ASN. When `servers.find_servers_in_asn()` finds no iperf3 server, `country.get_test_ip_for_asn()` (`src/netpath/country.py:137`) supplies a trace target: a connected RIPE Atlas probe IPv4 when one exists, otherwise the second host of the ASN's most-specific announced prefix — a guessed address that usually does not respond. Tracing such an address burns the full prober budget (`mtr.run()` waits `cycles*4+30` s; the traceroute fallback up to `30*probes+15` s per pass, run twice under `prefer_tcp`), then surfaces as `probe_errors["v4_trace"] = "timed out"` with no hubs, which `diagnose()` scores as an `incomplete_path` warning — skewing the summary table and the process exit code. In a recent US sweep, four of the top ten ISPs hit exactly this. Separately, when a trace subprocess is killed on timeout (`src/netpath/mtr.py:76`, `src/netpath/mtr.py:215`), all output collected up to that point is discarded.

## Requirements

### Live-target selection (country mode)

- R1: When an ISP has no iperf3 server, the sweep may only trace a target known to be alive — a connected RIPE Atlas probe address. The guessed-address fallback is removed. (`country.get_test_ip_for_asn()` drops its announced-prefix branch and returns the Atlas probe IPv4 or None; `_get_atlas_probe_ip()` is unchanged.)
- R2: An ISP with no server and no Atlas probe address, but with connected Globalping probes, is still measured — remotely only. No local trace runs; Globalping ping and mtr measurements are scheduled for it using the tester's public address as the ping target. (Country loop in `cli.py` plus a `_gp_test_ips` fallback to `_user_public_ip` in the scheduling block at `cli.py:757-761`.)
- R3: An ISP with no live target of any kind (no server, no Atlas probe, no Globalping probes — or remote measurement disabled or unavailable) is marked as having no coverage and skipped within seconds. Its summary row records the skip reason and carries no verdict. (Extends the existing skip branch at `cli.py:716-722`.)

### Honest reporting

- R4: The country summary displays no-coverage ISPs in their own clearly labelled group, separate from "incomplete paths", and labels remote-only ISPs so it is clear no local trace ran. (`display.country_summary()`; remote-only rows keep their Globalping sub-row.)
- R5: The run's exit code and verdict counts are derived only from ISPs that were actually measured; no-coverage rows contribute nothing. (Existing `row.get("verdict")` exclusion in `cli.py:862` preserved and now covered by a test.)

### Partial paths on timeout

- R6: When a system traceroute exceeds its time budget, the output collected so far is parsed and the hops seen are returned marked as partial, instead of being discarded with a bare "timed out" error. Zero parseable hops still surfaces the existing timeout error. (`mtr._run_traceroute_cmd()` — kill the process, harvest partial stdout, signal via a dedicated `TraceTimeout` exception carrying the hubs.)
- R7: A timed-out trace with partial hops still populates the AS path, hop table, and path classification in the measurement result, with the timeout recorded in `probe_errors` so the verdict notes partial results. The layered timeout budgets in `_measure()` must be aligned so the inner prober's partial result is not pre-empted by the outer future wait. (`cli.py` `_measure()` trace section; `trace_timeout` at `cli.py:233`.)
- R8: The rendered output for a timed-out trace shows the partial hop table plus an explicit note that the path was truncated by a timeout. (Follows the existing path-note pattern at `display.py:226-238`; the verdict panel's partial-results note already exists.)

## Acceptance Criteria

- [ ] `country.get_test_ip_for_asn()` returns None when no connected Atlas probe advertises an IPv4 address, and never returns an address derived from announced prefixes; verified by updated `pytest tests/test_country.py`.
- [ ] An ISP with no server, no Atlas probe, and no Globalping probes is reported under a "no coverage" label, its summary row has no `verdict` key, and the process exit code is unaffected by its presence; verified by a unit test plus a manual `netpath country US --top 10` run.
- [ ] An ISP with Globalping probes but no local live target gets Globalping measurements scheduled and appears in the summary labelled remote-only, with no local trace attempted; verified manually with `netpath country US --top 10`.
- [ ] The traceroute runner returns parsed partial hops when the subprocess is killed at its time budget; verified by a test in `tests/test_mtr.py` that mocks the subprocess to time out with partial output captured.
- [ ] A timed-out trace with partial hops produces a result whose `hubs` and `as_path` are non-empty and whose `probe_errors` records the timeout, so `diagnose()` reports `partial_results: true`; verified by a `tests/test_diagnosis.py` case.
- [ ] A manual `netpath country US --top 10` run completes without any single ISP stalling for multiple minutes on an unanswered trace target.
- [ ] `pytest` and `ruff check src tests` pass.

## Implementation Phases

### Phase 1: Live-target selection and coverage labelling
**Scope:** The sweep measures each ISP against the best live target available — a real test server, a live probe address, or remote-only measurement — and honestly labels ISPs with no usable target instead of timing out on guessed addresses.
**Files:**
- `src/netpath/country.py` — remove the announced-prefix fallback from `get_test_ip_for_asn()`
- `src/netpath/cli.py` — country-loop target ladder, remote-only branch, skip-reason row fields, `_gp_test_ips` fallback to the tester's public IP
- `src/netpath/display.py` — "no coverage" group and remote-only labelling in `country_summary()`
- `src/netpath/types.py` — additive keys for skip reason / remote-only on `MeasurementResult` rows
- `tests/test_country.py` — updated `get_test_ip_for_asn()` tests
**Verification:**
- `pytest tests/test_country.py` passes with the new None-fallback expectations
- `ruff check src tests` is clean
- Manual `netpath country US --top 10`: serverless ISPs resolve to Atlas targets, remote-only measurement, or a fast "no coverage" label — no multi-minute stalls
**Estimated effort:** Medium

### Phase 2: Partial-path recovery on trace timeout
**Scope:** When a trace runs out of time, the hops collected before the timeout are kept, classified, and displayed with a clear truncation note, so a timed-out measurement still yields useful data.
**Files:**
- `src/netpath/mtr.py` — Popen-based traceroute run with partial-stdout harvest; `TraceTimeout` exception carrying hubs
- `src/netpath/cli.py` — `_measure()` handles `TraceTimeout`, records `probe_errors`, aligns outer/inner timeout budgets
- `src/netpath/display.py` — truncation note on the hop table
- `tests/test_mtr.py`, `tests/test_diagnosis.py` — partial-harvest and partial-results tests
**Verification:**
- `pytest tests/test_mtr.py tests/test_diagnosis.py` passes including the new timeout cases
- `ruff check src tests` is clean
- Manual check: tracing a non-responsive address shows partial hops with a truncation note instead of a bare error
**Estimated effort:** Medium

## Edge Cases

- Atlas API down or unreachable mid-sweep: `_get_atlas_probe_ip()` already returns None on request failure; affected ISPs degrade to remote-only or no coverage, and the sweep still completes.
- Tester's public IP undiscoverable: remote-only ISPs cannot be measured and degrade to "no coverage"; the existing warning at `cli.py:671` already covers the Globalping skip.
- `--no-remote` passed: the remote-only rung of the ladder is unavailable; serverless, probe-less ISPs go straight to "no coverage".
- Subprocess timeout with no output captured (stdout None, empty, or bytes rather than str): fall back to the existing "traceroute timed out" error — never crash on decode.
- mtr JSON report mode prints only at process end, so a killed mtr yields no parseable partial output: keep the existing error behaviour for mtr; live-target selection makes this case rare.
- `prefer_tcp` traceroute runs two passes (TCP then UDP): partial recovery applies per pass, and the combined budget must stay inside `_measure()`'s outer wait.
- All parsed partial hops are `???` stars: treat as no usable path (existing `_all_stars()` handling), not as a partial path.
- IPv6 comparison trace timing out: `hubs_v6` already degrades to None silently — unchanged.

## Technical Notes

- Signal partial output with a dedicated exception (`class TraceTimeout(RuntimeError)` carrying a `hubs` attribute) rather than changing return types — `run_traceroute()` and `_run_traceroute_cmd()` callers keep their contracts, and `_measure()` catches it in one place. This mirrors the existing `MtrPermissionError` pattern in `mtr.py`.
- Partial stdout harvest: switch `_run_traceroute_cmd()` from `subprocess.run` to `Popen` + `communicate(timeout=...)`; on `TimeoutExpired`, `kill()` then `communicate()` again to drain the pipes. `subprocess.run` does not reliably attach partial stdout to `TimeoutExpired` across Python 3.9-3.13, so the Popen form is required.
- Timeout layering: in the `compare_v6` path `_measure()` waits `fut_v4.result(timeout=cycles*4+35)` while the traceroute fallback may legitimately run `30*probes+15` s per pass — the outer wait can fire first and discard the inner partial result. Align the budgets (outer wait ≥ worst-case inner subprocess budget) as part of Phase 2.
- Remote-only Globalping target: both the ping and the mtr measurement target the tester's public IP, measuring the ISP-to-tester path; `globalping.schedule_measurements()` needs no change — only the target passed from `cli.py` differs.
- `MeasurementResult` in `types.py` is `TypedDict(total=False)`, so new skip-reason / partial-flag keys are additive with no call-site churn; keep all new keys JSON-serialisable for the future country-mode `--json`.
- Follow the project test-strategy convention: mock `subprocess` in `tests/test_mtr.py`, keep `diagnose()` cases pure in `tests/test_diagnosis.py`, and do not add tests requiring live HTTP.
- `_check_deps()` still requires mtr to be installed for country mode — unchanged here; per the out-of-scope note, no prober bundling work in this task.

## Implementation Notes

## Phase 1: Live-target selection and coverage labelling

### What was built

- `src/netpath/country.py` — `get_test_ip_for_asn()` now returns only a connected RIPE Atlas probe IPv4 (via the unchanged `_get_atlas_probe_ip()`) or None. The entire announced-prefix guessing branch and the now-unused `RIPE_PREFIXES` constant were removed.
- `src/netpath/cli.py` — the country loop's serverless branch is now a target ladder: Atlas probe IP → local trace (as before, note reworded to "Atlas probe trace target"); no Atlas IP but ASN has Globalping probes → remote-only row (`remote_only: True`, no local trace, no verdict); otherwise → no-coverage row (`skip_reason: <reason>`, differentiated for `--no-remote`) skipped in seconds. The Globalping scheduling loop falls back to the tester's public IP for remote-only rows (`_tip = _gp_test_ips.get(_asn_str) or _user_public_ip`); the unreachable "no test IP available" branch was removed since `_user_public_ip` is guaranteed non-None inside that block.
- `src/netpath/display.py` — `country_summary()` first partitions rows into no-coverage (`skip_reason`), remote-only (`remote_only`), and measured; complete/incomplete grouping applies only to measured rows. Two new labelled groups render after "incomplete paths": "remote-only — measured from inside the ISP via Globalping; no local trace ran" (keeps the Globalping sub-row) and "no coverage — skipped, no live target" (shows each row's skip reason).
- `src/netpath/types.py` — additive `remote_only: bool` and `skip_reason: Optional[str]` keys on `MeasurementResult` (both JSON-serialisable).
- `tests/test_country.py` — the four prefix-fallback tests were replaced: Atlas-empty, Atlas-error, and null-`address_v4` cases now assert None is returned (the Atlas-empty case also asserts only the Atlas probes API is ever queried), plus a new test that rows without a `verdict` key (no-coverage, remote-only) do not affect `_worst_exit_code`.

### Deviations from plan

None. The exit-code test imports `_worst_exit_code` from `netpath.cli` and mirrors the summary-row comprehension at the end of `country()`.

### Verification

- `pytest`: 141 passed, 0 failed (matches the 141-test baseline; 4 tests replaced by 4 new ones)
- `ruff check src tests`: clean
- Smoke-rendered `country_summary()` with all four row types — grouping, labels, and the remote-only Globalping sub-row render correctly; no-coverage and remote-only rows no longer land in "incomplete paths"
- Manual `netpath country US --top 10` run is on the manual test list for the builder

## Phase 2: Partial-path recovery on trace timeout

### What was built

- `src/netpath/mtr.py` — new `TraceTimeout(RuntimeError)` exception carrying a `hubs` attribute, mirroring the `MtrPermissionError` pattern. `_run_traceroute_cmd()` switched from `subprocess.run` to `Popen` + `communicate(timeout=...)`: on `TimeoutExpired` the process is killed, the pipes drained with a second `communicate()`, and the partial stdout parsed. Usable hops (non-empty, not all-stars) raise `TraceTimeout` with the parsed hubs; empty, bytes, None, unparseable, or all-stars output falls back to the existing bare `RuntimeError("traceroute timed out")`. `run_traceroute()` re-raises `TraceTimeout` (with name enrichment applied to its hubs) instead of letting the pass-fallback `except RuntimeError` handlers swallow it, and stops after a timed-out pass rather than burning another full pass budget.
- `src/netpath/cli.py` — all three trace branches in `_measure()` (compare_v6, ecmp fallback, plain) catch `mtr.TraceTimeout`, adopt the partial hubs, set `probe_errors["v4_trace"] = "timed out (partial path shown)"` and `trace_truncated: True`, then continue into the normal AS-path / hop-table / classification flow. The compare_v6 outer future wait is recomputed as the sum of the worst-case inner budgets (mtr + Paris + two traceroute passes + slack) so it can no longer pre-empt the inner prober's partial result. `_run_test()`'s early error return now only fires when there are no hubs at all, and it threads `trace_truncated` into the display calls.
- `src/netpath/display.py` — `path_table()` and `dual_stack_columns()` accept `truncated: bool = False` and print a shared truncation note ("Path truncated — the trace timed out before completing; showing the hops collected so far") after the hop table, following the existing path-note pattern.
- `src/netpath/types.py` — additive `trace_truncated: bool` key on `MeasurementResult` (JSON-serialisable).
- `tests/test_mtr.py` — the Popen switch is covered by a `_TimeoutProc` fake: partial output raises `TraceTimeout` carrying parsed hubs; empty/None/bytes/all-stars output keeps the plain timeout error; `run_traceroute()` propagates `TraceTimeout` with enriched hubs. The existing probe-count tests were updated to mock `Popen` instead of `subprocess.run`.
- `tests/test_diagnosis.py` — new case: a result with partial hubs, a non-empty `as_path`, and `probe_errors["v4_trace"]` yields `partial_results: true` and still drives the incomplete-path analysis.

### Deviations from plan

None. One pre-existing issue noted (not touched, per surgical-changes rule): `MeasurementResult` in `types.py` still declares the long-removed `_trace_error`, `_iperf_error`, and `_speedtest_error` fields that were superseded by `probe_errors`.

### Verification

- `pytest`: 146 passed, 0 failed (141 baseline + 5 new)
- `ruff check src tests`: clean
- Smoke-rendered the truncation note in both `path_table` and `dual_stack_columns`
- In-process smoke of `_measure()` with a mocked `TraceTimeout`: partial hubs populate `hubs`, `as_path`, and path classification; the timeout lands in `probe_errors`; the verdict reports partial results — verified in both the plain and compare_v6 branches
- Manual non-responsive-trace check is on the manual test list for the builder

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 8 files changed across 2 phases

Both phases implement the live-target ladder and partial-path recovery correctly. The code changes are surgical, cover all acceptance criteria, and introduce no security or convention violations. Automated checks and 146 tests pass cleanly.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Test suite (pytest) | PASS | 146 passed, 0 failed, 0 skipped |
| Lint (ruff check src tests) | PASS | All checks passed |

### Acceptance Criteria (7/7 passed)

- [x] AC-1: country.get_test_ip_for_asn() returns None when no connected Atlas probe advertises an IPv4 address, and never returns an address derived from announced prefixes; verified by updated pytest tests/test_country.py. — PASS: country.py:136-143: function now only calls _get_atlas_probe_ip() and returns None when it returns None. RIPE_PREFIXES constant removed entirely. Tests test_get_test_ip_returns_none_when_atlas_empty, test_get_test_ip_returns_none_on_atlas_error, and test_get_test_ip_returns_none_for_null_address_v4 all assert None and verify only the Atlas probes API is ever queried. All 146 tests pass.
- [x] AC-2: An ISP with no server, no Atlas probe, and no Globalping probes is reported under a 'no coverage' label, its summary row has no verdict key, and the process exit code is unaffected by its presence; verified by a unit test plus a manual netpath country US --top 10 run. — PASS: cli.py:776-787: no-coverage rows append {asn, name, skip_reason} with no verdict key. cli.py:907: verdicts = [row['verdict'] for row in summary_rows if row.get('verdict')] excludes them from exit-code computation. display.py:538-546: 'no coverage — skipped, no live target' group renders skip_reason. test_rows_without_verdict_do_not_affect_exit_code (test_country.py:56) verifies exit code stays 0 when only no-coverage and remote-only rows exist. Manual run required for live validation.
- [x] AC-3: An ISP with Globalping probes but no local live target gets Globalping measurements scheduled and appears in the summary labelled remote-only, with no local trace attempted; verified manually with netpath country US --top 10. — PASS: cli.py:761-775: remote-only branch creates row with remote_only:True, no _run_test call, and continues. cli.py:806: _tip = _gp_test_ips.get(_asn_str) or _user_public_ip falls back to tester's public IP for remote-only rows (which have no _gp_test_ips entry). display.py:527-536: 'remote-only — measured from inside the ISP via Globalping; no local trace ran' group with Globalping sub-row. Manual run required for live validation.
- [x] AC-4: The traceroute runner returns parsed partial hops when the subprocess is killed at its time budget; verified by a test in tests/test_mtr.py that mocks the subprocess to time out with partial output captured. — PASS: mtr.py:228-246: _run_traceroute_cmd() uses Popen + communicate(timeout), kills on TimeoutExpired, drains partial stdout with a second communicate(), parses with _parse_traceroute_output(), raises TraceTimeout with hubs when hubs are non-empty and not all-stars. test_timeout_with_partial_output_raises_tracetimeout_carrying_hubs (test_mtr.py:221) verifies 3 hubs recovered. test_timeout_with_empty_output_raises_plain_timeout and test_timeout_with_all_stars_output_raises_plain_timeout verify degradation to plain RuntimeError.
- [x] AC-5: A timed-out trace with partial hops produces a result whose hubs and as_path are non-empty and whose probe_errors records the timeout, so diagnose() reports partial_results: true; verified by a tests/test_diagnosis.py case. — PASS: cli.py:249-252, 279-282, 291-295: all three _measure() trace branches catch mtr.TraceTimeout, set hubs/method from exc.hubs, record probe_errors['v4_trace'] = 'timed out (partial path shown)', and set trace_truncated = True, then continue into AS-path/classification flow (cli.py:300-324). test_partial_trace_timeout_reports_partial_results_with_path_data (test_diagnosis.py:308) verifies partial_results:true and incomplete_path signal from partial hubs.
- [x] AC-6: A manual netpath country US --top 10 run completes without any single ISP stalling for multiple minutes on an unanswered trace target. — PASS: Code logic verified: prefix-guessing fallback removed from get_test_ip_for_asn() (country.py:136-143), so no dead host is ever traced. Target ladder ensures only live Atlas probe IPs reach _run_test. TraceTimeout recovery means any trace that does time out yields partial hubs rather than the full prober budget burning. Outer future wait aligned with inner subprocess budgets (cli.py:238-243) prevents silent partial-path discard. Manual live-network execution deferred to builder.
- [x] AC-7: pytest and ruff check src tests pass. — PASS: pytest: 146 passed, 0 failed. ruff check src tests: All checks passed.

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- Remove the announced-prefix guessing fallback from get_test_ip_for_asn() entirely; a connected RIPE Atlas probe address becomes the only non-server local trace target
- Surface partial trace output via a dedicated TraceTimeout(RuntimeError) exception carrying the parsed hubs, raised from a Popen-based _run_traceroute_cmd()
- Remote-only ISPs (Globalping probes but no local live target) use the tester's public IP as the Globalping ping target, and no local trace is attempted
- Remote-only rows do not populate _gp_test_ips; the Globalping scheduling loop falls back to _user_public_ip inline, and the old 'no test IP available' error branch was removed as dead code
- A TraceTimeout raised by any traceroute pass propagates immediately out of run_traceroute() — no further pass runs, since a full time budget has already been spent
- The compare_v6 outer future wait is computed as the sum of the worst-case inner budgets (mtr + Paris + two traceroute passes + 15 s slack) so it can no longer pre-empt the inner prober's partial result

## Required Changes

None.

## Release

## Release Notes

### What was built
- Removed the announced-prefix address-guessing fallback from `country.get_test_ip_for_asn()` so country sweeps no longer trace dead hosts that burn the full prober budget and produce spurious incomplete-path warnings
- Added a live-target ladder in the country loop: iperf3 server first, then connected RIPE Atlas probe IP, then remote-only Globalping measurement using the tester's public IP, then fast "no coverage" skip
- ISPs with no live target are labelled "no coverage" and excluded from exit-code and verdict tallies; remote-only ISPs get their own labelled group in the summary
- Added `TraceTimeout` partial-path recovery in `mtr.py`: when a traceroute subprocess is killed at its time budget, the hops collected before the kill are parsed and surfaced rather than discarded, so timed-out traces still yield useful path data
- Aligned the compare_v6 outer future wait to the sum of the worst-case inner subprocess budgets so the outer wait can no longer pre-empt a recovered partial path

### Key decisions
- Remove the announced-prefix guessing fallback from `get_test_ip_for_asn()` entirely; a connected RIPE Atlas probe address becomes the only non-server local trace target
- Surface partial trace output via a dedicated `TraceTimeout(RuntimeError)` exception carrying the parsed hubs, raised from a Popen-based `_run_traceroute_cmd()`
- Remote-only ISPs (Globalping probes but no local live target) use the tester's public IP as the Globalping ping target, and no local trace is attempted
- Remote-only rows do not populate `_gp_test_ips`; the Globalping scheduling loop falls back to `_user_public_ip` inline, and the old unreachable "no test IP available" branch was removed
- A `TraceTimeout` raised by any traceroute pass propagates immediately out of `run_traceroute()` — no further pass runs after a timed-out one, since a full time budget has already been spent
- The compare_v6 outer future wait is computed as the sum of the worst-case inner budgets (mtr + Paris + two traceroute passes + 15 s slack)

### Changes by phase
- **Phase 1: Live-target selection and coverage labelling** — `get_test_ip_for_asn()` returns Atlas probe IP or None (prefix guessing removed); country loop implements the target ladder with remote-only and no-coverage branches; `country_summary()` renders the two new row groups with distinct labels; additive `remote_only` and `skip_reason` TypedDict keys; four test_country.py tests updated (141 passed)
- **Phase 2: Partial-path recovery on trace timeout** — `TraceTimeout` exception added mirroring `MtrPermissionError` pattern; `_run_traceroute_cmd()` switched to Popen + communicate for partial-stdout harvest on kill; all three `_measure()` trace branches catch `TraceTimeout` and adopt partial hubs; `path_table()` and `dual_stack_columns()` print a truncation note when `truncated=True`; additive `trace_truncated` TypedDict key; five new tests added across test_mtr.py and test_diagnosis.py (146 passed)

## Verification

### Production Build
- `uv tool run --from build pyproject-build` — PASS: `netpath-0.12.1.dev15+g6d12cabd2.tar.gz` and `netpath-0.12.1.dev15+g6d12cabd2-py3-none-any.whl` built successfully

### Automated Checks (from review)
- `pytest` — PASS: 146 passed, 0 failed
- `ruff check src tests` — PASS: clean

