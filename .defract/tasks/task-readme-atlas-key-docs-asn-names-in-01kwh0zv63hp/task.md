---
defract:
  id: task-readme-atlas-key-docs-asn-names-in-01kwh0zv63hp
  type: improvement
  status: active
  stage: review
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

# README atlas-key docs + ASN names in trace/AS-path display

# README atlas-key docs + ASN names in trace/AS-path display

# README atlas-key docs + ASN names in trace/AS-path display

# README atlas-key docs + ASN names in trace/AS-path display

# README atlas-key docs + ASN names in trace/AS-path display

# README atlas-key docs + ASN names in trace/AS-path display

## What We're Building

Four improvements: (1) README documentation for the undocumented `--atlas-key` / `NETPATH_ATLAS_KEY` option and `--globe` flag; (2) ASN org name enrichment so the trace table and AS path summary show `AS209 (Lumen)` instead of bare numbers; (3) RIPE Atlas anchor support — fall back to Atlas anchors when no volunteer probes exist in a target ASN, eliminating the "no probes found" failure for sparsely-probed countries; (4) a new `netpath atlas-profile` standalone subcommand that queries probe and anchor counts for every country, producing a ranked table and optional globe visualization showing where Atlas coverage is richest.

## Expected Outcome

- The README contains a "RIPE Atlas" section covering key supply, credit cost, and what output looks like when measurements run vs when no probes or anchors are found
- The country command's options block in the README lists `--atlas-key` and `--globe`
- When no volunteer probes exist in a target ASN, the tool queries for Atlas anchors and uses them as measurement sources; anchor-sourced measurements are labeled `[Atlas anchor]` in output
- `netpath atlas-profile` is a standalone subcommand that queries Atlas for probe and anchor counts by country, producing a ranked table showing coverage richness across the globe
- The atlas profile output can be rendered on the existing 3D globe visualization, with countries colored or sized by probe + anchor density
- The traceroute hop table's ASN column shows `AS209 (Lumen)` style entries
- The AS path summary shows named ASNs, e.g. `AS209 (Lumen) → AS3356 (Level 3) → ...`
- ASN names appear in `--json` output per hub

## Phase Outcomes

- **Phase 1: Show organization names everywhere ASNs appear** — Builders reading a traceroute no longer need to look up what each AS number belongs to. The organization name appears alongside the number in both the hop-by-hop table and the AS path summary, making paths readable at a glance. The same names appear in `--json` output so downstream tooling can consume them.
- **Phase 2: Recover from sparse Atlas coverage with anchor fallback** — When a target ISP has no RIPE Atlas volunteer probes deployed, netpath no longer returns a silent failure. It automatically falls back to Atlas anchor nodes in that network, completes the measurement, and notes in the output that anchors were used. Users probing smaller or regional ISPs get results instead of gaps.
- **Phase 3: Atlas coverage profile command and full documentation** — A new `netpath atlas-profile` command gives builders a ranked view of which countries have the richest Atlas coverage, helping them plan where Atlas-based measurements will succeed. Countries can be explored on the 3D globe. README documentation makes the Atlas feature discoverable for first-time users.

## Out of Scope

- Using the pre-existing anchor mesh measurements (`GET /anchor-measurements/`) — those reflect anchor-to-anchor paths, not the user's path
- Adding a bare `--atlas` boolean flag or changing how `--atlas-key` parses its argument
- Per-ASN breakdown within the atlas profile (country-level granularity is sufficient for the coverage map)

## Scope Summary

**Size:** 17 requirements, 12 acceptance criteria, 3 implementation phases
**Key decisions:**
- Reuse the existing `cymru_bulk_lookup_rich()` batch call for org name enrichment — no new external dependency
- Atlas anchor fallback submits anchor IDs through the identical scheduling/polling path as regular probe IDs
- `atlas-profile` fetches all active probes in a single paginated sweep to build the country count table
**Biggest risk:** Atlas API pagination for `atlas-profile` — with ~13,000 active probes at 500 per page, a slow or rate-limited Atlas API makes the command noticeably slow; the implementation should show progress and handle partial responses gracefully.

## Context

`netpath` already integrates with RIPE Atlas in `atlas.py` (probe discovery, measurement scheduling, ping/traceroute result parsing). The Atlas feature is exposed via `--atlas-key` on the `country` subcommand but is entirely undocumented in the README. ASN org name lookup already exists as `cymru_bulk_lookup_rich()` in `asn.py`, and a `clean_asn_name()` helper exists in `display.py`, but neither is wired into the trace display or AS path summary. The `Hub` TypedDict in `types.py` has no `asn_name` field today. The `globe.py` module renders an interactive 3D globe from existing lat/long data; it will need to accept country-level density data for the atlas-profile visualization.

## Requirements

