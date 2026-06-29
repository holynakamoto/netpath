---
defract:
  id: task-netpath-as-a-one-shot-diagnostic-path-01kwaqc10tym
  type: improvement
  status: active
  stage: architecture
  phase: 0
  total_phases: 4
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

## Story Brief

# netpath as a One-Shot Diagnostic Path CLI

# netpath as a One-Shot Diagnostic Path CLI

## What We're Building

We are transforming netpath from a metrics-display tool into a genuine "what's wrong right now" diagnostic instrument. The upgraded tool will measure the full picture of a network path — throughput, latency under load, jitter, and hop-by-hop loss — and then synthesize those measurements into a plain-language verdict that identifies where in the path the problem is and what kind of failure it is.

## Expected Outcome

- Running `netpath asn <ASN>` produces a structured diagnosis: a clear verdict naming the failure mode (last-mile congestion, mid-path loss, throughput cap, etc.) rather than a raw metrics dump
- Results are available in machine-readable JSON (`--json` flag), so network engineers can pipe netpath output into other tools or scripts without screen-scraping
- Latency is reported with richer statistics (median, p95, p99) in addition to avg/best/worst, giving a more accurate picture of real-world user experience
- Bufferbloat is detected and reported: the tool shows how much latency increases during an active transfer, which is the metric network engineers most associate with real congestion
- The tool remains a single command with no setup, no persistent storage, and no daemon — run once, get an answer

## Phase Outcomes

- **Phase 1: Richer latency statistics** — Network engineers see median, p95, and p99 latency for each hop, giving a more complete picture of tail latency that average RTT alone hides. The path table reflects these new columns immediately.
- **Phase 2: Bufferbloat measurement** — The tool measures how much latency rises while a transfer is in progress, revealing queuing congestion that only appears under load. This result feeds both the display and the diagnostic verdict.
- **Phase 3: Verdict engine** — Every run concludes with a plain-language diagnosis naming the failure mode and the hop or boundary where it occurs, replacing the need to manually interpret a table of numbers.
- **Phase 4: JSON output** — All collected measurements and the verdict are available as structured JSON via `--json`, letting operators pipe netpath into scripts, dashboards, or alerting systems without screen-scraping.

## Out of Scope

- Continuous monitoring, scheduled runs, or time-series storage — this tool diagnoses a single moment, not trends over time
- Prometheus, InfluxDB, or any metrics-export integration — structured output stops at `--json`
- ECMP-aware multi-path discovery and IPv6 dual-stack testing — high-value but deferred to a follow-up task to keep this scope bounded
- `--json` on the `country` subcommand — the multi-ASN output shape is more complex and better addressed separately once the single-ASN JSON schema is stable

## Scope Summary

**Size:** 14 requirements, 12 acceptance criteria, 4 implementation phases
**Key decisions:**
- p95/p99 estimated from Avg + z*StDev in mtr JSON mode; computed exactly from raw samples in traceroute mode where `rtt_samples` are already collected
- Bufferbloat probed by running concurrent ICMP ping in a background thread during the iperf3 transfer; idle RTT taken from the pre-existing last-hop mtr result via the existing `_extract_last_rtt` helper
- Verdict engine lives in a new `src/netpath/diagnosis.py` module; it is pure computation over the result dict with no I/O or network calls
- `--json` added to the `asn` subcommand only; `country` JSON deferred
**Biggest risk:** Concurrent ping during iperf3 requires ICMP permissions that may be restricted on some systems (same constraint as mtr raw sockets); the fallback path when ping is unavailable must degrade gracefully without crashing.

## Context

netpath currently measures throughput, latency, and loss correctly but presents only raw numbers with no synthesis. Engineers must manually correlate the path table with iperf3 results to draw a conclusion. The mtr JSON report exposes Avg, Best, Wrst, StDev, and Loss% per hop — p50/p95/p99 can be estimated from StDev in mtr mode and computed exactly in traceroute mode where raw per-probe RTT samples are already collected in a `rtt_samples` list. Bufferbloat requires a concurrent measurement not currently performed: the idle RTT is already available from the pre-test mtr run via `_extract_last_rtt(hubs)` in `cli.py`; loaded RTT requires a separate ping thread during the iperf3 window. The verdict engine is entirely new logic that will live in `src/netpath/diagnosis.py`. Platform differences in ping output format (Linux vs macOS summary line syntax) and the threading coordination strategy are the primary design questions for the architecture stage.

## Requirements

### Latency Statistics Enrichment

- R1: Each hop's latency data must include p50 (median), p95, and p99 values alongside the existing Avg/Best/Worst fields. In mtr JSON mode, estimate these from Avg and StDev (p50 ≈ Avg, p95 = Avg + 1.645×StDev, p99 = Avg + 2.326×StDev). In traceroute mode, compute exact percentiles from the `rtt_samples` list already collected per hop. (`src/netpath/mtr.py`)
- R2: The path table must display a p95 column alongside Avg, Best, and Worst. If adding p95 causes the table to exceed 80 columns, the p95 column is dropped from the visible table and p95 remains available only in the underlying data dict and `--json` output; it must never truncate or wrap other columns. (`src/netpath/display.py`)
- R3: Hops with no valid RTT samples (Loss% = 100%, all probes dropped) must carry None for all percentile fields rather than computed estimates from StDev, since the stats are meaningless when no probes returned. (`src/netpath/mtr.py`)

