---
defract:
  id: task-country-as-path-visual-binat-rtt-anomaly-01kwaw3774eb
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

# Country AS-path visual + Binat RTT anomaly

# Country AS-path Visual + Binat RTT Anomaly Fix

## What We're Building

Two related improvements to the `country` subcommand. First, a bug fix: when a traceroute path never reaches the target ISP's network, the tool currently reports the RTT of the last transit router as if it were an in-country measurement — this produces misleadingly fast numbers (e.g. 26 ms when the true path is unreachable). Second, a new visual tree display groups destination ISPs by their shared transit entry point and color-codes each by latency, making it immediately clear which transit networks serve a country and which paths are actually verified.

## Expected Outcome

- ISPs whose paths never entered their own network are labeled as incomplete rather than showing a falsely low RTT from a mid-ocean transit router
- The country summary gains a tree view grouping ISPs under their shared network entry point (e.g. "reached via Lumen", "reached via Telia")
- Each ISP row shows a color-coded latency reading: green for fast (< 120 ms), yellow for moderate (120–200 ms), red for slow (> 200 ms), grey for incomplete
- Incomplete paths appear in a separate dimmed branch with a warning indicator rather than competing in the ranking
- A star marker and a footer line identify the single fastest verified entry point into the country

## Phase Outcomes

- **Phase 1: Fix the RTT anomaly** — ISPs that were never actually reached no longer show a misleadingly low latency in the country summary; instead they are flagged as incomplete, giving an honest picture of reachability.
- **Phase 2: Tree summary display** — The country summary panel reorganizes into a tree that groups ISPs under the transit network that carries traffic into the country, with latency color-coded for at-a-glance comparison and a star on the fastest verified path.

## Out of Scope

- Changes to how traceroute or iperf3 data is collected — this task is limited to classification and display logic
- Changes to the `asn` subcommand or its output format
- Adding JSON output mode to the `country` subcommand

## Scope Summary

**Size:** 7 requirements, 6 acceptance criteria, 2 implementation phases
**Key decisions:**
- Classification logic lives in `cli.py`; rendering changes are isolated to `display.py`
- Phase 1 (RTT fix) is independently shippable before Phase 2 (tree visual) — this is the primary reason for the split
- New latency thresholds for country-level comparison (120 ms / 200 ms) are kept separate from the existing per-hop thresholds in `fmt_latency` (20 ms / 80 ms); a new function is added rather than modifying the shared one
**Biggest risk:** Correctly identifying the "entry transit" ASN across both the mtr path (where `--aslookup` annotates ASNs natively) and the traceroute fallback path (where Cymru bulk lookup is done per IP after the fact) — the ASN field may be absent or `AS???` for some hops in both cases

## Context

The `country` subcommand (`cli.py:339`) loops over top ASNs, runs a traceroute per ISP, and builds `summary_rows` passed to `display.country_summary`. The current bug is in `_extract_last_rtt` (`cli.py:44`): it returns the RTT of the last responsive hop regardless of whether that hop is inside the target ASN. When the traceroute stops at a transit router before entering the target ISP's network — as observed with Binat/Internet_Binat — the transit RTT is falsely attributed to the ISP.

The AS path is built by `_extract_as_path` (`cli.py:35`) from the hubs list. Whether the target ASN appears in any hub is a reliable signal for path completeness. The last transit ASN before the destination is derivable from the same path list and will serve as the grouping key for the tree display.

## Requirements

### Path Completeness Classification

- R1: A new helper `_classify_path(hubs, target_asn)` in `cli.py` replaces the `_extract_last_rtt` call inside `_run_test`. It returns a dict with `complete` (bool), `rtt_ms` (float or None), and `entry_transit_asn` (str or None). `complete` is True only when `target_asn` appears in at least one hub's `ASN` field.
- R2: When `complete` is True, `rtt_ms` is the Avg RTT of the last hub whose ASN matches `target_asn`. When `complete` is False, `rtt_ms` is None — it is never the RTT of a transit hop.
- R3: `entry_transit_asn` is the last distinct non-`AS???` ASN before `target_asn` in the path (when complete), or the last non-`AS???` ASN seen in the path when incomplete. If the path has no resolvable ASNs at all, it is None.
- R4: The `_run_test` result dict gains three new keys: `path_complete` (bool), `verified_rtt_ms` (float or None), and `entry_transit_asn` (str or None). The existing `last_rtt_ms` key is preserved and still set (to the last responsive hop regardless of ASN) for backward compatibility in the `asn` subcommand's JSON output, but the country summary uses `verified_rtt_ms` instead.
- R5: `summary_rows` in the `country` command includes `path_complete`, `verified_rtt_ms`, and `entry_transit_asn` for each row, propagated from the result dict `r`.

