---
defract:
  id: task-it-looks-like-we-still-have-a-ton-of-01kwje9gdqn2
  type: task
  status: active
  stage: scope
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

It looks like we still have a ton of gaps in our output data I want to cover all the gaps, also for the coverage command I want to see the top 50 countries  nickmoore@Nicks-MacBook-Air  ~  netpath coverage                                                                                                                                           ✔  440  16:04:21

╭─────────────────────────────────────────────────────────────────────────────────╮
│  netpath  network path analyzer — throughput · latency · packet loss · AS hops  │
╰─────────────────────────────────────────────────────────────────────────────────╯

    Globalping Coverage — Top 20 Countries
╭────┬──────┬────────────────────────┬────────╮
│  # │ Code │ Country                │ Probes │
├────┼──────┼────────────────────────┼────────┤
│  1 │  US  │ United States          │   1048 │
│  2 │  DE  │ Germany                │    511 │
│  3 │  NL  │ Netherlands            │    336 │
│  4 │  RU  │ Russia                 │    185 │
│  5 │  GB  │ United Kingdom         │    178 │
│  6 │  SG  │ Singapore              │    176 │
│  7 │  IN  │ India                  │    163 │
│  8 │  FR  │ France                 │    161 │
│  9 │  BR  │ Brazil                 │    126 │
│ 10 │  JP  │ Japan                  │    126 │
│ 11 │  CA  │ Canada                 │    125 │
│ 12 │  HK  │ Hong Kong              │    118 │
│ 13 │  FI  │ Finland                │    106 │
│ 14 │  AU  │ Australia              │     90 │
│ 15 │  TH  │ Thailand               │     87 │
│ 16 │  PL  │ Poland                 │     85 │
│ 17 │  RO  │ Romania                │     68 │
│ 18 │  SE  │ Sweden                 │     68 │
│ 19 │  CH  │ Switzerland            │     66 │
│ 20 │  ID  │ Indonesia              │     66 │
╰────┴──────┴────────────────────────┴────────╯
 nickmoore@Nicks-MacBook-Air  ~  netpath country US                                                                                                                                         ✔  441  16:04:28

╭─────────────────────────────────────────────────────────────────────────────────╮
│  netpath  network path analyzer — throughput · latency · packet loss · AS hops  │
╰─────────────────────────────────────────────────────────────────────────────────╯

Ranking top 10 ASNs for US via RIPE allocation data + Cymru…

✓ Top 10 ASNs for US:

   1.  AS701  Verizon Business  2,439,168 IPs · 10 prefixes
   2.  AS7922  Comcast Cable Communications  2,129,920 IPs · 3 prefixes
   3.  AS11426  Charter Communications Inc  1,115,136 IPs · 3 prefixes
   4.  AS7018  AT&T Enterprises  984,320 IPs · 11 prefixes
   5.  AS56  United States Department of Defense (DoD)  720,896 IPs · 8 prefixes
   6.  AS749  United States Department of Defense (DoD)  544,000 IPs · 37 prefixes
   7.  AS6128  Cablevision Systems Corp.  532,480 IPs · 2 prefixes
   8.  AS306  United States Department of Defense (DoD)  393,216 IPs · 2 prefixes
   9.  AS45102  Alibaba (US) Technology Co.  344,064 IPs · 3 prefixes
  10.  AS721  United States Department of Defense (DoD)  328,704 IPs · 9 prefixes

Measuring your connection baseline (speed.cloudflare.com)…
  ⚠ Baseline speedtest failed: Upload test failed: ('Connection aborted.', TimeoutError('The write operation timed out'))

Fetching + resolving iperf3 server list…

