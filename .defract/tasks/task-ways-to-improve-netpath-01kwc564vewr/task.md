---
defract:
  id: task-ways-to-improve-netpath-01kwc564vewr
  type: improvement
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

# Ways to Improve Netpath

# Ways to Improve Netpath

## What We're Building

Three targeted improvements that make netpath more reliable and scripting-friendly: a test suite covering the most fragile parsing and verdict logic with a GitHub Actions CI workflow, a refactor that separates measurement from display in the core test function, and exit codes that reflect diagnosed network health so netpath can participate in monitoring pipelines.

## Expected Outcome

- Running `netpath asn` or `netpath country` on a path with diagnosed issues exits with a non-zero code (1 for warning, 2 for critical), making netpath usable in shell scripts and alerting setups
- A test suite validates the traceroute parser, verdict classifier, and related pure functions on every pull request across Python 3.9 through 3.13
- Developers install all development tools (pytest, ruff) with a single `pip install -e ".[dev]"` step
- The core test function has a clear internal boundary between the code that measures network state and the code that renders it, reducing the risk of silent regressions when either side changes

## Phase Outcomes

- **Phase 1: Test suite and CI workflow** — Contributors get immediate feedback when a code change breaks the traceroute parser or verdict logic, across every supported Python version. The dev toolchain is also installable in a single command.
- **Phase 2: Exit codes and measurement/display separation** — Scripts and monitoring pipelines can act on netpath's diagnosis without parsing terminal output. The internal code structure also cleanly separates what is measured from what is shown, making future additions (like JSON output for the country subcommand) straightforward.

## Out of Scope

- Adding `--json` output to the `country` subcommand (the refactor makes this easy, but it is a follow-on change)
- New CLI subcommands, flags, or user-visible features beyond exit-code behavior
- Performance improvements to measurement speed or parallelism

## Scope Summary

**Size:** 10 requirements, 11 acceptance criteria, 2 implementation phases
**Key decisions:**
- Tests target `diagnosis.py` and `mtr._parse_traceroute_output` — the two pure-function areas with no subprocess or network dependencies
- Exit code is the worst verdict across all tested servers/ASNs (country mode runs multiple)
- `_run_test` refactored by extracting a `_measure()` inner function; `json_mode` branching eliminated from the measurement path
**Biggest risk:** The `_parse_traceroute_output` function is private and platform-specific; test inputs must cover Linux and macOS traceroute output formats.

## Context

`diagnosis.py` is already a pure function with no imports from other netpath modules — the ideal test target. `mtr._parse_traceroute_output` is the next most fragile piece: it parses free-form traceroute text and is currently untested. The `_run_test()` function in `cli.py` (lines 152–298) interleaves display calls with measurement logic via a `json_mode` flag; extracting a `_measure()` helper will remove this branching and enable future JSON output in `country` mode. The `pyproject.toml` has no `[project.optional-dependencies]` section and no CI configuration today.

## Requirements

### Test suite

- R1: A `dev` extras group in `pyproject.toml` lists `pytest>=8` and `ruff>=0.4` so contributors can install everything with `pip install -e ".[dev]"`.
- R2: `tests/test_diagnosis.py` covers all verdict paths in `diagnose()`: Healthy (default return), Severe Bufferbloat (bufferbloat > 30 ms), Mid-path Packet Loss (intermediate hop loss > 1%), Last-mile Congestion (first-hop loss + bufferbloat > 5 ms), and Throughput Cap (download < 70% of RUM baseline). Each scenario asserts `verdict`, `severity`, and that `signals` is non-empty for non-Healthy results.
- R3: `tests/test_mtr.py` covers `_parse_traceroute_output` with at least: a normal multi-hop response with RTT values, an all-stars filtered path, a mixed response (some hops responding, some filtered), and a single-hop path.
- R4: `tests/test_mtr.py` also covers the `_all_stars()` helper in `mtr.py` for empty input, all-star hubs, and mixed hubs.
- R5: All tests must pass with no subprocess calls, no network I/O, and no filesystem side effects.