### Tree Summary Display

- R6: `display.country_summary` groups result rows by `entry_transit_asn`. Each group renders as a tree branch headed by the transit ASN (with org name if derivable from a batched Cymru lookup on entry transit IPs, otherwise just the ASN code). Rows with `path_complete = False` or `verified_rtt_ms = None` are collected into a final dimmed branch at the end.
- R7: Within each branch, ISP rows show the ISP name and a color-coded RTT: green < 120 ms, yellow 120–200 ms, red > 200 ms, grey for incomplete (displayed as "— ⚠ incomplete"). The ISP with the lowest `verified_rtt_ms` across all complete rows receives a "★" prefix. A one-line footer names the fastest entry transit and its best ISP latency.

## Acceptance Criteria

- [ ] Running `netpath country IL` with Binat reachable only via transit: Binat appears in the incomplete branch with no RTT, not in the ranked list with a sub-30 ms reading. (Verify by inspecting that `path_complete = False` for that row, or by reading the summary output.)
- [ ] ISPs sharing the same `entry_transit_asn` are grouped together under one branch heading in the country summary.
- [ ] A verified ISP with RTT < 120 ms shows the latency in green; 120–200 ms in yellow; > 200 ms in red.
- [ ] Exactly one ISP row carries a "★" — the one with the lowest `verified_rtt_ms` across all complete paths.
- [ ] ISPs with `path_complete = False` render in a distinct dimmed branch with a "⚠ incomplete" indicator and no RTT value.
- [ ] The `asn` subcommand JSON output is unchanged — `last_rtt_ms` remains present in the result dict with the same semantics as before.

## Implementation Phases

### Phase 1: Path Completeness Classification
**Scope:** Replace the `_extract_last_rtt` helper with `_classify_path`, which determines whether the traceroute reached the target ASN and identifies the last transit hop. Propagate the three new fields through `_run_test` and `summary_rows`. No display changes — this phase fixes the bug and adds the data that Phase 2 will render.
**Files:**
- `src/netpath/cli.py` — add `_classify_path(hubs, target_asn) -> dict`, remove `_extract_last_rtt`, update `_run_test` result dict to include `path_complete`, `verified_rtt_ms`, `entry_transit_asn`, keep `last_rtt_ms` populated for backward compatibility
**Verification:**
- [ ] Run `netpath country IL` (or simulate a path that stops before the target ASN) and confirm ISPs with no target-ASN hop in their traceroute have `path_complete = False` and `verified_rtt_ms = None` in their summary row
- [ ] Run `netpath asn AS15169 --json` and confirm the JSON output still includes `last_rtt_ms` with a non-None value when the path is reachable
- [ ] Run `netpath country US` and confirm that ISPs with a complete path have `path_complete = True` and `verified_rtt_ms` is the Avg RTT of the last hub inside the target ASN
**Estimated effort:** Small

### Phase 2: Tree Summary Display
**Scope:** Rewrite `country_summary` in `display.py` to render the grouped tree view with color-coded latencies, the star marker for the fastest verified path, and a footer line. Add `fmt_country_latency` for country-level color thresholds.
**Files:**
- `src/netpath/display.py` — rewrite `country_summary`; add `fmt_country_latency(ms: float) -> Text` using 120 ms / 200 ms thresholds; use indented `console.print` with tree-drawing characters or `rich.tree.Tree` for the branch structure
**Verification:**
- [ ] Run `netpath country IL` and confirm the summary groups ISPs under their transit entry point with indented branch headings
- [ ] Confirm color breakpoints: < 120 ms = green, 120–200 ms = yellow, > 200 ms = red, incomplete = grey dim
- [ ] Confirm "★" appears on exactly one ISP (the fastest verified); omitted when no complete paths exist
- [ ] Confirm incomplete ISPs render in a separate dimmed branch with "⚠ incomplete" and no RTT
- [ ] Confirm the footer line names the fastest entry transit and its RTT
**Estimated effort:** Small