Discovering Globalping probes…
✓ Globalping probes found in 6/10 ASNs


 #1  AS701  Verizon Business  2,439,168 IPs  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → remote-only — no live trace target in AS701; Globalping probes will measure toward your public IP


 #2  AS7922  Comcast Cable Communications  2,129,920 IPs  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → 24.128.98.241  (Atlas probe trace target — no iperf3 server in AS7922)

  Tracing path (10 probes)…
  (mtr unavailable — using traceroute + Cymru ASN lookup)


    #   Host                 ASN                             Type          Loss         Avg        Best       Worst         p95
 ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    1   192.168.68.1         —                               transit       0.0%     21.6 ms     10.5 ms     49.3 ms     49.3 ms
    2   192.168.0.1          —                               transit       0.0%     41.9 ms     11.5 ms     63.5 ms     63.5 ms
    3   207.225.112.16       AS209 (CENTURYLINK-US-LEGAC)    transit       0.0%     52.1 ms     38.9 ms     75.8 ms     75.8 ms
    4   63.225.124.121       AS209 (CENTURYLINK-US-LEGAC)    transit       0.0%     40.0 ms     31.2 ms     56.0 ms     56.0 ms
    5   * * *                —                               —                —           —           —           —           —
    6   4.69.219.74          AS3356 (Level 3 Parent)         transit       0.0%     42.6 ms     42.6 ms     42.6 ms     42.6 ms
    7   * * *                —                               —                —           —           —           —           —
    8   96.216.147.70        AS7922 (Comcast Cable Commun)   dest          0.0%    356.8 ms    356.8 ms    356.8 ms    356.8 ms
    9   68.86.179.214        AS7922 (Comcast Cable Commun)   dest          0.0%     81.4 ms     40.4 ms    124.2 ms    124.2 ms
   10   96.217.60.246        AS7922 (Comcast Cable Commun)   dest          0.0%     56.2 ms     56.2 ms     56.2 ms     56.2 ms

    + 20 hops beyond — ICMP TTL-exceeded filtered
  AS path: AS209 (CENTURYLINK-US-LEGACY-QWEST - CenturyLink Communications) → AS3356 (Level 3 Parent) → AS7922 (Comcast Cable Communications)

╭─ Cloudflare Radar · AS7922 (7d) ─╮
│   ↓ 300 Mbps   ↑ 57 Mbps         │
│   idle 46 ms   loaded 103 ms     │
│   loss 0.00%                     │
╰──────────────────────────────────╯

╭────────────────── Diagnosis ──────────────────╮
│   Healthy                                     │
│   No anomalies detected on the measured path. │
╰───────────────────────────────────────────────╯


 #3  AS11426  Charter Communications Inc  1,115,136 IPs  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → 45.36.6.26  (Atlas probe trace target — no iperf3 server in AS11426)

  Tracing path (10 probes)…
  (mtr unavailable — using traceroute + Cymru ASN lookup)


    #   Host                 ASN                              Type          Loss         Avg        Best       Worst         p95
 ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    1   192.168.68.1         —                                transit       0.0%     77.5 ms     34.1 ms    134.7 ms    134.7 ms
    2   192.168.0.1          —                                transit       0.0%     53.5 ms     17.0 ms     89.8 ms     89.8 ms
    3   207.225.112.16       AS209 (CENTURYLINK-US-LEGAC)     transit       0.0%     76.0 ms     36.5 ms    150.0 ms    150.0 ms
    4   63.225.124.121       AS209 (CENTURYLINK-US-LEGAC)     transit       0.0%     34.1 ms     29.8 ms     37.6 ms     37.6 ms
    5   * * *                —                                —                —           —           —           —           —
    6   4.69.206.169         AS3356 (Level 3 Parent)          transit       0.0%    110.5 ms    110.5 ms    110.5 ms    110.5 ms
    7   *                    —                                transit       0.0%     49.3 ms     49.3 ms     49.3 ms     49.3 ms
    8   66.109.6.91          AS7843 (Charter Communicatio)    transit      60.0%    114.2 ms     85.5 ms    142.9 ms    142.9 ms
    9   66.109.6.37          AS7843 (Charter Communicatio)    transit       0.0%    113.1 ms    113.1 ms    113.1 ms    113.1 ms
   10   *                    —                                transit       0.0%     99.0 ms     99.0 ms     99.0 ms     99.0 ms
   11   24.93.70.46          AS11426 (Charter Communicatio)   dest          0.0%     80.3 ms     80.3 ms     80.3 ms     80.3 ms
   12   24.93.64.197         AS11426 (Charter Communicatio)   dest          0.0%     98.9 ms     85.5 ms    117.9 ms    117.9 ms
   13   24.28.255.33         AS11426 (Charter Communicatio)   dest         20.0%    130.1 ms     97.0 ms    191.8 ms    191.8 ms
   14   24.74.244.113        AS11426 (Charter Communicatio)   dest          0.0%    139.1 ms    104.7 ms    197.1 ms    197.1 ms

    + 16 hops beyond — ICMP TTL-exceeded filtered
  AS path: AS209 (CENTURYLINK-US-LEGACY-QWEST - CenturyLink Communications) → AS3356 (Level 3 Parent) → AS7843 (Charter Communications Inc) → AS11426 (Charter Communications Inc)

