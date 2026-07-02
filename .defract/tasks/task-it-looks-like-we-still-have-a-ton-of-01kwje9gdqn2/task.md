---
defract:
  id: task-it-looks-like-we-still-have-a-ton-of-01kwje9gdqn2
  type: task
  status: active
  stage: implementation
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

# Expand coverage command to top 50 countries and address output data gaps

## What We're Building

Expand the coverage overview so it ranks the top 50 countries by probe availability instead of the current top 20, giving a fuller picture of where measurements can be taken. Alongside that, close the most visible gaps in the per-ISP output: pull in more real, reachable test endpoints so fewer network providers show up as blank rows, fall back to available quality data when no endpoint exists, and stop a single failed baseline reading from wiping out the results that did succeed.

## Expected Outcome

- The coverage overview lists the top 50 countries by probe count, with the current option to request a different number still working.
- More internet providers get a real, reachable target to measure against, so fewer show up as blank "no coverage" rows.
- Providers that still have no reachable target display available quality data (typical download/upload speed, latency, and loss) instead of an empty row, whenever that data exists.
- When a speed baseline check partially fails, the reading that succeeded is still shown rather than the whole baseline being discarded.
- Users get a more complete, less patchy view of network coverage and provider quality in everyday runs.

## Phase Outcomes

- **Phase 1: Show the top 50 countries** — Anyone checking coverage sees a much broader ranking of where measurements are possible, instead of being cut off at 20 countries.
- **Phase 2: Fill the blank rows and salvage partial baselines** — Providers that used to appear as empty "no coverage" or "remote-only" entries now show whatever quality data is available for them, and a half-failed speed baseline no longer throws away the half that worked.
- **Phase 3: Find real test targets for more providers** — By drawing on a directory of real network interconnection points, netpath can find a reachable target inside many more providers than before, so measurements run for networks that previously had nothing to test against.

## Out of Scope

- Adding brand-new measurement types or probing methods (no new latency, throughput, or path techniques beyond what already exists).
- Changing the underlying diagnosis rules or how anomalies are detected.
- Country or provider filtering/customization features beyond the expanded country count.
- Analyzing the network paths between two specific providers (an "ASN-to-ASN path" view showing all available routes and the best one). This is a substantial new capability being tracked as a separate task that builds on the endpoint discovery delivered here.
- Reverse-DNS hostname enrichment for trace hops and reworking how unresponsive (`* * *`) hops are displayed — candidate follow-ups, not committed here.

## Scope Summary

**Size:** 8 requirements, 9 acceptance criteria, 3 implementation phases
**Key decisions:**
- Interpret "cover all the gaps" as the concrete, observable gaps in the pasted `country US` run: blank uncovered/remote-only ISP rows and a fully-discarded baseline on partial failure.
- Use PeeringDB `netixlan` (IXP interface IPs per ASN) as an additional, non-RIPE source of reachable trace targets — reusing the PeeringDB access already present in `ixp.py`.
- Backfill Cloudflare Radar (RUM) as the fallback for ASNs that still have no reachable target, since Radar data is ASN-level and needs no live target.
- The ASN-to-ASN path analysis feature is split into its own task (hybrid BGP + live), building on the PeeringDB discovery delivered here.
**Biggest risk:** PeeringDB IXP interface IPs are real router interfaces but not guaranteed to answer ICMP; some targets may still fail to trace, so Radar backfill remains the safety net.

## Context

The `coverage` command (`cli.py:957`) prints a Rich table of probe counts per country, defaulting to the top 20 via `--top` (`cli.py:960`); the ranking and title both derive from that value. Raising the default is a one-line change.

The output-data gaps come from the `country` command flow (`cli.py` ~`716`-`914`). For each ranked ASN, netpath looks for an iperf3 server, then a live trace target via `country.get_test_ip_for_asn` (`country.py:138`) — which today returns only a connected RIPE Atlas probe IP (`country.py:145`). ASNs with neither fall into two branches that `continue` before `_measure()` runs: `remote_only` rows (`cli.py:774`) and `skip_reason`/"no coverage" rows (`cli.py:786`). Because `_measure()` is where Cloudflare Radar data is fetched (`_fetch_rum` at `cli.py:177`, submitted at `cli.py:334`), these rows never get Radar figures even though Radar quality data is keyed by ASN and needs no live target. The summary renderer (`display.py:425`) shows these rows as bare labels with no throughput/latency/loss.