## Edge Cases

- **No complete paths**: All ISPs are incomplete (all traceroutes stop at transit). Tree shows only the incomplete branch; star and footer are omitted.
- **Single-hop path**: Path has only one resolvable ASN (same as target). Treat as complete with `entry_transit_asn = None`; group under a "direct" branch heading.
- **Entry transit unresolvable**: Last transit hop is `AS???`. Group under "unknown transit" rather than crashing or discarding the row.
- **Tie for fastest RTT**: Multiple ISPs share the same minimum `verified_rtt_ms`. Star goes to whichever appears first in the sorted list.
- **All ISPs in one transit group**: Tree has only one branch — still renders the branch heading for consistency.
- **No entry transit IPs for name lookup**: The hub list contains no IPs for the transit hop (all `???`). Fall back to displaying the ASN code only; do not attempt a Cymru lookup with empty input.

## Technical Notes

Path completeness: compare each hub's `ASN` field to `target_asn`. Both should be normalized via `normalize_asn` from `asn.py` before comparison to avoid casing or prefix mismatches (e.g., "as12849" vs "AS12849").

Transit name resolution at summary time: collect the distinct `entry_transit_asn` values across all rows, then find one hub IP per transit ASN from the hubs lists stored in `summary_rows`. Run a single `cymru_bulk_lookup_rich` call (one TCP connection) on those IPs to get org names. If the lookup fails or a transit has no resolvable IP, fall back to the ASN code in the branch heading.

`fmt_latency` (thresholds 20 ms / 80 ms) must not be modified — it is used for per-hop tables in both subcommands. The new `fmt_country_latency` is country-summary-only.

For the tree structure: `rich.tree.Tree` is clean but adds visible connectors that may look noisy at narrow terminal widths. An alternative is manual indentation with `"  ├─ "` / `"  └─ "` characters via `console.print`. Either approach is acceptable; choose based on how it looks at 80-character width.

### Dependencies

None beyond existing dependencies (Rich 13+ and requests already in use).

## Implementation Notes

## Phase 1: Path Completeness Classification

**Files changed:** `src/netpath/cli.py`

**What was built:**

- Removed `_extract_last_rtt` helper. Its logic (last responsive hop regardless of ASN) is inlined directly in `_run_test` to preserve `last_rtt_ms` for backward compatibility.
- Added `_classify_path(hubs, target_asn) -> dict` returning `{complete, rtt_ms, entry_transit_asn}`. Normalizes ASN strings via `normalize_asn` before comparison to handle casing differences.
- `complete` is `True` only when `target_asn` appears in at least one hub's ASN field.
- `rtt_ms` is the Avg RTT of the last hub inside the target ASN when complete; `None` otherwise — the Binat fix.
- `entry_transit_asn` is the last distinct non-AS??? ASN before the target (complete) or the last resolvable ASN seen (incomplete).
- `_run_test` result dict gains `path_complete`, `verified_rtt_ms`, `entry_transit_asn`. `last_rtt_ms` still populated from inlined loop.
- The early-continue path in the `country` command (no test IP found) also gets the three new fields defaulted to `False`/`None`/`None`.
- `summary_rows` entries carry `path_complete`, `verified_rtt_ms`, `entry_transit_asn` via `**r` spread (or explicit defaults on the skip path).

**Deviations from plan:** None. `_extract_last_rtt` logic inlined rather than kept as a named helper — satisfies "remove _extract_last_rtt" while preserving `last_rtt_ms` backward compat.

## Phase 2: Tree Summary Display

**Files changed:** `src/netpath/display.py`

**What was built:**