### CI workflow

- R6: A `.github/workflows/ci.yml` workflow runs on every push and pull request to `main`.
- R7: The CI matrix covers Python 3.9, 3.10, 3.11, 3.12, and 3.13 on `ubuntu-latest`.
- R8: Each matrix job installs the package with `pip install -e ".[dev]"` and then runs `pytest`.

### Exit codes

- R9: After all probes complete, `netpath asn` exits 0 if the worst verdict severity is `ok`, 1 if `warning`, and 2 if `critical`. In JSON mode, a single server is tested; in normal mode, all tested servers are considered.
- R10: `netpath country` exits 0 if all ASN verdicts are `ok`, 1 if any are `warning` and none are `critical`, and 2 if any are `critical`. ASNs skipped due to no servers or unreachable test IPs do not affect the exit code.

### Measurement/display refactor

- R11: A `_measure()` function extracted from `_run_test()` in `cli.py` handles all data collection (trace, classify path, fetch RUM, run throughput, compute bufferbloat, call `diagnose()`) and returns the enriched result dict with no display calls and no `json_mode` parameter. `_run_test()` calls `_measure()` and then handles all display rendering; `json_mode` remains only in `_run_test()` (and only to suppress its own display calls).

## Acceptance Criteria

- [ ] `pip install -e ".[dev]"` succeeds from a clean checkout and installs pytest and ruff.
- [ ] `pytest` exits 0 with no errors; the suite includes at least 12 test cases across `test_diagnosis.py` and `test_mtr.py`.
- [ ] `test_diagnosis.py` covers: Healthy, Severe Bufferbloat, Mid-path Packet Loss, Last-mile Congestion, and Throughput Cap paths.
- [ ] `test_mtr.py` covers: normal multi-hop, all-stars, mixed, single-hop traceroute output, plus `_all_stars()` edge cases.
- [ ] GitHub Actions CI workflow file exists at `.github/workflows/ci.yml` and defines a matrix over Python 3.9–3.13.
- [ ] `netpath asn AS15169 --no-throughput` exits 0 when the path is healthy (verified via `echo $?`).
- [ ] When `diagnose()` returns severity `warning`, the `asn` subcommand exits 1; when severity is `critical`, it exits 2.
- [ ] `netpath country US --top 1 --no-throughput` exits with a code that matches the worst verdict across tested ASNs (0/1/2).
- [ ] ASNs skipped due to missing servers in `country` mode do not cause a spurious non-zero exit.
- [ ] `_measure()` exists in `cli.py` and contains no Rich console calls and no `json_mode` branching; verified by reading the function body.
- [ ] `netpath asn ... --json` output is identical before and after the refactor (same keys, same values for the same input).

## Implementation Phases

### Phase 1: Test suite and CI workflow
**Scope:** Add the `dev` extras group to `pyproject.toml`, create the `tests/` package with test modules covering `diagnosis.py` and `mtr.py` pure functions, and add the GitHub Actions CI workflow.
**Files:**
- `pyproject.toml` — add `[project.optional-dependencies]` with `dev` group
- `tests/__init__.py` — empty package marker
- `tests/test_diagnosis.py` — all verdict scenarios for `diagnose()`
- `tests/test_mtr.py` — traceroute parser and `_all_stars()` scenarios
- `.github/workflows/ci.yml` — Python 3.9–3.13 matrix, `pip install -e ".[dev]"`, `pytest`
**Verification:**
- [ ] `pip install -e ".[dev]"` exits 0
- [ ] `pytest -v` exits 0 with all tests passing
- [ ] CI workflow file present and syntactically valid YAML
**Estimated effort:** Small