netpath already talks to PeeringDB in `ixp.py` (for IXP prefix classification), so the HTTP client and module-level caching pattern exist. PeeringDB's `netixlan` endpoint (`https://www.peeringdb.com/api/netixlan?asn=N`) returns, per ASN, that network's interface IPs at every IXP it peers on (`ipaddr4`/`ipaddr6`) — real router IPs that generally answer ping/traceroute. Adding this as a target source expands reachable coverage without any RIPE dependency.

Separately, the once-per-run baseline speedtest (`cli.py:661`-`672`) calls `speedtest.run()`, which raises on the first failing direction (`speedtest.py:82`-`90`), so an upload timeout discards a successful download — exactly the failure in the pasted run.

## Requirements

### Coverage command

- R1: The `coverage` command defaults to ranking the top 50 countries instead of 20. The `--top` / `-t` option must still override the default, and the table title must reflect the effective count. (Default at `cli.py:960`; title at `cli.py:977` already interpolates `top`.)

### PeeringDB trace-target discovery

- R2: netpath can look up reachable trace targets for an ASN from PeeringDB's `netixlan` data (the ASN's IXP interface IPs), reusing the existing PeeringDB access/caching pattern in `ixp.py` (or a small sibling helper following the single-purpose module convention).
- R3: `country.get_test_ip_for_asn` (`country.py:138`) is extended so that when no other live target is found, it returns a PeeringDB `netixlan` IPv4 for the ASN when one exists. This augments existing discovery — it does not remove current behavior. (Open question in Technical Notes: whether existing RIPE Atlas target lookup should be removed entirely.)
- R4: When a PeeringDB target is used, its selection is logged in the per-ISP note the same way the current Atlas-target note reads (`cli.py:749`), so the user can see where the target came from.

### Backfilling uncovered and remote-only ISP rows (fallback)

- R5: For ISP rows that still short-circuit to `remote_only` (`cli.py:774`) or `skip_reason`/no-coverage (`cli.py:786`) after target discovery, netpath fetches Cloudflare Radar (RUM) for the ASN when a Cloudflare token is available, using the existing `_fetch_rum` path (`cli.py:177`). No live target required.
- R6: When Radar data is returned for such a row, the per-ISP section prints it (reuse `display.rum_only_panel`, as `_run_test` does at `cli.py:463`), and the country summary tree (`display.py:425`) surfaces the Radar figures for those rows instead of a bare label. When no Radar data exists (no token, or ASN absent), the row falls back to the current label unchanged — no empty or misleading values.

### Resilient baseline speedtest

- R7: `speedtest.run()` no longer discards a successful direction when the other fails. It captures per-direction errors and returns whatever succeeded, so a completed download is still available when the upload times out (and vice versa) — mirroring the `probe_errors` convention.
- R8: The baseline display (`cli.py:670`, `display.baseline_panel`) shows the direction(s) that succeeded and indicates the direction that failed, rather than printing only a warning. If both directions fail, the current warning behavior is preserved.

## Acceptance Criteria