- Added `from netpath.asn import cymru_bulk_lookup_rich, normalize_asn` at module level and `_IP_PAT` regex for IP detection.
- Added `fmt_country_latency(ms: float) -> Text` with 120 ms / 200 ms thresholds (green < 120 ms, yellow 120–200 ms, red >= 200 ms). Does not modify the existing `fmt_latency` (20 ms / 80 ms).
- Rewrote `country_summary` as a grouped tree view:
  - Separates complete rows (path_complete=True, verified_rtt_ms not None) from incomplete rows.
  - Groups complete rows by `entry_transit_asn`; sorts groups by best RTT ascending; sorts ISPs within each group by RTT.
  - Collects one IP per transit ASN from hub lists, runs a single `cymru_bulk_lookup_rich` batch call for org names. Falls back to ASN code if lookup fails or no IP is available.
  - Renders each group with `├─` / `└─` connectors, star prefix on the fastest ISP across all complete paths, and color-coded RTT via `fmt_country_latency`.
  - Incomplete paths render in a final dimmed branch with "⚠ incomplete" and no RTT.
  - Footer line names the fastest entry transit and its best ISP RTT. Omitted when no complete paths exist.
  - Edge cases: "direct" label for entry_transit_asn=None; ASN code fallback when Cymru name lookup fails; empty results → no output; all incomplete → no star or footer.

**Deviations from plan:** None.

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 2 files changed across 2 phases

Both phases are correctly implemented and all six acceptance criteria pass. The Binat RTT bug is fixed and the tree summary groups ISPs correctly by transit entry point with the right color thresholds, one star, and intact backward compatibility.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Module imports | PASS | Both cli.py and display.py import cleanly with PYTHONPATH=src |
| _classify_path unit tests | PASS | 5 scenarios: Binat incomplete, complete path RTT, single-hop direct, all-AS??? hops, case normalization |
| fmt_country_latency thresholds | PASS | 6 boundary values verified: <120ms=bold green, 120-199.9ms=yellow, >=200ms=bold red |
| country_summary rendering | PASS | Grouping, star placement, incomplete branch, footer all render correctly |
| Edge case coverage | PASS | All-incomplete (no star/footer), direct path (None transit → 'direct' label) |
| fmt_latency unchanged | PASS | Per-hop thresholds 20ms/80ms unmodified |
| Backward compat: last_rtt_ms | PASS | last_rtt_ms present in result dict init and set by inlined loop; asn JSON output unchanged |

### Acceptance Criteria (6/6 passed)

- [x] AC-1: Running `netpath country IL` with Binat reachable only via transit: Binat appears in the incomplete branch with no RTT, not in the ranked list with a sub-30 ms reading. (Verify by inspecting that `path_complete = False` for that row, or by reading the summary output.) — PASS: cli.py:55-59 — complete flag requires target_asn in at least one hub; transit-only paths return complete=False, rtt_ms=None. display.py:329 — rows with path_complete=False routed to incomplete list. Rendering test confirmed AS199524 in dimmed branch with no RTT.
- [x] AC-2: ISPs sharing the same `entry_transit_asn` are grouped together under one branch heading in the country summary. — PASS: display.py:337-338 — groups.setdefault(r.get('entry_transit_asn'), []) groups by transit ASN. display.py:385-395 — each group renders one heading then all ISPs under it. Rendering test with two ISPs under AS3257 confirmed single branch heading.
- [x] AC-3: A verified ISP with RTT < 120 ms shows the latency in green; 120–200 ms in yellow; > 200 ms in red. — PASS: display.py:34-40 — fmt_country_latency: <120 → bold green, <200 → yellow, else bold red. Six boundary-value tests (50, 119.9, 120, 199.9, 200, 300 ms) all produced the expected Rich style.
- [x] AC-4: Exactly one ISP row carries a '★' — the one with the lowest `verified_rtt_ms` across all complete paths. — PASS: display.py:333 — star_asn set to asn of min verified_rtt_ms row. display.py:391 — star prefix applied only when r['asn'] == star_asn. Rendering test with AS8551 (87ms) and AS5765 (142ms) found exactly one ★ on AS8551.
- [x] AC-5: ISPs with `path_complete = False` render in a distinct dimmed branch with a '⚠ incomplete' indicator and no RTT value. — PASS: display.py:397-406 — incomplete rows rendered with dim 'incomplete paths' heading, '⚠' in yellow, 'incomplete' in dim, and no RTT. Rendering test confirmed all three elements with no numeric RTT on the AS199524 row.
- [x] AC-6: The `asn` subcommand JSON output is unchanged — `last_rtt_ms` remains present in the result dict with the same semantics as before. — PASS: cli.py:156-194 — result dict initialized with last_rtt_ms:None; inlined reversed-hub loop sets it to the last responsive hop Avg regardless of ASN (same semantics as removed _extract_last_rtt). The JSON output blob in the asn subcommand (cli.py:350-378) does not include last_rtt_ms, matching pre-task behavior.

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- Preserve last_rtt_ms in the result dict alongside the new verified_rtt_ms — avoids breaking the asn subcommand's internal result contract while fixing the display bug for the country subcommand.
- Add fmt_country_latency as a new function rather than modifying fmt_latency — country-level ISP comparison uses different thresholds (120ms/200ms) than per-hop tables (20ms/80ms); keeping them separate avoids unintended side effects.
- Inline the last_rtt_ms loop in _run_test rather than retaining _extract_last_rtt as a named helper — satisfies the removal requirement while preserving backward compat without an extra private function.
- Use manual tree connectors (├─/└─) rather than rich.tree.Tree — cleaner at 80-char width; allows mixing colored RTT Text objects with plain prefixes on the same line.
- Import cymru_bulk_lookup_rich and normalize_asn at module level in display.py — no circular import risk; cleaner than deferred function-level imports.