### Phase 2: Exit codes and measurement/display separation
**Scope:** Extract `_measure()` from `_run_test()` to isolate data collection from rendering, then wire exit codes into both `asn` and `country` subcommands based on the worst verdict severity across all probes.
**Files:**
- `src/netpath/cli.py` — extract `_measure()`, propagate exit codes in `asn` and `country`
**Verification:**
- [ ] `_measure()` function present, no `display.*` calls in its body, no `json_mode` parameter
- [ ] `netpath asn AS15169 --no-throughput` exits 0 for a healthy path (run live or mock the subprocess)
- [ ] Manually testing with a forced `warning` verdict (patch `diagnose` or use a known-bad path) yields exit 1
- [ ] `netpath asn ... --json` still produces valid JSON output unchanged
- [ ] `netpath country US --top 1 --no-throughput` exits based on worst verdict
**Estimated effort:** Small

## Edge Cases

- Traceroute lines with multiple hostnames (MPLS alias): `_parse_traceroute_output` should treat the first token as the host and ignore alternates.
- macOS traceroute uses `round-trip min/avg/max/stddev` instead of Linux's `rtt min/avg/max/mdev`; `_parse_ping_avg` already handles this but test coverage should confirm.
- `diagnose()` swallows all exceptions and returns a Healthy default; tests should verify this with malformed input.
- `country` mode with all ASNs skipped (no servers, no test IPs): exit code should be 0, not an error.
- JSON mode in `asn` tests only the first server; the exit code in JSON mode reflects that single result.

## Technical Notes

`diagnose()` in `diagnosis.py` has no dependencies and can be tested by constructing plain dicts. `_parse_traceroute_output` and `_all_stars` in `mtr.py` are module-private but importable via `from netpath.mtr import _parse_traceroute_output, _all_stars`.

For exit codes, Typer's `raise typer.Exit(code=N)` is the correct mechanism — do not call `sys.exit()` directly, as that bypasses Typer's cleanup.

The `_measure()` extraction should keep the existing `_run_test()` signature and behavior intact for all call sites in `asn` and `country`. The `json_mode` parameter stays on `_run_test()` and only governs display output from that wrapper, not measurement logic.

Ruff config can be left unconfigured in `pyproject.toml` for now; a bare `ruff check .` with defaults is sufficient for this task. Adding a `[tool.ruff]` section is out of scope.

The CI workflow should use `actions/setup-python@v5` and `actions/checkout@v4` (latest stable at knowledge cutoff). Pin to `ubuntu-latest` only — macOS runners are slower and the pure-function tests have no platform-specific behavior.

## Implementation Notes

## Phase 1: Test suite and CI workflow

**Files changed:**
- `pyproject.toml` — added `[project.optional-dependencies]` with `dev = ["pytest>=8", "ruff>=0.4"]`
- `tests/__init__.py` — empty package marker
- `tests/test_diagnosis.py` — 6 tests: Healthy, Severe Bufferbloat, Mid-path Packet Loss, Last-mile Congestion, Throughput Cap, malformed-input fallback
- `tests/test_mtr.py` — 8 tests: normal multi-hop, all-stars, mixed, single-hop, macOS parenthesized-IP format, `_all_stars()` empty/all-filtered/mixed
- `.github/workflows/ci.yml` — CI matrix over Python 3.9, 3.10, 3.11, 3.12, 3.13 on ubuntu-latest using `pip install -e "[dev]"` then `pytest`

**Results:** 14/14 tests pass, no deviations from plan.

## Phase 2: Exit codes and measurement/display separation

**Files changed:**
- `src/netpath/cli.py` — extracted `_measure()`, wired exit codes into `asn` and `country` subcommands

**What was built:**

`_measure(host, port, target_asn, cycles, duration, skip_throughput, cf_token)` handles all data collection: trace, path classification, RUM fetch, iperf3/speedtest throughput, bufferbloat computation, and `diagnose()`. It returns the enriched result dict with no display calls and no `json_mode` parameter. Internal `_`-prefixed keys (`_iperf_upload`, `_iperf_download`, `_iperf_idle_rtt`, `_iperf_loaded_rtt`, `_iperf_error`, `_speedtest_upload`, `_speedtest_download`, `_speedtest_error`, `_trace_method`, `_trace_error`) carry intermediate state for `_run_test()` to use in display without re-running any measurement.