╭─ Cloudflare Radar · AS11426 (7d) ─╮
│   ↓ 324 Mbps   ↑ 30 Mbps          │
│   idle 57 ms   loaded 129 ms      │
│   loss 0.00%                      │
╰───────────────────────────────────╯

╭───────────────────────────────────────────── Diagnosis ──────────────────────────────────────────────╮
│   Mid-path Packet Loss                                                                               │
│   Packet loss of 60.0% detected at 66.109.6.91, suggesting a congested or faulty intermediate hop.   │
│                                                                                                      │
│   • Packet loss of 60.0% detected at 66.109.6.91, suggesting a congested or faulty intermediate hop. │
│   • Path jitter of 37.4 ms exceeds the 10.0 ms threshold, indicating unstable latency.               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────╯


 #4  AS7018  AT&T Enterprises  984,320 IPs  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → remote-only — no live trace target in AS7018; Globalping probes will measure toward your public IP


 #5  AS56  United States Department of Defense (DoD)  720,896 IPs  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → no coverage — no iperf3 server, Atlas probe, or usable Globalping coverage


 #6  AS749  United States Department of Defense (DoD)  544,000 IPs  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → no coverage — no iperf3 server, Atlas probe, or usable Globalping coverage


 #7  AS6128  Cablevision Systems Corp.  532,480 IPs  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  → 69.112.140.24  (Atlas probe trace target — no iperf3 server in AS6128)

# Expand coverage command to top 50 countries and address output data gaps

# Expand coverage command to top 50 countries and address output data gaps

## What We're Building

Expand the coverage overview so it ranks the top 50 countries by probe availability instead of the current top 20, giving a fuller picture of where measurements can be taken. Alongside that, close the most visible gaps in the per-ISP output so fewer network providers show up as blank rows with no data, and so a single failed baseline reading no longer wipes out the results that did succeed.

## Expected Outcome

- The coverage overview lists the top 50 countries by probe count, with the current option to request a different number still working.
- Internet providers that currently show up as "no coverage" or "remote-only" now display available quality data (typical download/upload speed, latency, and loss) instead of an empty row, whenever that data exists.
- When a speed baseline check partially fails, the reading that succeeded is still shown rather than the whole baseline being discarded.
- Users get a more complete, less patchy view of network coverage and provider quality in everyday runs.

## Phase Outcomes

- **Phase 1: Show the top 50 countries** — Anyone checking coverage sees a much broader ranking of where measurements are possible, instead of being cut off at 20 countries.
- **Phase 2: Fill the blank rows and salvage partial baselines** — Providers that used to appear as empty "no coverage" or "remote-only" entries now show whatever quality data is available for them, and a half-failed speed baseline no longer throws away the half that worked.

## Out of Scope

- Adding brand-new measurement types or probing methods (no new latency, throughput, or path techniques beyond what already exists).
- Changing the underlying diagnosis rules or how anomalies are detected.
- Country or provider filtering/customization features beyond the expanded country count.
- Reverse-DNS hostname enrichment for trace hops and reworking how unresponsive (`* * *`) hops are displayed — these are candidate follow-ups flagged in Technical Notes, not committed here.

## Scope Summary

**Size:** 6 requirements, 7 acceptance criteria, 2 implementation phases
**Key decisions:**
- Interpret "cover all the gaps" as the concrete, observable gaps in the pasted `country US` run: blank uncovered/remote-only ISP rows and a fully-discarded baseline on partial failure. Other gaps are flagged for builder confirmation rather than silently included.
- Reuse the existing Cloudflare Radar (RUM) fetch to backfill uncovered/remote-only rows, since Radar data is ASN-level and needs no live trace target.
**Biggest risk:** "Cover all the gaps" is open-ended; the committed set may not match the builder's mental list of gaps. The scope names the exact gaps addressed so the builder can prune or extend before implementation.

