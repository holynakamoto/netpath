---
defract:
  id: task-systems-design-review-of-netpath-01kwesg18dsj
  type: improvement
  status: active
  stage: architecture
  phase: 0
  total_phases: 3
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

## Story Brief

# Systems-design review of netpath

# Systems-design review of netpath

## What We're Building

A structural overhaul of netpath addressing six architectural problems identified in a design review: measurement logic tangled into the CLI layer, a diagnostic engine that reports only the first problem found instead of all of them, silently swallowed probe failures that make a "Healthy" verdict untrustworthy, fragile untyped data contracts, hand-rolled concurrency that leaks processes on timeout, and missing retry/caching for external service calls. The goal is a codebase where each concern lives in its own layer, failures are visible, and both probe modes (ASN and country) share the same full feature set.

## Expected Outcome

- When a path has multiple problems simultaneously — bufferbloat, mid-path loss, high jitter — all of them appear in the report instead of only the first one detected
- A "partial results" indicator appears when one or more probes fail silently, so a clean "Healthy" verdict is trustworthy rather than ambiguous
- Country-mode sweeps get the same full probe set as ASN mode — ECMP detection, IPv6 comparison, PMTU, and TCP/TLS latency no longer silently absent in country scans
- Independent probes run concurrently instead of sequentially, reducing total wall-clock time per target
- Transient failures in external lookups (BGP origin data, iperf3 server lists) are retried automatically and do not silently drop data

## Phase Outcomes

- **Phase 1: Complete diagnostic reporting and typed contracts** — Users see every network problem present in a path rather than only the first one caught. Data passed between modules is explicitly typed, making the codebase verifiable and reducing the chance of silent data-shape mismatches.
- **Phase 2: Probe failure visibility and external call reliability** — A failed probe produces a visible "Partial results" indicator instead of silently inflating the "Healthy" count. Transient network errors on external lookups trigger automatic retries, so a momentary disruption no longer causes data to disappear from the report without warning.
- **Phase 3: Structured concurrency and country-mode parity** — Independent probes run in parallel, cutting per-target scan time. Country-mode sweeps gain the same probe depth as single-ASN mode. Probe processes clean up correctly when a timeout occurs, removing the current resource leak.

## Out of Scope

- New probe types or network metrics not already implemented in the codebase
- Changes to the command-line interface, flag names, or output format visible to users
- On-disk caching, persistent configuration, or anything that requires writing state between runs

## Scope Summary

**Size:** 16 requirements, 12 acceptance criteria, 3 implementation phases
**Key decisions:**
- Typed contracts via TypedDict (not dataclasses) to preserve dict compatibility with existing JSON output callers
- Diagnostic engine accumulates all matched signals before determining verdict, replacing early-return pattern
- Structured concurrency via `concurrent.futures.ThreadPoolExecutor` rather than asyncio, to preserve subprocess compatibility
**Biggest risk:** Extracting state out of `_measure()` while preserving the `_`-prefixed internal key contract and worst-severity exit-code rollup that both probe modes rely on

## Context

netpath probes network paths to target ASNs using mtr/traceroute, iperf3, PMTU probing, and TCP/TLS latency measurements. The codebase has grown organically: `_measure()` in `cli.py` is 167+ lines mixing subprocess orchestration, threading setup, and data collection. `diagnosis.py` uses early-return logic across 9 checks, so only the first matched condition surfaces in the verdict. IPv6 trace exceptions are silently swallowed with a bare `except Exception: return None` at line 217. All inter-module data flows as plain untyped dicts with 30+ mixed public and `_`-prefixed internal keys. Background daemon threads for ping and dual-stack traces have no structured teardown on timeout. No outbound HTTP call has retry logic. Country mode's per-ASN sweep omits the ECMP multi-pass, dual-stack, PMTU, and TCP/TLS latency probes that ASN mode enables.

## Requirements

### Diagnostic engine

- R1: `diagnose()` evaluates all nine diagnostic checks against the result dict and accumulates every matched condition into a `signals` list before returning, replacing the current early-return pattern. The function short-circuits to "Healthy" only when no conditions match.
- R2: The top-level `verdict` severity in the return value is derived from the worst severity across all entries in `signals` (critical > warning > ok). When no signals match, severity is "ok" and verdict is "Healthy".
- R3: Each entry in the `signals` list is a dict with three keys: `condition` (str, machine-readable label), `severity` (str: "ok" / "warning" / "critical"), and `detail` (str, human-readable description matching existing verdict strings).

### Probe failure tracking

- R4: Each probe in `_measure()` — v4 trace, v6 trace, PMTU, TCP/TLS latency, iperf3, speedtest — populates a `probe_errors: dict[str, str]` entry on failure, keyed by probe name with a short reason string. The current pattern of storing errors in `_`-prefixed keys (`_trace_error`, `_iperf_error`, `_speedtest_error`) is replaced.
- R5: `diagnose()` reads `probe_errors` from the result dict and sets a `partial_results: bool` field in its return value to `True` when the dict is non-empty.
- R6: `display.verdict_panel()` renders a visible annotation — "(partial results: {comma-separated probe list})" — appended to the verdict text when `partial_results` is `True`, visually distinguishing a "Healthy (partial)" result from a fully verified "Healthy".

