---
defract:
  id: task-paris-traceroute-to-cut-ecmp-false-01kwhv8zfhx9
  type: bug
  status: active
  stage: scope
  phase: 0
  total_phases: 3
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

# Paris traceroute to cut ECMP false positives

## Story Brief

From chat: Paris traceroute to cut ECMP false positives (2026-07-02T16:31:35.278Z)

### Findings

- **jitter_ms is StDev of the last responsive hop — only 2 samples in the traceroute fallback** — cli.py:268-271 sets result["jitter_ms"] to the StDev of the last responsive hub (the destination). In the traceroute fallback path (macOS, "mtr unavailable"), that StDev is computed from just 2 RTT samples because _run_traceroute_cmd hardcodes -q 2 (mtr.py:204). On a transcontinental US→India path crossing ECMP-balanced backbone, two probes to the destination can traverse different physical paths, so the StDev captures path diversity, not real jitter. This is the primary driver of the "High Jitter" false positives (20.5–58.6 ms) in the country IN run.
  - Files: src/netpath/cli.py, src/netpath/mtr.py
- **"50% loss" at single hops is a -q 2 quantization artifact, mostly already suppressed** — The traceroute fallback runs -q 2 (mtr.py:204), so per-hop Loss% can only be 0/50/100 — a single unanswered probe reads as 50%. That is why isolated hops (e.g. #1 hop 10, #3 hop 10, #6 hop 16) show 50.0%. diagnosis.py:130-145 already forward-scans: if all downstream responsive hops are clean, it emits the "ok" rate_limited_hop signal instead of mid_path_packet_loss, so most of these correctly resolve to Healthy. The loss false positives are largely handled; the jitter verdict is the one still leaking through.
  - Files: src/netpath/mtr.py, src/netpath/diagnosis.py
- **Paris traceroute fixes the ECMP path-divergence class specifically, not the vantage-point or sample-size problems** — Paris traceroute pins the flow identifier (dest port / ICMP id-seq) constant across probes so every probe to a given TTL follows the same ECMP path. It directly eliminates phantom loss, phantom hops/loops, and RTT variance that is really per-flow load-balancer path diversity — which is a real contributor to the High Jitter and stalled-path signals here. What it does NOT fix: (1) the 2-sample sample-size noise from -q 2, and (2) the fact that measuring India ISPs from a US host inherently sees ~280-430 ms RTT with high variance across transoceanic segments. Paris is the right instrument for the load-balancer artifacts but only part of the picture.
- **Globalping mtr runs near the destination and is the authoritative loss/jitter source vs the local transcontinental trace** — Country mode already schedules Globalping ping + mtr measurements (visible in the IN run: AS9829 Globalping RTT 44.5 ms avg vs the local trace's 403.6 ms). Globalping probes sit near the target ASN, so their loss/jitter reflects the ISP's actual path quality, whereas the local US-origin trace mostly measures the transoceanic backbone. A strong alternative (or complement) to adding a Paris binary locally is to source the loss/jitter verdict inputs from Globalping mtr when available and demote the local traceroute to topology/AS-path only.

### Proposed actions

- **Options to cut the High Jitter false positives: raise -q, adopt a Paris tool, or trust Globalping** — Three levers, cheapest first. (1) Raise the fallback probe count above -q 2 and compute jitter from a real sample; nearly free, no new dependency, removes the 2-sample quantization. (2) Adopt a Paris-capable prober — scamper (CAIDA, -P udp-paris/icmp-paris), dublin-traceroute (Paris + Python bindings), or paris-traceroute — to eliminate ECMP path-divergence variance; note macOS system /usr/sbin/traceroute is not Paris-capable, so this adds a system prerequisite alongside mtr/iperf3. (3) Gate the High Jitter / loss verdicts on Globalping mtr data when a probe exists near the target, treating the local trace as topology only. (2) and (3) are complementary; (1) helps regardless.
  - Files: src/netpath/mtr.py, src/netpath/cli.py, src/netpath/diagnosis.py

### Bugs

- **High Jitter verdict misfires on healthy long-haul paths because jitter comes from 2-sample ECMP-contaminated StDev** — Every India ISP with a completed path in the country IN run got a "High Jitter — unstable latency" verdict (AS9829 20.5 ms, AS4755 58.6 ms, AS9498 19.1 ms, AS17488 23.8 ms) despite Cloudflare Radar showing sub-0.2% loss and normal RTTs for those ASNs. The verdict is derived from the destination hub StDev over just 2 probes across an ECMP-balanced transoceanic path (cli.py:268-271, mtr.py:204), so it reports path diversity + sampling noise as instability. The 10 ms JITTER_WARNING_MS threshold (diagnosis.py:1) was likely calibrated for local mtr runs, not long-haul 2-sample traceroute.
  - Files: src/netpath/cli.py, src/netpath/mtr.py, src/netpath/diagnosis.py

Originating chat: Paris traceroute to cut ECMP false positives (68eb9592-3446-4544-94e8-9750fb30fcbc)

## What We're Building

Netpath currently warns about "High Jitter" on network paths that are actually healthy. The false alarm happens because the fallback prober sends only two test packets, and on long-distance routes those two packets can travel different physical paths through load-balanced internet backbones — so normal route diversity gets reported as instability. This task makes the jitter verdict trustworthy: measure with enough samples, keep each measurement on a consistent route where the tooling allows it, and prefer measurements taken near the target network over the long-haul local view when judging that network's quality.

## Expected Outcome

- Healthy ISPs on the far side of the world no longer receive "High Jitter" warnings that independent data sources contradict
- Jitter is computed from a meaningful number of samples instead of two, eliminating the coin-flip artifacts in loss and jitter figures
- When a Paris-style prober that holds each probe on a consistent route is available on the machine, netpath uses it, so load-balancer route diversity stops masquerading as instability
- When a nearby vantage-point measurement of the target network exists, its loss and jitter figures drive the verdict, and the long-distance local trace is used for path topology only
- Country sweeps produce verdicts a network operator can act on without cross-checking external dashboards

## Phase Outcomes

- **Phase 1: Meaningful samples in the fallback prober** — The backup path prober collects enough measurements per hop that a single lucky or unlucky packet can no longer flip a healthy network into a "High Jitter" warning, and the verdict engine declines to raise a jitter alarm when it has too few samples to judge.
- **Phase 2: Consistent-route probing when a Paris-style prober is installed** — Users who install a route-pinning prober get measurements where every packet follows the same path, so route diversity inside load-balanced backbones stops registering as instability. Users without one see no change and gain no new required install.
- **Phase 3: Nearby measurements drive country-sweep verdicts** — Country sweeps judge each ISP by measurements taken close to that ISP rather than by the long approach path from the user's machine, so the verdicts reflect the ISP's actual quality and the process exit status becomes trustworthy for monitoring.

## Out of Scope

- Throughput measurement (bandwidth testing) is unchanged — this task is about path-quality verdicts only
- Judging the quality of intermediate networks along the route — verdicts continue to describe the target network only
- Running netpath itself from multiple vantage points or making the probe origin configurable — nearby measurements come from the existing remote-probe integration
- Remote-measurement verdict gating for the single-ASN command — remote probing is wired into country sweeps today, and extending it to single-ASN runs is a separate task
- Changing the jitter warning threshold itself — the fix addresses the quality of the inputs, not the cutoff

## Scope Summary

**Size:** 11 requirements, 8 acceptance criteria, 3 implementation phases
**Key decisions:**
- Skip the architecture stage — the work follows the established single-purpose module convention and detailed phases carry the design
- Paris prober support is a new `paris.py` module slotted into the existing fallback chain (mtr → paris → system traceroute), never a hard prerequisite
- Verdict gating stays inside the pure `diagnose()` function via result-dict keys; country mode re-derives verdicts after remote results merge
**Biggest risk:** Paris-capable probers need the same raw-socket privileges that already force mtr into the fallback path, so on an unprivileged macOS host phase 2 may rarely engage — phases 1 and 3 must eliminate the false positives on their own.

## Context

A `country IN` run from a US host produced a "High Jitter" warning for every India ISP with a completed path (20.5–58.6 ms reported jitter) while Cloudflare Radar showed sub-0.2% loss and normal RTTs for the same ASNs. The jitter figure is the StDev of the last responsive hop (`src/netpath/cli.py:268-271`), and in the traceroute fallback that StDev comes from exactly 2 samples because `_run_traceroute_cmd` hardcodes `-q 2` and ignores the `probes` parameter it is passed (`src/netpath/mtr.py:198-217`). Country mode already schedules Globalping ping and mtr measurements from probes inside each target ASN (`src/netpath/globalping.py`, merged in `cli.py:731-818`), but only RTT and outbound AS path are parsed, and the merge happens after `diagnose()` has already set each row's verdict. The loss-side false positives are largely handled by the existing rate-limited-hop forward scan in `src/netpath/diagnosis.py:130-156`; jitter is the signal still leaking through.

## Requirements

### Fallback probe sampling

- R1: The fallback prober sends the requested number of probes per hop instead of the hardcoded two, capped at 5 per hop to bound runtime, with the subprocess timeout scaled to the probe count. (`_run_traceroute_cmd` in `src/netpath/mtr.py` hardcodes `-q 2` and a 60 s timeout; `run_traceroute` must thread its `probes` parameter through.)
- R2: Results record the per-hop sample count that was actually used, so the verdict engine knows how many samples the jitter figure rests on. (`result["probe_count"]` in `_measure()` currently always equals `cycles` even when the fallback ran fewer probes; set it from the effective count when `_trace_method` is the fallback.)

### Verdict calibration

- R3: The High Jitter check does not fire when the jitter figure is derived from fewer than 5 samples; an informational note appears instead. (Check (5) in `src/netpath/diagnosis.py`; mirrors the existing sample-size-calibrated loss thresholds, using an "ok"-severity signal so it displays without elevating the verdict.)

### Paris-capable prober

- R4: When mtr is unavailable or lacks raw-socket permission, netpath prefers a route-pinning Paris prober over the system traceroute if one is installed, so every probe to a hop follows the same path. (New `src/netpath/paris.py` module per the single-purpose module convention; `_trace()` in `src/netpath/cli.py` gains the chain mtr → paris → traceroute.)
- R5: The Paris module detects supported binaries (`dublin-traceroute` first, then `scamper`), runs the first one found, and parses its output into the same hop shape the rest of the pipeline consumes. (Output parsing is a pure function testable with canned output; hop dicts match the `Hub` TypedDict in `src/netpath/types.py` including `Loss%`, `Avg`, `StDev`, and percentile fields.)
- R6: Any Paris-prober failure — binary absent, permission denied, timeout, unparseable output — falls through silently to the existing traceroute path, and the terminal notes which prober produced the displayed path. (Extends the existing "mtr unavailable — using traceroute" note in `_run_test()`; no new hard system prerequisite.)

### Near-target measurements drive the verdict (country mode)

- R7: The remote ping measurement collects enough packets for meaningful loss and jitter figures — raise the packet count from 3 to 16 — and parsing extracts loss percentage and jitter alongside the existing RTT stats. (`schedule_measurements` and a new stats parser in `src/netpath/globalping.py`; the results payload carries per-packet timings and per-probe drop/loss stats.)
- R8: When near-target loss and jitter figures exist for an ASN, they drive the jitter verdict: a clean near-target measurement suppresses a High Jitter warning sourced from the local trace and emits an informational note in its place, while a near-target jitter figure above the threshold fires the warning citing the near-target value. (`diagnose()` reads the parsed figures from keys on the result dict and remains a pure function with no I/O.)
- R9: Near-target loss exceeding the existing calibrated loss thresholds emits a warning signal attributed to the near-target measurement, so genuine loss inside the target network is surfaced rather than hidden by the suppression logic.
- R10: Country mode re-derives each ASN's verdict after remote results merge, so the summary table and the process exit code reflect the remote-aware verdicts. (In `country()` in `src/netpath/cli.py`, Globalping data merges into `summary_rows` after `diagnose()` already ran inside `_measure()`; re-run `diagnose()` on rows that gained remote data before `display.country_summary()` and `_worst_exit_code()`.)
- R11: When no remote data exists for an ASN — `--no-remote`, no probe coverage, scheduling failure, or poll timeout — its verdict behaves exactly as it does after phases 1 and 2, with no regression for uncovered ASNs.

## Acceptance Criteria

- [ ] The fallback prober sends the requested per-hop probe count capped at 5; verified by `tests/test_mtr.py` cases asserting the constructed traceroute command for `probes=3` and `probes=10` via a mocked `subprocess.run`.
- [ ] A jitter figure derived from fewer than 5 samples never produces a High Jitter warning and yields an informational signal instead; verified by `tests/test_diagnosis.py` cases with `probe_count` of 2 and of 5.
- [ ] The Paris module parses canned prober output into hop dicts carrying hop number, host, loss, and RTT statistics; verified by pure-function tests in `tests/test_paris.py`.
- [ ] With mtr permission-denied and a Paris binary present the trace uses the Paris prober, and with no Paris binary it uses the system traceroute; verified by tests mocking binary detection and `subprocess.run`.
- [ ] Remote ping scheduling requests 16 packets and the new parser returns loss percentage and jitter from a canned Globalping results payload; verified by tests in `tests/test_globalping.py`.
- [ ] `diagnose()` with a 20 ms local-trace jitter and clean near-target figures returns no High Jitter warning and includes an informational signal naming the near-target source; with near-target jitter above 10 ms it returns a High Jitter warning citing the near-target figure; verified in `tests/test_diagnosis.py`.
- [ ] `diagnose()` with no near-target data present behaves identically to the phase 1 behavior for the same inputs; verified by regression cases in `tests/test_diagnosis.py`.
- [ ] `pytest` and `ruff check src tests` pass with no regressions in the existing suite.

## Implementation Phases

### Phase 1: Meaningful samples in the fallback prober
**Scope:** The backup path prober collects enough measurements per hop that jitter and loss figures reflect reality instead of a two-packet artifact, and the verdict engine declines to raise a jitter alarm when the sample is too small to judge.
**Files:** `src/netpath/mtr.py` (thread `probes` into `_run_traceroute_cmd`, cap at 5, scale timeout), `src/netpath/cli.py` (record effective `probe_count` when the fallback ran), `src/netpath/diagnosis.py` (sample-size gate on the High Jitter check), `tests/test_mtr.py`, `tests/test_diagnosis.py`
**Verification:**
- `tests/test_mtr.py` asserts the traceroute command contains the capped `-q` value for `probes=3` and `probes=10` (mocked `subprocess.run`)
- `tests/test_diagnosis.py` asserts no High Jitter warning at `probe_count=2` and normal behavior at `probe_count=5` and `probe_count=10`
- `pytest` and `ruff check src tests` pass
**Estimated effort:** Small

### Phase 2: Consistent-route probing via a Paris-capable prober
**Scope:** When a route-pinning prober is installed, netpath uses it in place of the system traceroute so that every probe follows the same path and load-balancer route diversity stops appearing as loss or jitter. Machines without one behave exactly as today.
**Files:** `src/netpath/paris.py` (new: binary detection, runner, pure output parser producing `Hub`-shaped dicts), `src/netpath/cli.py` (`_trace()` fallback chain mtr → paris → traceroute; prober note in `_run_test()`), `tests/test_paris.py`
**Verification:**
- `tests/test_paris.py` parses canned `dublin-traceroute` and `scamper` output into hop dicts with `count`, `host`, `Loss%`, `Avg`, `StDev`, and percentile fields
- Fallback-chain tests: mtr permission error plus Paris binary present selects the Paris prober; Paris absent or failing selects the system traceroute (mocked detection and `subprocess.run`)
- `pytest` and `ruff check src tests` pass
**Estimated effort:** Medium

### Phase 3: Near-target measurements drive country-sweep verdicts
**Scope:** Country sweeps judge each ISP by loss and jitter measured from probes near that ISP, with the long-haul local trace kept for topology. Verdicts, the summary table, and the exit code reflect the near-target view whenever remote coverage exists, and are unchanged where it does not.
**Files:** `src/netpath/globalping.py` (16-packet ping, loss/jitter stats parser), `src/netpath/diagnosis.py` (near-target gating of the High Jitter check plus the near-target loss warning), `src/netpath/cli.py` (merge parsed figures into rows, re-run `diagnose()` post-merge before summary and exit code), `src/netpath/display.py` (show near-target loss/jitter and verdict source in the summary), `tests/test_globalping.py`, `tests/test_diagnosis.py`
**Verification:**
- `tests/test_globalping.py` asserts the scheduling payload requests 16 packets and the stats parser returns loss and jitter from a canned results payload
- `tests/test_diagnosis.py` covers suppression with clean remote figures, warning with poor remote figures, the near-target loss warning, and identical behavior when remote keys are absent
- Manual check: `netpath country IN --top 3` produces verdicts consistent with the near-target figures shown
- `pytest` and `ruff check src tests` pass
**Estimated effort:** Medium

## Edge Cases

- Higher per-hop probe counts multiply fallback runtime (30 hops × probes × 1 s wait worst case): cap at 5 probes per hop and scale the subprocess timeout so a slow filtered path cannot hang the sweep.
- Paris binary installed but lacking raw-socket privileges (the common unprivileged-macOS case): treat exactly like the mtr permission error — fall through silently to the system traceroute.
- Globalping returns fewer probes or packets than requested: compute loss and jitter from whatever timings arrived, and only let remote figures drive the verdict when a minimum sample (at least 5 packets) exists; otherwise fall back to local-trace behavior.
- Remote jitter clean but remote loss high (or vice versa): the two checks act independently — suppressing the jitter warning must not hide a genuine near-target loss warning.
- Per-ISP verdict panels print during the sweep, before remote results merge: the post-merge summary table and exit code are authoritative, and the verdict detail names the near-target source so the discrepancy is explainable.
- ASNs skipped in the sweep (no servers, no test IP) have no verdict key: re-diagnosis must skip them, preserving the existing no-spurious-exit-code behavior.
- The mtr (non-fallback) path with default `cycles=10` already has 10 samples per hop: the new sample-size gate must leave its behavior unchanged.
- `diagnose()` wraps everything in a safety-net except-handler: new remote-data keys must be read defensively (missing, None, or partial dicts) so a malformed payload degrades to current behavior rather than a Healthy-by-exception verdict.

## Technical Notes

The jitter threshold (`JITTER_WARNING_MS = 10.0`) is deliberately unchanged — the problem is input quality, not the cutoff. `diagnose()` stays a pure function: remote figures arrive as plain keys parsed upstream (suggested shape: extend the existing per-row `globalping` dict with `ping_loss_pct` and `ping_jitter_ms` next to the current `ping_rtt`), and `diagnose()` only reads them. This placement follows the established rule that context-dependent signal re-classification lives in `diagnosis.py`, not in the transport modules.

Globalping ping results carry per-probe `stats` (min/avg/max/loss/drop) and per-packet `timings` arrays; jitter should be computed per probe from its timings (standard deviation) and aggregated across probes (median is robust to one bad probe), while loss aggregates from the stats fields. The 16-packet request is the API's per-measurement maximum and costs no additional credits under the free tier.

For the Paris module, `dublin-traceroute` is preferred (purpose-built Paris implementation, JSON output, brew-installable) with `scamper` as the alternate (CAIDA-maintained, `-O json` output, `trace -P icmp-paris`). Both need raw-socket privileges, so the module must map permission failures to a silent fall-through rather than an error — on unprivileged macOS the phase 2 path may rarely engage, which is why phases 1 and 3 carry the false-positive fix on their own. The parser lives as module-private pure functions (`_parse_...`) importable directly in tests, matching the existing `mtr._parse_traceroute_output` test pattern.

Re-diagnosis in country mode should be a small helper that re-runs `diagnose(row)` for rows that gained remote data, replacing `row["verdict"]` before `display.country_summary()` and the exit-code computation. Skipped ASNs without a `verdict` key are excluded, preserving the existing exit-code contract (0=ok, 1=warning, 2=critical).