### ASN Organization Name Display

- R1: The hop-by-hop trace table's ASN column shows the organization name alongside the ASN number in the format `AS209 (Lumen)`. The name portion is truncated to a reasonable column width (≤20 characters) to keep the table from wrapping. (`display.path_table()` in `display.py`.)
- R2: The AS path summary line shows named ASNs: `AS1234 (ISP A) → AS5678 (ISP B) → AS9999 (ISP C)`. (`display.as_path_summary()` in `display.py`.)
- R3: Each hub entry in `--json` output includes an `asn_name` field alongside the existing `ASN` field. (`asn_name` added to `Hub` TypedDict in `types.py`; populated in `mtr.py`.)
- R4: Name enrichment uses `cymru_bulk_lookup_rich()` in `asn.py` via a single batch call on all unique non-`***` IPs in the hubs list — no new external service or dependency.
- R5: When a hop's IP has no Cymru record, or the hop is `***`, the ASN column falls back gracefully to showing the bare ASN number with no parenthetical and no crash.
- R6: Atlas-sourced traceroute AS path results (`atlas.parse_traceroute_as_path()`) include org names in the returned path strings so the named format appears consistently across both local-mtr and Atlas-measured paths.

### Atlas Anchor Fallback

- R7: When `find_probes_in_asn()` returns zero probes for a target ASN during a country sweep, the tool automatically queries the RIPE Atlas anchors endpoint for anchors in that ASN. (`find_anchors_in_asn()` added to `atlas.py`.)
- R8: Anchor probe IDs retrieved by the fallback are submitted through the existing `schedule_measurements()` / `poll_until_done()` / `parse_*` pipeline unchanged — no parallel code path for anchor measurements.
- R9: When anchors are used, each measurement result is tagged so that the country sweep table and `--json` output include a `source: "atlas_anchor"` or equivalent label.
- R10: The country sweep table row for an anchor-sourced ASN renders a visible `[Atlas anchor]` annotation so the user knows the measurement came from an anchor, not a volunteer probe.
- R11: When neither volunteer probes nor anchors exist for a target ASN, the tool reports "no Atlas coverage" for that ASN and moves to the next — the same graceful skip behavior as the current "no probes found" path.

### Atlas Coverage Profile Command

- R12: A new `netpath atlas-profile` Typer subcommand is registered in `cli.py`. It accepts `--atlas-key` (also read from `NETPATH_ATLAS_KEY`) and `--top N` (default 20) and `--globe` (flag).
- R13: The command paginates through the Atlas `/api/v2/probes/` endpoint (status=1, minimal fields) to build a per-country probe count, then similarly through `/api/v2/anchors/` for anchor counts.
- R14: Results are displayed as a ranked Rich table with columns: rank, country code, country name, probe count, anchor count, total. Sorted descending by total. `--top N` limits rows shown.
- R15: With `--globe`, the command renders the 3D globe (via `globe.py`) with countries shaded by probe+anchor density using a choropleth layer. Countries with zero coverage are shown in a neutral color.
- R16: `atlas-profile` exits with a clear error message and non-zero exit code when `--atlas-key` is absent and `NETPATH_ATLAS_KEY` is not set.

### README Documentation

- R17: README gains a "RIPE Atlas" section (under the existing "Usage" or as a top-level section) covering: what an Atlas key is, where to obtain a free account, how to set `NETPATH_ATLAS_KEY`, approximate credit cost per measurement, example terminal output for a successful Atlas run, and the "no probes or anchors found" case.
- R18: The README documents `netpath atlas-profile` with a one-line description, usage example (`netpath atlas-profile --top 10`), and sample output showing the ranked table.
- R19: The `country` command's option reference in the README lists `--atlas-key KEY` and `--globe` with brief descriptions alongside the existing options.

## Acceptance Criteria

- [ ] Running `netpath asn AS15169` produces a trace table where the ASN column shows `AS15169 (Google)` — verified by inspecting terminal output or running with `--json` and confirming `asn_name` is populated in hub entries.
- [ ] The AS path summary line on any trace contains org names in the `AS{N} (Name) →` format, not bare AS numbers.
- [ ] `netpath asn AS15169 --json 2>/dev/null | python -m json.tool | python -c "import sys,json; hubs=json.load(sys.stdin)['hubs']; assert all('asn_name' in h for h in hubs if h.get('ASN','').startswith('AS') and not h['ASN'].startswith('AS???'))"` exits 0.
- [ ] A hop with no Cymru record or a `***` hop renders without error; the ASN column shows the bare ASN number or `—` with no crash.
- [ ] When `find_probes_in_asn()` returns an empty list for a target ASN in a country sweep (mockable in tests), `find_anchors_in_asn()` is called and its results are passed to the scheduling function.
- [ ] Country sweep output for an ASN served by anchor fallback shows `[Atlas anchor]` in the results row for that ASN.
- [ ] When both probes and anchors are absent for an ASN, the country sweep continues to the next ASN and reports "no Atlas coverage" for the skipped one.
- [ ] `netpath atlas-profile --atlas-key <key> --top 5` renders a ranked table with at least 5 rows and columns for probe count, anchor count, and total.
- [ ] `netpath atlas-profile --atlas-key <key> --globe` completes without raising an exception and opens (or saves) a globe visualization.
- [ ] `netpath atlas-profile` (no key, no env var) exits with a non-zero code and prints a message directing the user to obtain an Atlas key.
- [ ] README contains a "RIPE Atlas" section that documents `NETPATH_ATLAS_KEY`, `--atlas-key`, credit cost, and `netpath atlas-profile`.
- [ ] `pytest` passes after all phases.