### Typed data contracts

- R7: A `Hub` TypedDict is defined in a new `src/netpath/types.py` module with fields matching existing hub dict keys: `count`, `host`, `ASN`, `Loss%`, `Avg`, `Best`, `Wrst`, `StDev`, `p50`, `p95`, `p99`, plus an optional `type` field for IXP classification.
- R8: A `MeasurementResult` TypedDict is defined in `src/netpath/types.py` capturing all public output keys returned by `_measure()`. `total=False` is used so callers that access optional probe fields via `.get()` continue working without modification.
- R9: `cli.py`, `mtr.py`, and `display.py` import and annotate return values against the TypedDicts in `types.py`. No changes to dict key-access patterns in callers are required.

### Structured concurrency

- R10: The dual-stack trace pair (IPv4 and IPv6) is submitted to a `concurrent.futures.ThreadPoolExecutor`; the executor context manager ensures threads are joined and futures collected when `_measure()` exits, replacing the current bare daemon thread pair joined with a fixed timeout.
- R11: The background ping thread launched during iperf3 throughput measurement is submitted to the same executor as a `Future`. On iperf3 completion or failure, the ping future is cancelled within a bounded wait, removing the daemon thread that currently may remain alive after a timeout.
- R12: Independent probes with no data dependency on each other — PMTU, TCP/TLS latency, and RUM fetch — are submitted concurrently to the executor in `_measure()` rather than called sequentially.

### Retry and external call reliability

- R13: A local retry helper `_with_retry(fn, attempts=3, base_delay=1.0)` is introduced in a new `src/netpath/utils.py` module. It retries the callable up to `attempts` times on `requests.ConnectionError`, `requests.Timeout`, and HTTP 5xx responses, with delays of 1 s, 2 s, 4 s (exponential backoff). On final failure it re-raises the last exception.
- R14: `servers._fetch_and_resolve()` and `rum.fetch_asn_quality()` wrap their `requests.get()` calls with `_with_retry`.
- R15: The Cymru bulk ASN lookup in `mtr.py` and `display.py` retries once on `socket.error` before returning an empty string for unresolvable hosts. Failed retries emit a single `warnings.warn()` line, not a full traceback.

### Country-mode parity

- R16: The per-ASN measurement loop in `country()` passes `passes=2` for ECMP detection, enables dual-stack comparison, and enables PMTU and TCP/TLS latency probes, matching the default probe parameters used in `asn()` mode. The `skip_throughput=True` flag remains in place; only throughput measurement is excluded from country sweeps.

## Acceptance Criteria

- [ ] `diagnosis.diagnose()` returns a dict whose `signals` key is a non-empty list when two or more conditions are simultaneously present; verifiable with a crafted result dict in `tests/test_diagnosis.py`
- [ ] The top-level `severity` in the `diagnose()` return equals the worst severity across all entries in `signals`
- [ ] `_measure()` returns a dict containing a `probe_errors` key; it is populated when any probe fails and is an empty dict when all probes succeed
- [ ] Running `netpath asn` against a target where iperf3 is unavailable shows "(partial results)" in the terminal verdict panel
- [ ] `src/netpath/types.py` exists and exports `Hub` and `MeasurementResult` TypedDicts; `cli.py` and `mtr.py` import from it
- [ ] `_measure()` uses `concurrent.futures.ThreadPoolExecutor` for the dual-stack trace pair; no bare `threading.Thread(daemon=True)` remains for v4/v6
- [ ] PMTU probe and RUM fetch are submitted concurrently to the thread pool executor, not called sequentially
- [ ] `servers._fetch_and_resolve()` retries the HTTP GET up to 3 times on `ConnectionError` or `Timeout`
- [ ] `rum.fetch_asn_quality()` retries the HTTP GET up to 3 times on `ConnectionError` or `Timeout`
- [ ] Running `netpath country US --top 3` produces per-ASN output that includes ECMP path count, IPv6 delta, and PMTU results
- [ ] `ruff check .` reports zero errors after all changes
- [ ] `pytest` passes with no regressions after all changes

## Implementation Phases

### Phase 1: Complete diagnostic reporting and typed contracts
**Scope:** Refactor `diagnosis.py` to accumulate all matched signals rather than returning on the first match, and add `partial_results` to the diagnosis return keyed from `probe_errors`. Define `Hub` and `MeasurementResult` TypedDicts in a new `types.py` module and annotate existing callers without breaking dict-access patterns.

### Phase 2: Probe failure tracking and external call reliability
**Scope:** Replace scattered `_`-prefixed error keys in `_measure()` with a unified `probe_errors` dict. Introduce the `_with_retry` helper in `utils.py` and wrap all outbound HTTP requests in `servers.py` and `rum.py`. Add single-retry to Cymru bulk lookups. Add the "partial results" annotation to `display.verdict_panel()`.