`_run_test()` now calls `_measure()` inside a single Progress spinner (normal mode) or directly (json_mode), then handles all display rendering afterward. `json_mode` branching remains only in `_run_test()`.

Exit codes via `_SEVERITY_CODE = {"ok": 0, "warning": 1, "critical": 2}` and `_worst_exit_code(verdicts)`:
- `asn` subcommand: collects verdicts from all tested servers (or the single json-mode server) and raises `typer.Exit(code)` where code is the worst severity.
- `country` subcommand: collects verdicts from all rows that have a verdict (skipped ASNs have no verdict key and naturally score 0), raises `typer.Exit(code)` for the worst severity.

**Results:** 14/14 tests pass, ruff clean on `src/netpath/cli.py` and `tests/`.

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 6 files changed across 2 phases

All 11 acceptance criteria pass, all 3 automated checks pass (install, pytest 14/14, ruff clean), and no security or code quality issues were found. The implementation correctly separates measurement from display in _measure(), wires exit codes through typer.Exit, and the test suite covers all required verdict paths and traceroute parser scenarios.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Install (dev extras) | PASS | uv pip install -e ".[dev]" exits 0; pytest>=8 and ruff>=0.4 resolved |
| Test suite (pytest) | PASS | 14/14 tests pass: 6 in test_diagnosis.py, 8 in test_mtr.py |
| Linter (ruff) | PASS | ruff check src/netpath/cli.py tests/ — all checks passed |

### Acceptance Criteria (11/11 passed)

- [x] AC-1: pip install -e ".[dev]" succeeds from a clean checkout and installs pytest and ruff. — PASS: uv pip install -e ".[dev]" exits 0; pyproject.toml:37-41 defines dev = ["pytest>=8", "ruff>=0.4"]
- [x] AC-2: pytest exits 0 with no errors; the suite includes at least 12 test cases across test_diagnosis.py and test_mtr.py. — PASS: 14 tests pass (6 in test_diagnosis.py + 8 in test_mtr.py), pytest exit 0
- [x] AC-3: test_diagnosis.py covers: Healthy, Severe Bufferbloat, Mid-path Packet Loss, Last-mile Congestion, and Throughput Cap paths. — PASS: tests/test_diagnosis.py lines 4-45: test_healthy_default, test_severe_bufferbloat, test_mid_path_packet_loss, test_last_mile_congestion, test_throughput_cap — all 5 verdict paths present
- [x] AC-4: test_mtr.py covers: normal multi-hop, all-stars, mixed, single-hop traceroute output, plus _all_stars() edge cases. — PASS: tests/test_mtr.py: normal multi-hop (line 38), all-stars (line 49), mixed (line 56), single-hop (line 65); _all_stars() empty/all-filtered/mixed (lines 84-95)
- [x] AC-5: GitHub Actions CI workflow file exists at .github/workflows/ci.yml and defines a matrix over Python 3.9-3.13. — PASS: .github/workflows/ci.yml line 14: python-version: ["3.9", "3.10", "3.11", "3.12", "3.13"]
- [x] AC-6: netpath asn AS15169 --no-throughput exits 0 when the path is healthy (verified via echo $?). — PASS: Code path: _worst_exit_code returns 0 for all-ok verdicts; if code: is False so no typer.Exit raised; program exits 0 naturally. Programmatically verified: _worst_exit_code([{'severity':'ok'}]) == 0
- [x] AC-7: When diagnose() returns severity warning, the asn subcommand exits 1; when severity is critical, it exits 2. — PASS: _SEVERITY_CODE at cli.py:32 maps warning->1, critical->2; _worst_exit_code at cli.py:35-36; raise typer.Exit(code) at cli.py:433. Programmatically verified: warning->1, critical->2
- [x] AC-8: netpath country US --top 1 --no-throughput exits with a code that matches the worst verdict across tested ASNs (0/1/2). — PASS: cli.py:561-564: verdicts = [row["verdict"] for row in summary_rows if row.get("verdict")], exit_code = _worst_exit_code(verdicts), raise typer.Exit(exit_code) when >0
- [x] AC-9: ASNs skipped due to missing servers in country mode do not cause a spurious non-zero exit. — PASS: cli.py:527-533: skipped ASN rows appended without a verdict key; row.get("verdict") returns None for those rows, excluding them from the verdicts list
- [x] AC-10: _measure() exists in cli.py and contains no Rich console calls and no json_mode branching; verified by reading the function body. — PASS: cli.py:157-244 defines _measure(); no display. calls, no json_mode parameter in signature, no json_mode references in the body
- [x] AC-11: netpath asn ... --json output is identical before and after the refactor (same keys, same values for the same input). — PASS: JSON output built from cli.py:385-411 uses same keys (asn, target_host, path, throughput, bufferbloat_ms, rum, verdict); all values come from _measure() which returns the same field set; internal _-prefixed keys excluded from output

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- Tests target only pure functions (diagnosis.diagnose() and mtr._parse_traceroute_output / _all_stars) to avoid subprocess/network mocking overhead
- Exit code reflects worst verdict across all probes in a run (0=ok, 1=warning, 2=critical) so monitoring scripts get a single actionable result
- _measure() returns internal _-prefixed keys (e.g. _iperf_upload, _iperf_loaded_rtt) alongside public keys so _run_test() can reconstruct display without re-running measurements