## Implementation Phases

### Phase 1: ASN org name enrichment
**Scope:** Enrich every trace hop with the organization name behind its ASN, and wire those names into the hop table, AS path summary, and JSON output. No new external lookups — the existing Cymru batch call is extended to the rich variant.
**Files:**
- `src/netpath/types.py` — add optional `asn_name: str` field to `Hub` TypedDict
- `src/netpath/mtr.py` — after building hubs list in both mtr and traceroute paths, batch-call `cymru_bulk_lookup_rich()` on unique non-`***` IPs; populate `hub["asn_name"]` from result `name` field via `clean_asn_name()`
- `src/netpath/atlas.py` — switch `parse_traceroute_as_path()` to use `cymru_bulk_lookup_rich()` and return formatted strings like `"AS1234 (Name)"` instead of bare ASN strings
- `src/netpath/display.py` — update `path_table()` to render `hub.get("asn_name")` after the ASN number (truncated to ≤20 chars); update `as_path_summary()` to show `AS{N} (Name)` format for each hop
**Verification:**
- `netpath asn AS15169` trace table ASN column shows `AS15169 (Google)` format
- `netpath asn AS15169 --json 2>/dev/null` hub entries contain `asn_name` field
- AS path summary line shows named format
- A hop with `***` or unresolved ASN renders cleanly with no crash
- `pytest` passes
**Estimated effort:** Medium

### Phase 2: Atlas anchor fallback
**Scope:** When a target ASN has no volunteer probes, automatically fall back to querying for Atlas anchor nodes and use them as measurement sources. Label anchor-sourced results so users can distinguish them from volunteer-probe results.
**Files:**
- `src/netpath/atlas.py` — add `find_anchors_in_asn(asn_number: int, api_key: str) -> list[int]` calling `GET /api/v2/anchors/?asn_v4={asn}&page_size=100&status=1`; add a return value or flag to distinguish anchor vs probe source
- `src/netpath/cli.py` — in the country sweep loop, after `find_probes_in_asn()` returns empty, call `find_anchors_in_asn()`; pass found anchor IDs to `schedule_measurements()`; annotate the result row with `source: "atlas_anchor"` when anchors were used
- `src/netpath/display.py` — in the country sweep table renderer, show `[Atlas anchor]` annotation in the result row when `source == "atlas_anchor"`
**Verification:**
- Mocking `find_probes_in_asn` to return `[]` and `find_anchors_in_asn` to return a non-empty list causes measurement to proceed (verify by inspecting cli.py logic or a lightweight integration test)
- Country sweep terminal output for an anchor-served row shows `[Atlas anchor]`
- When both return `[]`, the row shows "no Atlas coverage" and the sweep continues
- `pytest` passes
**Estimated effort:** Small

### Phase 3: Atlas coverage profile command and README documentation
**Scope:** Add a standalone `netpath atlas-profile` subcommand that maps Atlas probe and anchor density by country, with optional globe visualization. Document the complete RIPE Atlas feature surface in the README.
**Files:**
- `src/netpath/atlas.py` — add `fetch_coverage_by_country(api_key: str) -> dict[str, dict]` that paginates `GET /api/v2/probes/?status=1&fields=country_code&page_size=500` and `GET /api/v2/anchors/?status=1&fields=country_code&page_size=200` to build `{country_code: {probes, anchors}}` dict; show a Rich progress spinner during the fetch
- `src/netpath/cli.py` — register `atlas_profile` Typer command; accept `--atlas-key`, `--top` (default 20), `--globe`; render ranked Rich table; call `globe.render_coverage()` when `--globe` is set
- `src/netpath/globe.py` — add `render_coverage(coverage: dict[str, int])` function that renders a choropleth globe using plotly with countries shaded by probe+anchor total density
- `README.md` — add "RIPE Atlas" section with account/key setup, `NETPATH_ATLAS_KEY`, credit cost, example output; add `netpath atlas-profile` usage; add `--atlas-key` and `--globe` to country command option reference
**Verification:**
- `netpath atlas-profile --atlas-key <key> --top 5` renders a 5-row ranked table with probe, anchor, and total columns
- `netpath atlas-profile --atlas-key <key> --globe` opens globe without exception
- `netpath atlas-profile` (no key) exits non-zero with a helpful message
- README contains "RIPE Atlas" section and `netpath atlas-profile` usage example
- `pytest` passes
**Estimated effort:** Large