## Required Changes

None.

## Release

## Release Notes

### What was built
- Fixed a latency reporting bug in the `country` subcommand where ISPs whose traceroute path never entered the target ASN (e.g. Binat/Internet Binat reaching only a transit router) were falsely assigned the transit router's RTT instead of being marked incomplete
- Added `_classify_path(hubs, target_asn)` helper in `cli.py` that determines path completeness by checking whether the target ASN appears in any traceroute hub, returning `complete`, `rtt_ms`, and `entry_transit_asn`
- Extended the `_run_test` result dict with three new fields (`path_complete`, `verified_rtt_ms`, `entry_transit_asn`) while preserving `last_rtt_ms` for backward compatibility with the `asn` subcommand
- Rewrote `country_summary` in `display.py` as a transit-grouped tree view with color-coded latency (green < 120 ms / yellow 120–200 ms / red >= 200 ms), a star marker on the fastest verified ISP, incomplete paths in a dimmed branch with a warning indicator, and a footer naming the fastest entry transit
- Added `fmt_country_latency` with country-level thresholds separate from the existing per-hop `fmt_latency` (20 ms / 80 ms)

### Key decisions
- Preserve `last_rtt_ms` in the result dict alongside the new `verified_rtt_ms` — avoids breaking the asn subcommand's internal result contract while fixing the display bug for the country subcommand
- Add `fmt_country_latency` as a new function rather than modifying `fmt_latency` — country-level ISP comparison uses different thresholds (120 ms / 200 ms) than per-hop tables (20 ms / 80 ms); keeping them separate avoids unintended side effects
- Inline the `last_rtt_ms` loop in `_run_test` rather than retaining `_extract_last_rtt` as a named helper — satisfies the removal requirement while preserving backward compat without an extra private function
- Use manual tree connectors (├─ / └─) rather than `rich.tree.Tree` — cleaner at 80-char width; allows mixing colored RTT Text objects with plain-text prefix on the same line
- Import `cymru_bulk_lookup_rich` and `normalize_asn` at module level in `display.py` — no circular import risk; cleaner than deferred function-level imports

### Changes by phase
- **Phase 1: Path Completeness Classification** — Replaced `_extract_last_rtt` with `_classify_path` in `cli.py`. ISPs that never reached the target ASN now have `verified_rtt_ms=None` and `path_complete=False`. `last_rtt_ms` preserved via inlined loop for backward compatibility.
- **Phase 2: Tree Summary Display** — Rewrote `country_summary` in `display.py` as a transit-grouped tree. Added `fmt_country_latency`, batched Cymru lookup for transit org names, star marker for fastest verified ISP, dimmed incomplete branch, and footer line.

## Verification

All 6 acceptance criteria passed in review (2026-06-30):
- Binat-style incomplete paths report no RTT and appear in the dimmed branch
- ISPs sharing the same `entry_transit_asn` group under one branch heading
- Color thresholds verified at boundary values (< 120 ms green, 120–200 ms yellow, > 200 ms red)
- Exactly one star on the ISP with the lowest `verified_rtt_ms`
- Incomplete branch renders with "⚠ incomplete" and no RTT
- `last_rtt_ms` preserved in result dict; `asn` subcommand JSON output unchanged