## Context

The `coverage` command (`cli.py:957`) prints a Rich table of probe counts per country, defaulting to the top 20 via `--top` (`cli.py:960`); the ranking and title both derive from that value (`cli.py:972`, `cli.py:977`). Raising the default is a one-line change.

The output-data gaps come from the `country` command flow (`cli.py` around `716`-`914`). For each ranked ASN, ISPs with no iperf3 server and no Atlas trace target fall into one of two branches that `continue` before `_measure()` runs: `remote_only` rows (`cli.py:774`) and `skip_reason` / "no coverage" rows (`cli.py:786`). Because `_measure()` is where Cloudflare Radar data is fetched (`_fetch_rum` at `cli.py:177`, submitted at `cli.py:334`), these rows never get Radar figures even though Radar quality data is keyed by ASN and needs no live target. The summary renderer (`display.py:425`) shows these rows as bare labels — "remote-only" or the skip reason — with no throughput/latency/loss.

Separately, the once-per-run baseline speedtest (`cli.py:661`-`672`) calls `speedtest.run()`, which raises a `RuntimeError` on the first failing direction (`speedtest.py:82`-`90`). An upload timeout therefore discards a perfectly good download result, and the user sees only a warning with no baseline — exactly the "Baseline speedtest failed: Upload test failed" case in the pasted run.

## Requirements

### Coverage command

- R1: The `coverage` command defaults to ranking the top 50 countries instead of 20. The `--top` / `-t` option must still override the default, and the table title must reflect the effective count. (Default lives at `cli.py:960`; title at `cli.py:977` already interpolates `top`.)

### Backfilling uncovered and remote-only ISP rows

- R2: For ISP rows that currently short-circuit to `remote_only` (`cli.py:774`) or `skip_reason`/no-coverage (`cli.py:786`), netpath fetches Cloudflare Radar (RUM) quality data for the ASN when a Cloudflare token is available, using the existing `_fetch_rum` path (`cli.py:177`, `rum.fetch_asn_quality`). No live trace target is required.
- R3: When Radar data is returned for such a row, the per-ISP section prints it (reuse `display.rum_only_panel`, as `_run_test` already does at `cli.py:463`) instead of only the one-line "remote-only" / "no coverage" note.
- R4: The country summary tree (`display.py:425`) surfaces the Radar figures for remote-only and no-coverage rows, so those rows show download/upload/latency/loss instead of a bare label. When no Radar data exists (no token, or ASN absent from Radar), the row falls back to the current label unchanged — no empty or misleading values.

### Resilient baseline speedtest

- R5: `speedtest.run()` no longer discards a successful direction when the other direction fails. It captures per-direction errors and returns whatever succeeded, so a download that completed is still available when the upload times out (and vice versa). This mirrors the codebase's `probe_errors` convention of recording partial failures rather than aborting.
- R6: The baseline display (`cli.py:670`, `display.baseline_panel`) shows the direction(s) that succeeded and indicates the direction that failed, rather than printing only a warning and no panel. If both directions fail, the current warning behavior is preserved.

## Acceptance Criteria

- [ ] Running `netpath coverage` with no `--top` flag prints up to 50 ranked country rows and a title reading "Top 50 Countries"; verified by inspecting the command output and the default at `cli.py:960`.
- [ ] Running `netpath coverage --top 10` still prints exactly 10 rows with a "Top 10" title (override preserved).
- [ ] In `country` mode with a valid Cloudflare token, an ISP that would otherwise be "remote-only" or "no coverage" but exists in Cloudflare Radar shows a Radar panel in its per-ISP section and Radar figures in the summary tree.
- [ ] In `country` mode with no Cloudflare token, remote-only and no-coverage rows render exactly as they do today (bare label, no empty Radar values) — no regression.
- [ ] With `speedtest.run()` mocked so `_upload` raises and `_download` succeeds, `run()` returns the download result plus a recorded upload error instead of raising; verified by a unit test in `tests/`.
- [ ] With both directions mocked to fail, the baseline still surfaces a warning and no panel (current behavior preserved).
- [ ] `pytest` and `ruff check src tests` both pass.

## Implementation Phases