- [ ] Running `netpath coverage` with no `--top` flag prints up to 50 ranked country rows and a title reading "Top 50 Countries"; verified against the default at `cli.py:960`.
- [ ] Running `netpath coverage --top 10` still prints exactly 10 rows with a "Top 10" title (override preserved).
- [ ] For an ASN with IXP presence in PeeringDB but no other live target, `get_test_ip_for_asn` returns a PeeringDB `netixlan` IPv4; verified by a unit test mocking the PeeringDB response (consistent with the project's subprocess/HTTP-mockable test strategy).
- [ ] For an ASN absent from PeeringDB `netixlan`, `get_test_ip_for_asn` behaves exactly as today (no regression); verified by a unit test.
- [ ] In `country` mode, an ISP that gains a PeeringDB target shows a trace section with a note indicating the target's origin.
- [ ] In `country` mode with a Cloudflare token, an ISP that is still remote-only / no-coverage but exists in Radar shows a Radar panel in its section and Radar figures in the summary tree.
- [ ] In `country` mode with no Cloudflare token, remote-only and no-coverage rows render exactly as today (no empty Radar values).
- [ ] With `speedtest._upload` mocked to raise and `_download` mocked to succeed, `run()` returns the download plus a recorded upload error instead of raising; verified by a unit test. Both-fail case preserves the warning with no panel.
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
**Scope:** Backfill Cloudflare Radar quality data for ISP rows that today show as blank "no coverage" or "remote-only" entries, surfacing it in both the per-ISP section and the country summary. Make the baseline speed check return partial results so a single failed direction no longer discards the reading that succeeded.
**Files:** `src/netpath/cli.py` (short-circuit branches at `cli.py:774` and `cli.py:786`; baseline block at `cli.py:661`-`672`), `src/netpath/display.py` (`country_summary` at `display.py:425` and summary subrow helpers), `src/netpath/speedtest.py` (`run` at `speedtest.py:77`, `extract_stats` at `speedtest.py:99`), `tests/` (partial-baseline test).
**Verification:**
- With a Cloudflare token, a formerly remote-only / no-coverage ASN present in Radar shows a Radar panel and summary figures.
- Without a token, those rows render unchanged.
- Unit tests: `_upload` fails / `_download` succeeds → `run()` returns download plus recorded error, no raise; both fail → warning preserved, no panel.
- `pytest` and `ruff check src tests` pass.
**Estimated effort:** Medium

### Phase 3: PeeringDB netixlan trace-target discovery
**Scope:** Give netpath a second, non-RIPE source of reachable test targets by reading a provider's interconnection interface addresses from PeeringDB, so measurements can run for many providers that previously had no target to test against.
**Files:** `src/netpath/ixp.py` (reuse existing PeeringDB access/cache) or a new `src/netpath/peeringdb.py` sibling helper; `src/netpath/country.py` (`get_test_ip_for_asn` at `country.py:138`); `src/netpath/cli.py` (target-origin note at `cli.py:749`); `tests/` (new `netixlan` lookup tests).
**Verification:**
- Unit test: ASN with mocked `netixlan` presence → `get_test_ip_for_asn` returns a PeeringDB IPv4.
- Unit test: ASN absent from `netixlan` → unchanged fallback behavior.
- In `country` mode, an ASN with PeeringDB presence but no Atlas probe now runs a trace with an origin note.
- `pytest` and `ruff check src tests` pass.
**Estimated effort:** Medium

## Edge Cases

- **PeeringDB IXP IP does not answer ICMP:** these are real router interfaces but not guaranteed responsive. Treat a non-responding target like today's dead-target case (fall through to Radar backfill); consider a lightweight reachability check before committing to a target to avoid burning the prober budget (the concern noted in `country.py:142`).
- **ASN present on many IXPs:** `netixlan` may return numerous IPs; pick one deterministically (e.g., first responsive, or first by IXP), and support IPv6 (`ipaddr6`) for dual-stack consistency with existing behavior.
- **No Cloudflare token set:** Radar backfill no-ops cleanly (`_fetch_rum` returns `None`); rows fall back to current labels.
- **ASN absent from both PeeringDB and Radar (e.g. DoD/enterprise networks):** row remains "no coverage" — no dataset can help; behavior unchanged.
- **Both baseline directions fail:** preserve today's behavior (warning, no panel).
- **JSON mode (`--json`):** target-origin and Radar backfill changes must not alter the `--json` contract; summary/panel changes are display-only.

## Technical Notes

Reuse the PeeringDB access already in `ixp.py` (HTTP client + module-level cache per the established in-process caching convention) rather than adding a second PeeringDB client. `netixlan?asn=N` returns objects with `ipaddr4`/`ipaddr6`; strip the `AS` prefix with `asn.normalize_asn()` before querying (bare integer). Cache the per-ASN result in-process.

For target selection in `get_test_ip_for_asn`, keep PeeringDB as a fallback after any existing live target so current behavior is preserved. The Cloudflare Radar backfill (R5-R6) should reuse `_fetch_rum` directly for skipped rows rather than routing them through `_measure()`, which would trigger unwanted trace/latency probes toward dead targets. Store the fetched Radar dict on the summary row (a `rum` key, matching what `_measure` sets at `cli.py:198`) so `country_summary` renders it uniformly.

For the baseline, follow the `probe_errors` convention: attempt each direction independently, collect failures into an errors dict, return whatever succeeded. `extract_stats` (`speedtest.py:99`) assumes both keys are present — update it (or callers) to tolerate a missing direction. Keep exit handling out of `speedtest.py`.

Testing per project strategy: PeeringDB lookup and the partial-baseline logic are unit-testable by mocking the HTTP response / `_download`/`_upload`. Live Radar backfill and real trace reachability are verified manually.

**Open question for the builder (flagged, not assumed):** you said "no RIPE data." This scope *adds* PeeringDB as a target source but leaves the existing RIPE Atlas target lookup in `get_test_ip_for_asn` in place (removing it is a larger, riskier change affecting all of country mode). If you want RIPE Atlas discovery removed entirely, confirm and it can be folded into Phase 3 or split out.

### Dependencies

- The separate ASN-to-ASN path analysis task (proposed) depends on the PeeringDB endpoint discovery delivered in Phase 3.

## Implementation Notes

## Phase 1: Expand coverage to top 50

Raised the `coverage` command's `--top` default from 20 to 50 (`src/netpath/cli.py`). The table title already interpolates `top`, so no title change was needed.

**Files changed:** `src/netpath/cli.py` (one line).

## Phase 2: Fill uncovered/remote-only ISP data and salvage partial baselines

Closed two concrete output gaps from the pasted `country US` run.

**Resilient baseline speedtest (R7/R8):**
- `speedtest.run()` no longer raises when one direction fails. It attempts download and upload independently and returns `{"download": {...}|None, "upload": {...}|None, "server": ..., "errors": {direction: reason}}`, mirroring the `probe_errors` convention.
- `speedtest.extract_stats()` returns `(upload|None, download|None)` so callers render whatever succeeded.
- Both consumers updated: the baseline block (`cli.py`) and the `_measure()` speedtest fallback (`cli.py`). A successful download now survives an upload timeout in every path. Both-directions-fail preserves the original warning with no panel.
- `display.baseline_panel(upload, download, errors=...)` now tolerates a None direction and marks the failed one as `failed` rather than dropping the whole panel.

**Radar backfill for blank rows (R5/R6):**
- The two short-circuit branches (`remote_only`, `skip_reason`/no-coverage) now call the existing `_fetch_rum(asn_str, cf_token)` before `continue`. When Radar data returns, `display.rum_only_panel` prints it in the per-ISP section and the Radar dict is stored on the summary row under a `rum` key (matching what `_measure` sets).
- `display.country_summary` renders a compact Radar figures subrow (`_render_rum_subrow` / `_rum_summary_str`) beneath remote-only and no-coverage rows when `rum` is present. With no token, `_fetch_rum` returns None and rows render exactly as before — no empty values.

**Tests:** `tests/test_speedtest.py` — upload-fails/download-succeeds returns partial (no raise), download-fails/upload-succeeds, both-fail records both errors, both-succeed.

**Files changed:** `src/netpath/speedtest.py`, `src/netpath/cli.py`, `src/netpath/display.py`, `tests/test_speedtest.py`.

## Phase 3: PeeringDB netixlan trace-target discovery

Added a second, non-RIPE source of reachable trace targets (R2-R4).

**PeeringDB netixlan lookup (`src/netpath/ixp.py`):**
- `_load_netixlan(asn)` fetches `https://www.peeringdb.com/api/netixlan?asn=N` (bare integer via `normalize_asn(asn)[2:]`) and caches the record list per-ASN in a module-level `_NETIXLAN_CACHE` dict, reusing the same PeeringDB access/caching pattern as the IXP prefix classifier already in this module. Any failure yields an empty list.
- `netixlan_ipv4_for_asn(asn)` returns the first record with a usable `ipaddr4` (deterministic selection), or None.

**Target discovery (`src/netpath/country.py`):**
- New `get_test_target_for_asn(asn) -> (ipv4, origin)` tries a connected RIPE Atlas probe first (origin `"atlas"`), then falls back to a PeeringDB netixlan IPv4 (origin `"peeringdb"`), else `(None, None)`. Prefix-guessing remains removed.
- `get_test_ip_for_asn(asn)` now wraps `get_test_target_for_asn` and returns just the IPv4 — its plain-string contract is unchanged, so existing behavior and the acceptance-criteria tests hold.

**Origin note (`src/netpath/cli.py`):**
- The per-ISP trace target note now reads `PeeringDB IXP trace target` vs `Atlas probe trace target` based on the origin returned by `get_test_target_for_asn`, so the user can see where the target came from.

**Tests (`tests/test_country.py`):**
- New: PeeringDB fallback returns the netixlan IPv4 with origin `"peeringdb"`; ASN absent from netixlan returns `(None, None)` (no regression); per-ASN caching (second lookup served from cache, one HTTP call).
- Updated the existing Atlas-empty / Atlas-error / null-address tests to also stub the PeeringDB layer so they stay offline and assert the no-target path.

**Files changed:** `src/netpath/ixp.py`, `src/netpath/country.py`, `src/netpath/cli.py`, `tests/test_country.py`.

**Note:** existing RIPE Atlas target lookup was left in place (Atlas tried first, PeeringDB as fallback) per the flagged open question in the scope — removing RIPE entirely was not confirmed.

**Verification:** 153 tests pass (150 + 3 new); `ruff check src tests` clean. Live PeeringDB reachability and the in-`country`-mode origin note are covered in the manual test list.