### Bufferbloat Detection

- R4: The idle RTT to the iperf3 server is taken from the last responsive hop in the already-computed mtr/traceroute results, using the existing `_extract_last_rtt(hubs)` helper in `cli.py`. No additional mtr pass is required.
- R5: During the iperf3 transfer, measure loaded RTT by running concurrent ICMP ping probes to the iperf3 server host in a background thread. The probe count must be calibrated to the iperf3 duration so the ping completes within the transfer window (e.g., `ping -c <duration> -i 1` for a duration-second iperf3 run). (`src/netpath/iperf.py` or `src/netpath/cli.py` — architecture stage to decide placement)
- R6: If `ping` is not found or returns a permission error, the tool must complete without error and set loaded RTT to None. The bufferbloat value is reported as "unable to measure" in display and as null in JSON output rather than crashing or silently omitting the field.
- R7: The bufferbloat delta (loaded RTT minus idle RTT) must be exposed in the result dict under a `bufferbloat_ms` key. When unavailable (R6 fallback or speedtest mode), the value is None.
- R8: The display must show a bufferbloat summary line beneath the throughput panel: idle RTT (ms), loaded RTT (ms or "unavailable"), delta (ms), and a qualitative label — "None" for delta < 5ms, "Moderate" for 5–30ms, "Severe" for > 30ms. (`src/netpath/display.py`)

### Verdict Engine

- R9: A new module `src/netpath/diagnosis.py` must expose a single function `diagnose(result: dict) -> dict` that takes the enriched result dict and returns a verdict dict containing: `verdict` (short label string), `severity` ("ok" | "warning" | "critical"), `detail` (one plain-language sentence naming the failure and its location), and `signals` (list of strings naming each contributing measurement).
- R10: The verdict engine must classify the following failure modes in priority order, stopping at the first match: (1) **Severe bufferbloat** — `bufferbloat_ms > 30`; (2) **Mid-path packet loss** — any non-terminal, non-local hop with Loss% > 1%; (3) **Last-mile congestion** — first hop Loss% > 0% combined with `bufferbloat_ms > 5`; (4) **Throughput cap** — measured download Mbps more than 30% below the Cloudflare RUM baseline for the same ASN (only when RUM data is present); (5) **Healthy** — no anomalies detected.
- R11: The display must render a verdict panel below all other output: the `verdict` label styled by severity (green = ok, yellow = warning, red = critical), the `detail` sentence, and the `signals` list as supporting evidence. (`src/netpath/display.py`)
- R12: `diagnose` must handle missing data gracefully: if `bufferbloat_ms` is None, skip all bufferbloat checks; if `rum` is None, skip the throughput-cap check; if the path has only one hop, skip mid-path loss checks. A partial diagnosis is always returned; the function must never raise.

### JSON Output

- R13: The `asn` subcommand must accept a `--json` flag. When set, the command serializes a single JSON object to stdout and suppresses all Rich terminal output. The JSON object must include: `asn`, `target_host`, `path` (array of hop objects with all latency stats including p50/p95/p99), `throughput` (upload and download Mbps, or null if skipped), `bufferbloat_ms` (float or null), `rum` (Cloudflare RUM metrics dict or null), and `verdict` (the full dict from `diagnose`). (`src/netpath/cli.py`)
- R14: When `--json` is combined with `--no-throughput`, the JSON output is still valid — `throughput` and `bufferbloat_ms` are null rather than absent. The schema must be stable regardless of which optional measurements were skipped.

## Acceptance Criteria

- [ ] Running `netpath asn AS15169` shows a p95 column in the path table alongside Avg, Best, and Worst without wrapping on an 80-column terminal; if the column cannot fit, it is absent from the table but present in the returned data dict.
- [ ] Each hop dict returned by `mtr.run()` and `mtr.run_traceroute()` contains `p50`, `p95`, and `p99` keys; hops with Loss% = 100% have all three set to None.
- [ ] Running `netpath asn AS15169` with throughput enabled shows a bufferbloat line beneath the throughput panel with idle RTT, loaded RTT (or "unavailable"), delta, and a qualitative label.
- [ ] If `ping` is not available or permission is denied, the tool completes without error, `bufferbloat_ms` is None, and the display shows "unable to measure".
- [ ] Running `netpath asn AS15169 --json` outputs valid, parseable JSON to stdout with no Rich terminal escape codes; the object contains `path`, `throughput`, `bufferbloat_ms`, and `verdict` keys.
- [ ] Running `netpath asn AS15169 --json --no-throughput` outputs valid JSON with `throughput: null` and `bufferbloat_ms: null` rather than crashing or omitting the keys.
- [ ] On a path with a mid-path hop showing Loss% > 1%, the verdict panel shows severity "warning" or "critical" and the detail sentence contains the word "loss".
- [ ] On a path with no anomalies, the verdict panel shows severity "ok" and the `verdict` label is "Healthy".
- [ ] Calling `diagnose({})` (empty result dict) returns a complete verdict dict with severity "ok" and does not raise an exception.
- [ ] Existing `netpath asn` and `netpath country` invocations without `--json` continue to work with no change in behavior other than the new columns and verdict panel.
- [ ] `netpath asn --help` lists the `--json` flag with a brief description.
- [ ] The `diagnose` function has no imports from `mtr`, `iperf`, `display`, or any module that performs I/O; it is a pure function verifiable by inspection.