### Phase 3: Structured concurrency and country-mode parity
**Scope:** Replace daemon thread pairs for dual-stack traces and the ping background thread with `concurrent.futures.ThreadPoolExecutor` managed futures. Submit PMTU, TCP/TLS latency, and RUM fetch concurrently. Update the country-mode measurement loop to pass the same probe parameters as ASN mode.

## Edge Cases

- All probes fail: `probe_errors` has 6+ entries, `partial_results=True`, `signals=[]` — verdict is "Healthy" but the partial-results annotation must be prominent enough to signal maximum uncertainty
- Retry exhaustion on server list fetch: `_fetch_and_resolve()` re-raises on final failure; the caller in `cli.py` handles it via the existing no-servers-found path, not a new code path
- Country mode target with no servers: trace, PMTU, and latency still run; only iperf3 is skipped, matching ASN mode behavior for the same condition
- Executor timeout: futures that exceed wall-clock budget are cancelled; the probe name is added to `probe_errors` with reason `"timeout"` so the partial-results path is triggered
- `diagnose()` exception handler: the existing bare `except Exception` safety net must remain, but the `probe_errors` read and `partial_results` flag must execute inside the try block so a failing probe still contributes its signal before any exception can propagate

## Technical Notes

The core invariant is that `_measure()`'s return value remains JSON-serializable and backward-compatible for `--json` output mode. `MeasurementResult` uses `total=False` so optional probe fields (PMTU, TCP/TLS, IPv6 results) are optional — existing `.get("key")` call sites require no modification.

`concurrent.futures.ThreadPoolExecutor` is preferred over asyncio because `subprocess.Popen` and socket I/O (Cymru, PMTU probing) are blocking. Wrapping them with `asyncio.run_in_executor()` would add complexity without improving semantics. One executor instance is created at the start of `_measure()`, used across all concurrent submissions, and torn down with the context manager when `_measure()` returns.

The retry helper in `utils.py` accepts only `Callable[[], T]` with no keyword arguments, so callers bind arguments via `functools.partial` or lambdas. This keeps the helper testable without mocking `requests` internals.

The country-mode parity change (R16) is the highest end-user impact requirement but lowest implementation risk: it is a parameter change to existing function calls rather than a structural change, and should be implemented last to confirm no regressions from the earlier phases.

### Dependencies

Phase 2 depends on the `probe_errors` key structure and `MeasurementResult` TypedDict established in Phase 1. Phase 3 has no hard dependency on Phase 2 output but must preserve the `probe_errors` dict contract when futures time out.

## Architecture

### Architecture Summary

The six architectural problems in netpath are fixed in three sequential passes. First, the diagnostic engine is taught to collect every network problem it finds instead of stopping at the first one — a path with bufferbloat, packet loss, and high jitter will now report all three, and the worst one sets the overall verdict. TypedDict contracts are added to make the data shapes visible and verifiable. Second, probe failures become first-class data: every probe that fails records its name and reason in a shared dictionary, the diagnostic engine reads that dictionary and sets a 'partial results' flag, and the terminal output shows a visible annotation so a 'Healthy (partial)' result is clearly distinguished from a fully-verified clean pass. External HTTP calls (server list, Cloudflare RUM) get automatic retry with exponential backoff. Third, the background threads that have no structured cleanup are replaced by a single managed thread pool used for all concurrent work: dual-stack traces, PMTU probing, TCP/TLS latency, and RUM fetching all run in parallel through the same executor, and country-mode sweeps gain the same full probe set that single-ASN mode already provides.

### Implementation Phases

### Phase 1: Complete diagnostic reporting and typed contracts

**Verification:**
- [ ] pytest tests/test_diagnosis.py passes with zero failures after signal format change
- [ ] python -c "from netpath.types import Hub, MeasurementResult" exits 0
- [ ] python -c "from netpath.diagnosis import diagnose; r = diagnose({'bufferbloat_ms': 50, 'jitter_ms': 15.0, 'hubs': []}); assert len(r['signals']) >= 2" exits 0
- [ ] python -c "from netpath.diagnosis import diagnose; r = diagnose({'probe_errors': {'iperf3': 'timed out'}}); assert r['partial_results'] is True" exits 0
- [ ] ruff check . reports zero errors

**Estimated effort:** Medium

### Phase 2: Probe failure tracking and external call reliability

**Verification:**
- [ ] pytest tests/test_utils.py passes
- [ ] grep '_trace_error\|_iperf_error\|_speedtest_error' src/netpath/cli.py returns zero matches
- [ ] python -c "from netpath.utils import _with_retry" exits 0
- [ ] ruff check . reports zero errors
- [ ] pytest passes with no regressions from Phase 1

**Estimated effort:** Medium

### Phase 3: Structured concurrency and country-mode parity

**Verification:**
- [ ] grep -n 'threading.Thread' src/netpath/cli.py returns zero results
- [ ] python -c "import concurrent.futures; from netpath.cli import _measure" exits 0
- [ ] pytest passes with no regressions
- [ ] ruff check . reports zero errors
- [ ] manual test: netpath country US --top 2 shows ECMP path count and PMTU in per-ASN output

**Estimated effort:** Medium