## Edge Cases

- **`***` hops:** No IP available; skip in the Cymru batch call and leave `asn_name` absent; display renders `—` as today.
- **Very long org names:** Truncate display to ≤20 characters in table column; full name still emitted in `--json` via `asn_name`.
- **Same ASN appearing multiple consecutive hops:** AS path summary deduplicates as today; name lookup is by IP so even duplicate ASNs get correct names from their respective IPs.
- **Atlas API rate limit during atlas-profile fetch:** Wrap pagination in `_with_retry()` helper from `utils.py`; on repeated failure, emit a warning and return a partial result rather than crashing.
- **Country with zero Atlas coverage in atlas-profile:** Render `0 / 0 / 0` row in table; globe shows country in neutral color, no crash.
- **Atlas key valid but no credits:** Atlas will return an error on `schedule_measurements()`; the existing error-handling path surfaces this; no change needed for this edge case.
- **`find_anchors_in_asn` returns anchors for a different ASN** (misconfigured ASN param): anchor IDs are submitted as-is; measurements may show unexpected AS path; no special handling needed.

## Technical Notes

`cymru_bulk_lookup_rich()` (`asn.py` lines 77–113) returns `{ip: {asn, prefix, name}}` where `name` is already trimmed to the first comma-segment (e.g., `"GOOGLE"` from `"GOOGLE - Google LLC, US"`). The existing `clean_asn_name()` in `display.py` (lines 23–36) applies further cosmetic trimming and is the right place to do final truncation before rendering. Call `clean_asn_name()` on the Cymru `name` value when populating `asn_name` in hubs.

For mtr mode, mtr's `--aslookup` already populates `hub["ASN"]` — the Cymru rich call is still needed to get the org name and may return a redundant ASN value; use the Cymru ASN only as a fallback if `hub["ASN"]` is `AS???`.

The RIPE Atlas anchors endpoint is `GET https://atlas.ripe.net/api/v2/anchors/?asn_v4={asn_number}&status=1&page_size=100`. Note that `asn_v4` takes a bare integer (e.g., `15169`), not the `AS15169` string form. `asn.normalize_asn()` already handles stripping the `AS` prefix if needed.

For `atlas-profile`, pagination terminates when `next` in the API response is `null`. Store only `country_code` per record to keep memory usage flat across ~13K probes.

`globe.py` currently renders lat/long scatter points via plotly; adding a choropleth layer (`go.Choropleth`) with ISO-3166-1 alpha-2 country codes and a `z` value (probe+anchor count) is straightforward alongside the existing globe trace. Use a log scale for the color axis to avoid high-density countries (US, Germany) washing out mid-density ones.

The `atlas-profile` command does not require a credit budget check — it only reads data from the Atlas API, never schedules measurements.

### Dependencies

No new runtime dependencies. All network calls use the existing `requests`-based `_with_retry()` helper from `utils.py`. Globe visualization reuses `plotly` which is already a transitive dependency via `globe.py`.

## Implementation Notes

## Phase 3: Atlas Profile Command + README

### Files Changed

- `src/netpath/atlas.py` — added `fetch_coverage_by_country(api_key)`: paginates `/api/v2/probes/` and `/api/v2/anchors/` with Rich spinners, returns `{cc: {"probes": int, "anchors": int}}`.
- `src/netpath/globe.py` — added `_A2_TO_A3` (ISO alpha-2 → alpha-3 dict, ~240 entries), `_build_coverage_html` (plotly.js choropleth via CDN, log-scale z-values, orange gradient), `render_coverage(coverage)` (writes temp HTML, opens browser).
- `src/netpath/cli.py` — added `_COUNTRY_NAMES` dict (~240 entries), `atlas_profile` command (`atlas-profile` subcommand) with `--atlas-key`, `--top`, `--globe` options; displays Rich rounded table ranked by total probes+anchors.
- `README.md` — added `### Atlas coverage profile` usage section with sample table output; added `## RIPE Atlas` section covering Atlas overview, key setup, credit cost, output labels (`[Atlas]` / `[Atlas anchor]`), and `atlas-profile` cross-reference; updated country command options to include `--atlas-key` and `--globe`.

### Deviations from Plan

None. All items in the phase spec were implemented as specified.

### Test Results

75 passed, 0 failed.