### Phase 1: Expand coverage to top 50
**Scope:** Raise the default number of countries shown in the coverage overview from 20 to 50, keeping the ability to request a custom count.
**Files:** `src/netpath/cli.py` (`coverage` command default at `cli.py:960`).
**Verification:**
- `netpath coverage` prints up to 50 rows with a "Top 50 Countries" title.
- `netpath coverage --top 10` prints 10 rows with a "Top 10 Countries" title.
- `ruff check src` passes.
**Estimated effort:** Small

### Phase 2: Fill uncovered/remote-only ISP data and salvage partial baselines
**Scope:** Backfill Cloudflare Radar quality data for ISP rows that today show as blank "no coverage" or "remote-only" entries, surfacing that data in both the per-ISP section and the country summary. Make the baseline speed check return partial results so a single failed direction no longer discards the reading that succeeded.
**Files:** `src/netpath/cli.py` (short-circuit branches at `cli.py:774` and `cli.py:786`; baseline block at `cli.py:661`-`672`), `src/netpath/display.py` (`country_summary` at `display.py:425` and the summary subrow helpers), `src/netpath/speedtest.py` (`run` at `speedtest.py:77`), `tests/` (new test for partial-baseline behavior).
**Verification:**
- With a Cloudflare token, a formerly remote-only / no-coverage ASN present in Radar shows a Radar panel and summary figures.
- Without a token, those rows render unchanged (no empty Radar values).
- Unit test: `_upload` fails and `_download` succeeds → `run()` returns the download plus a recorded upload error and does not raise.
- Unit test: both directions fail → baseline warning preserved, no panel.
- `pytest` and `ruff check src tests` pass.
**Estimated effort:** Medium

## Edge Cases

- **No Cloudflare token set:** R2-R4 must no-op cleanly — `_fetch_rum` already returns `None` without a token (`cli.py:178`); rows fall back to their current labels.
- **ASN absent from Cloudflare Radar:** Radar returns no data; render the existing label, never an empty or zero-filled Radar panel.
- **Both baseline directions fail:** Preserve today's behavior (warning, no panel) — do not synthesize a partial panel from nothing.
- **JSON mode (`--json`):** Radar backfill for skipped rows must remain consistent with existing JSON serialization; the summary/panel changes are display-only and must not alter the `--json` contract.
- **Radar fetch latency for many skipped rows:** a country sweep may have several uncovered ASNs; the Radar fetch already runs with a timeout (`cli.py:352`, 15s) — ensure backfill fetches do not serialize into a long stall (reuse the executor pattern where practical).

## Technical Notes

The Cloudflare Radar fetch is already isolated behind `_fetch_rum(asn, cf_token)` (`cli.py:177`) and `rum.fetch_asn_quality` — reuse it directly for the skipped rows rather than routing them through `_measure()`, which would also trigger unwanted trace/latency probes for ASNs with no reachable target. Store the fetched Radar dict on the existing `remote_only` / `skip_reason` summary row dicts (e.g. a `rum` key, matching the `rum` key `_measure` already sets at `cli.py:198`) so `country_summary` can render it uniformly.

For the baseline, follow the established `probe_errors` convention (see the project memory on unified `probe_errors`): have `speedtest.run()` attempt each direction independently, collect failures into an errors dict, and return whatever succeeded. `extract_stats` (`speedtest.py:99`) assumes both `download` and `upload` keys are present — update it (or its callers) to tolerate a missing direction. Keep `raise typer.Exit` usage out of `speedtest.py`; error handling stays at the CLI display layer.

Testing: per the project's test strategy (pure/subprocess-mockable modules only), the partial-baseline logic is testable by mocking `speedtest._download` / `speedtest._upload`. The Radar backfill involves network I/O and is not a unit-test target; verify it manually with a token.

**Open question for the builder (flagged, not assumed):** "Cover all the gaps" is broad. This scope commits to the two concrete, observable gaps in the pasted `country US` run (blank uncovered/remote-only rows; discarded partial baseline). Other candidate gaps — reverse-DNS hostnames for trace hops, richer display of `* * *` unresponsive hops, or surfacing per-ISP throughput in country mode beyond Radar — are intentionally left out (see Out of Scope). If any of these are part of the intended "all gaps," confirm and they can be folded in or split into follow-up tasks.