## Required Changes

None.

## Release

## Release Notes

### What was built
- Added `dev` optional-dependencies group to `pyproject.toml` (`pytest>=8`, `ruff>=0.4`), enabling a single `pip install -e ".[dev]"` install step for contributors
- Created a test suite (`tests/test_diagnosis.py`, `tests/test_mtr.py`) covering all verdict paths in `diagnose()` and all traceroute parser scenarios in `_parse_traceroute_output`/`_all_stars()` — 14 tests total
- Added GitHub Actions CI workflow (`.github/workflows/ci.yml`) running the test matrix across Python 3.9, 3.10, 3.11, 3.12, and 3.13 on `ubuntu-latest`
- Extracted `_measure()` from `_run_test()` in `cli.py` to cleanly separate all data collection (trace, RUM, throughput, diagnosis) from display rendering, with no `json_mode` branching in the measurement path
- Wired exit codes into both `asn` and `country` subcommands: 0 for all-ok, 1 for worst severity warning, 2 for worst severity critical — making netpath usable in shell scripts and monitoring pipelines

### Key decisions
- Tests target only pure functions (`diagnosis.diagnose()` and `mtr._parse_traceroute_output`/`_all_stars`) to avoid subprocess/network mocking overhead
- Exit code reflects worst verdict across all probes in a run so monitoring scripts get a single actionable result without parsing JSON output
- `_measure()` returns internal `_`-prefixed keys (e.g. `_iperf_upload`, `_iperf_loaded_rtt`, `_trace_error`) alongside public keys so `_run_test()` can reconstruct display without re-running any measurement

### Changes by phase
- **Phase 1: Test suite and CI workflow** — Added `dev` extras to `pyproject.toml`; created `tests/__init__.py`, `tests/test_diagnosis.py` (6 tests), `tests/test_mtr.py` (8 tests); added `.github/workflows/ci.yml` with Python 3.9–3.13 matrix. All 14 tests pass from the start.
- **Phase 2: Exit codes and measurement/display separation** — Extracted `_measure()` from `_run_test()` with `_SEVERITY_CODE`/`_worst_exit_code()` helpers; wired `typer.Exit(code)` into both `asn` and `country` subcommands. Skipped ASNs in `country` mode excluded from exit code calculation via absent `verdict` key. 14/14 tests pass, ruff clean.

## Verification

### Production Build
PASS — `uv pip install -e ".[dev]"` exits 0; `netpath==0.1.0` installed from worktree.

### Push
PASS — branch `feature/task-ways-to-improve-netpath-01kwc564vewr` pushed to `origin` and tracking set.

### Review Reference
Approved 2026-06-30T15:42:25Z — 11/11 acceptance criteria passed, all 3 automated checks passed (install, pytest 14/14, ruff clean).