## Implementation Phases

### Phase 1: Latency statistics enrichment
**Scope:** Add p50, p95, and p99 to hop dicts returned by both mtr and traceroute code paths, and surface p95 as a new column in the path table where terminal width allows.
**Estimated effort:** Small

### Phase 2: Bufferbloat measurement
**Scope:** Instrument the iperf3 test run with a concurrent ping probe to capture loaded RTT, compute the bufferbloat delta from the idle RTT already available in the mtr result, and display the bufferbloat summary line beneath the throughput panel.
**Estimated effort:** Medium

### Phase 3: Verdict engine
**Scope:** Create `src/netpath/diagnosis.py` with the `diagnose` function and its failure-mode classification logic, wire it into the `asn` command after all measurements complete, and render the verdict panel in the display.
**Estimated effort:** Medium

### Phase 4: JSON output
**Scope:** Add the `--json` flag to the `asn` subcommand, serialize the full enriched result dict (including verdict) to stdout as JSON, and suppress Rich output when the flag is active.
**Estimated effort:** Small

## Edge Cases

- **mtr hop with all probes lost**: Avg and StDev are zero or absent — percentile estimation must not produce negative or divide-by-zero values; treat as None.
- **Short iperf3 duration** (e.g., `--duration 3`): The ping window must be reduced to fit; hardcoding `ping -c <min(duration, 5)> -i 1` is safer than assuming a 5-second window.
- **iperf3 fails mid-transfer**: The ping background thread may outlive the iperf3 process; it must be joined with a timeout and its result discarded if iperf3 fails, not surfaced as a partial measurement.
- **Speedtest fallback** (no iperf3 server found): No fixed host is available to ping during the HTTP speedtest; bufferbloat_ms must be None in this mode.
- **Traceroute-only path** (no throughput): The verdict engine must return a meaningful result covering only path-layer signals (mid-path loss, first-hop loss) without any throughput or bufferbloat input.
- **Single-hop path** (direct peer): No intermediate hops exist to check for mid-path loss; the verdict engine skips that check and falls through to Healthy or another applicable condition.
- **RUM data absent for ASN**: `rum.fetch_asn_quality` returns None; the throughput-cap verdict check must skip silently rather than treating 0 Mbps as a failure.

## Technical Notes

The most structurally significant change is the concurrent ping during iperf3. Python's `subprocess.Popen` can start ping non-blocking; a `threading.Thread` can wait on it while iperf3 runs on the main thread. The thread must parse the average RTT from ping's final summary line — the format differs between Linux (`rtt min/avg/max/mdev`) and macOS (`round-trip min/avg/max/stddev`) — and write the result into a shared `queue.Queue` for the main thread to read after joining. The architecture stage must specify the parse strategy and the exact placement of the probing logic (inside `iperf.py` as an optional parameter, or in `cli.py` orchestration).

`diagnosis.py` is purely functional: it takes a dict and returns a dict. No imports from `mtr`, `iperf`, `display`, or any module that performs I/O. This keeps it trivially testable without mocking.

The JSON schema produced by `--json` should be treated as a stable contract from first release. The architecture stage should document the schema explicitly so future additions (e.g., `country --json`) can extend it consistently.

StDev from mtr is in milliseconds, the same units as Avg — no conversion is needed for the percentile estimation formula. The `statistics.quantiles` function from the Python stdlib computes exact percentiles from `rtt_samples` in traceroute mode with no additional dependencies.

The `--json` flag must suppress Rich output entirely. The cleanest approach is a flag passed into `display` functions or an early-exit branch in cli.py that calls `json.dumps` and returns, since all Rich output routes through `display.console`.

### Dependencies

No new Python packages are required. Concurrent probing uses `threading` and `subprocess` from stdlib. Exact percentile computation uses `statistics` from stdlib. JSON serialization uses `json` from stdlib.

## Architecture

### Open Decisions

**1. Where does the load probe during the iperf3 transfer live?**

The concurrent ping that measures latency-under-load must be coordinated with the throughput test. Where this lives determines whether the bufferbloat result is automatically available to every caller (including future country-mode tests) or must be explicitly wired each time.

- Encapsulate inside the transfer module
- Orchestrate from the command layer (recommended)

**2. How should the tool parse ping summary output across Linux and macOS?**

Linux and macOS produce different summary line formats from ping. An incorrect or partial parse silently yields a wrong bufferbloat value — which is worse than reporting the measurement as unavailable. The parsing strategy determines how robustly the tool degrades when the format is unexpected.

- Try both known patterns, return unavailable if neither matches (recommended)
- Split on delimiters by field position

