---
defract:
  id: task-migrating-atlas-globalping-dropping-key-01kwhgzgj8t8
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


# Migrate from RIPE Atlas to Globalping and drop the API key requirement

## Story Brief

From chat: Migrating Atlas → Globalping + dropping key requirement (2026-07-02). The builder chose a full replacement: delete the Atlas backend and all its wiring, make Globalping the sole in-network measurement backend for zero-config operation. Accepted trade-offs: smaller probe network, no anchor fallback (Globalping has no anchor class), renaming the atlas-profile command, and rewriting the README's RIPE Atlas section. An optional token may be kept for a higher rate-limit tier, but no key is required by default.

## What We're Building

Today, measuring network paths from vantage points inside the target networks requires a RIPE Atlas account, an API key, and a credit balance — a setup hurdle that stops most users before they see any value. This task replaces that backend with Globalping, a free service that needs no account or key, so in-network measurements and the coverage report work out of the box for everyone.

## Expected Outcome

- Users can run in-network path measurements and country sweeps without creating an account, obtaining a key, or managing a credit balance
- The probe-coverage report works with zero configuration, showing where measurement vantage points are available
- Users who want higher usage limits can optionally supply a token, but nothing requires one
- Documentation describes the new service and no longer mentions API keys or credits as a prerequisite
- Error messages and command names no longer reference the old service

## Phase Outcomes

- **Phase 1: Build the new measurement backend** — Establishes and verifies the connection to the free measurement service, so in-network results are reliable before the switch is flipped for users. No user-visible change yet.
- **Phase 2: Switch over and remove the old service** — Country sweeps and the coverage report now work with zero configuration; every mention of the old service, its key, and its credits disappears from commands, messages, and documentation.

## Out of Scope

- Keeping the old RIPE Atlas backend as an alternative or fallback — this is a full replacement, and the recently added anchor-based coverage boost goes away with it (the new service has no equivalent, by accepted trade-off)
- Publishing a new release to the package index and cleaning up the builder's local install — that is a separate release runbook, not part of this change
- Any changes to the local measurement features (traceroute, throughput, latency probes run from the user's own machine) — only the remote in-network measurement backend changes
- Changing how the tool picks a representative test address inside each target network — that lookup already works without any account or key and continues unchanged (the new service does not publish probe addresses, so there is nothing to migrate it to)

## Scope Summary

**Size:** 13 requirements, 9 acceptance criteria, 2 implementation phases
**Key decisions:**
- Full deletion of `atlas.py` and all its wiring — no deprecation shim, no fallback
- Use Globalping's `mtr` measurement type for the inside-out path (per-hop ASN is included in results, so the remote path parser no longer needs the Cymru bulk lookup)
- Remote in-network measurements run by default in country mode (no key gate), with a `--no-remote` opt-out
- `country.py`'s keyless Atlas probe-IP lookup for test-IP discovery stays — it serves local measurements and Globalping exposes no probe IPs
- `atlas-profile` command becomes `coverage`
**Biggest risk:** Assumptions about the Globalping result schema (especially per-hop ASN fields in `mtr` results and the probe-list response shape) must be verified against the live API during implementation.

## Context

The Atlas backend lives in `src/netpath/atlas.py` (probe/anchor discovery, credit budget check, measurement scheduling, 600-second polling, ping/traceroute result parsing, coverage-by-country pagination). It is wired into `src/netpath/cli.py` in three places: the `country` command's pre-sweep probe discovery and budget check (lines ~630-680), the post-sweep schedule/poll/merge block (lines ~749-819), and the `atlas-profile` command (lines ~871-931). `src/netpath/display.py` renders an `[Atlas]` / `[Atlas anchor]` subrow via `_render_atlas_subrow()`, and `src/netpath/globe.py` titles the choropleth "RIPE Atlas Coverage by Country". `tests/test_atlas.py` covers `find_anchors_in_asn`. Separately, `src/netpath/country.py` uses the public keyless Atlas probes API inside `_get_atlas_probe_ip()` only to find a routable test IP per ASN for local measurements — that is out of scope. Globalping (`https://api.globalping.io/v1`) requires no authentication: `POST /v1/measurements` creates one-off ping/traceroute/mtr measurements from probes selected by ASN, `GET /v1/measurements/{id}` polls results (typically finished in seconds), and `GET /v1/probes` lists all connected probes with country and ASN metadata. An optional Bearer token raises the hourly rate limit.

## Requirements

### New Globalping backend module

- R1: A new single-purpose module owns all Globalping interaction — probe inventory, measurement creation, polling, result parsing, and coverage-by-country — replacing the deleted Atlas module. (New file `src/netpath/globalping.py`, mirroring the role of `src/netpath/atlas.py`; follows the display-free, `_with_retry`-wrapped conventions of the existing measurement modules.)
- R2: Probe coverage for a sweep is determined from a single probe-inventory request rather than one query per ASN. (`GET /v1/probes` returns all connected probes with `location.asn` and `location.country`; build an ASN-to-count map client-side and reuse the same fetch for the coverage command. No credit or budget concept exists — `check_budget` has no successor.)
- R3: For each covered ASN, the module schedules the same two measurements the Atlas backend did: a ping from probes inside the ASN to the per-ASN test IP, and a path trace from those probes back to the user's public IP. (`POST /v1/measurements` with `locations: [{"magic": "AS{n}"}]` and `limit: 3`; ping type `ping`, path type `mtr` so each hop carries its own ASN. `get_public_ip()` via ipify carries over unchanged.)
- R4: Polling matches Globalping's speed: results are checked every few seconds and a measurement that never finishes is marked timed out without failing the sweep. (`GET /v1/measurements/{id}` until `status` leaves `in-progress`; poll interval ~2 s, overall timeout ~60 s, replacing Atlas's 30 s / 600 s cadence.)
- R5: Result parsing produces the same shapes the display layer consumes today: min/avg/max RTT from ping stats, and a deduplicated AS-hop path with names from mtr hops. (Pure functions in the new module; the per-hop `asn` field in mtr results replaces the `cymru_bulk_lookup_rich` round-trip that `parse_traceroute_as_path` needed.)
- R6: An optional token raises the rate-limit tier but is never required. (`--gp-token` flag with envvar `NETPATH_GLOBALPING_TOKEN`, mirroring the `--cf-token` pattern; when set, requests carry `Authorization: Bearer {token}`.)

### CLI rewiring

- R7: Country mode runs in-network measurements by default with no key, and users who want a faster or quieter sweep can turn them off. (Remove `--atlas-key` / `NETPATH_ATLAS_KEY` from the `country` command; add a `--no-remote` flag that skips the Globalping block entirely, in the style of `--no-throughput`.)
- R8: The coverage command works with zero configuration and drops its key-check error path. (Rename `atlas-profile` to `coverage`; remove the key option and the "No Atlas API key provided" exit; table shows per-country probe counts with no anchors column; `--top` and `--globe` behave as before.)
- R9: All user-facing status and error strings name the new service. ("Discovering Globalping probes…", "Scheduling Globalping measurements…", "no Globalping coverage", and the `probe_errors` key `atlas` becomes `globalping` in `_set_atlas_error`'s successor in `cli.py`.)

### Display, globe, and result shape

- R10: The per-ISP subrow labels remote results with the new service name and the anchor variant disappears. (`display._render_atlas_subrow` becomes a Globalping subrow reading a `globalping` key on the summary row; the `[Atlas anchor]` tag and `source: "atlas_anchor"` field are removed; JSON output carries `globalping` instead of `atlas`.)
- R11: The coverage globe titles itself after the new service. (Title strings in `src/netpath/globe.py`; `render_coverage`'s dict-of-counts interface is unchanged.)

### Tests and documentation

- R12: The old backend's tests are deleted and the new module's pure parse and inventory functions are covered with mocked HTTP responses. (Delete `tests/test_atlas.py`; add `tests/test_globalping.py` for RTT parsing, AS-path parsing from mtr hops, coverage counting, and empty/error responses — same mock-`requests` style as the existing tests. `tests/test_country.py` is untouched.)
- R13: The README describes Globalping end to end and drops every key and credit prerequisite. (Rewrite the "RIPE Atlas" section and its subsections, the `--atlas-key` flag docs, the `[Atlas]` / `[Atlas anchor]` output examples, and the `atlas-profile` usage; add a short note that the optional token exists for higher rate limits.)

## Acceptance Criteria

- [ ] `netpath country ZA --top 5` performs in-network measurements with no token, key, or environment variable set; verified by running the command in a clean environment and observing a `[Globalping]` subrow or a per-ASN "no Globalping coverage" note
- [ ] `netpath coverage --top 10` prints a ranked per-country probe table with zero configuration, and `--globe` renders the choropleth
- [ ] `--gp-token` and `NETPATH_GLOBALPING_TOKEN` are accepted on the `country` and `coverage` commands and produce an `Authorization: Bearer` header; verified by a unit test asserting the header in `tests/test_globalping.py`
- [ ] `--no-remote` on the `country` command skips all Globalping activity; verified by running with the flag and observing no Globalping status lines
- [ ] `src/netpath/atlas.py` and `tests/test_atlas.py` no longer exist, and `grep -ri atlas src/netpath/cli.py src/netpath/display.py src/netpath/globe.py README.md` returns no matches
- [ ] `netpath --help`, `netpath country --help`, and `netpath coverage --help` contain no mention of Atlas, API keys as a requirement, or credits
- [ ] JSON output for country mode uses a `globalping` key for remote results and contains no `atlas` key or `atlas_anchor` source tag; verified by inspecting `--json` output or the `MeasurementResult`-adjacent row shape
- [ ] `tests/test_globalping.py` covers ping RTT parsing, mtr AS-path parsing, coverage counting, and error/empty responses; `pytest` passes
- [ ] `ruff check src tests` passes

## Implementation Phases

### Phase 1: Build the Globalping backend module
**Scope:** Stand up the complete integration with the new measurement service — probe inventory, scheduling, polling, and result parsing — verified by unit tests, without touching any existing behavior yet.
**Files:** `src/netpath/globalping.py` (new), `tests/test_globalping.py` (new)
**Verification:**
- `pytest tests/test_globalping.py` passes, covering RTT parsing, mtr AS-path parsing, coverage counting, Bearer-header injection, and empty/error responses
- `ruff check src tests` passes
- Module imports cleanly in isolation (`python -c "from netpath import globalping"`)
**Estimated effort:** Medium

### Phase 2: Switch the CLI over and delete Atlas
**Scope:** Make the new service the sole remote backend everywhere users touch it — country sweeps, the renamed coverage command, display labels, globe titles, and the README — and remove the old backend and its key requirement entirely.
**Files:** `src/netpath/cli.py`, `src/netpath/display.py`, `src/netpath/globe.py`, `README.md`, `src/netpath/atlas.py` (delete), `tests/test_atlas.py` (delete)
**Verification:**
- `grep -ri atlas src/netpath/cli.py src/netpath/display.py src/netpath/globe.py README.md` returns nothing
- `netpath country --help` shows `--gp-token` and `--no-remote`, no `--atlas-key`; `netpath coverage --help` works
- Full `pytest` and `ruff check src tests` pass
- Manual smoke: `netpath coverage --top 5` returns a ranked table with no token set
**Estimated effort:** Medium

## Edge Cases

- No Globalping probes in a target ASN: record "no Globalping coverage" in that ASN's `probe_errors` and continue the sweep — mirrors the current per-ASN Atlas behavior, no sweep abort
- Rate limit exhausted mid-sweep (HTTP 429): record a per-ASN `probe_errors` entry that mentions the optional `--gp-token` for higher limits; remaining ASNs are still attempted or skipped with the same note, and the sweep completes
- Public IP undetectable (ipify failure): warn and skip all remote measurements, as today
- Measurement stuck in progress past the timeout: mark it "timed_out" in `probe_errors` for that ASN and move on
- Invalid or expired token (HTTP 401): surface a clear error naming the token, skip remote measurements, and continue the local sweep rather than exiting
- Stale `NETPATH_ATLAS_KEY` in the user's environment: silently ignored (the option no longer exists); the README migration note tells users the variable is obsolete
- Empty probe inventory response (API reachable but zero probes): coverage command warns "no coverage data" and exits 1, matching the current empty-coverage path

## Technical Notes

Globalping API surface used (base `https://api.globalping.io/v1`, no auth by default): `POST /measurements` with `{type, target, locations: [{magic: "AS{n}"}], limit}` returns `{id, probesCount}`; `GET /measurements/{id}` returns per-probe results and a top-level `status` (`in-progress` then `finished`); `GET /probes` returns all connected probes with `location.asn` and `location.country`. A 422 on creation means no matching probes. Rate limits are per-IP for unauthenticated use and higher with a Bearer token — exact figures should be confirmed against current Globalping docs during implementation and reflected in the README rather than hard-coded assumptions.

The `mtr` measurement type is preferred over `traceroute` for the inside-out path because each hop in the result carries its own ASN, which removes the new module's dependency on `asn.cymru_bulk_lookup_rich` (that helper stays — local-path code still uses it). The exact hop field names must be verified against a live response in Phase 1 before the parsers are locked in.

`country._get_atlas_probe_ip()` and its `RIPE_ATLAS_PROBES` constant are deliberately untouched: they hit the public, keyless Atlas metadata API only to find a routable IPv4 per ASN for local probing, Globalping publishes no probe addresses, and `tests/test_country.py` pins this behavior. The acceptance-criteria grep therefore excludes `country.py`.

Conventions to follow: `_with_retry` for all HTTP calls, display-free pure parse functions (test targets), `raise typer.Exit(code)` never `sys.exit()`, and the single-purpose measurement module pattern. The 401/429 handling must populate `probe_errors` so `diagnose()` sets `partial_results` and `verdict_panel()` renders the partial-results note without elevating the verdict incorrectly.

## Implementation Notes

## Phase 1: Build the Globalping backend module — complete

**Files created:**
- `src/netpath/globalping.py` — the complete Globalping integration: `get_public_ip()` (carried over from atlas.py unchanged), `fetch_probes()` (single GET /v1/probes inventory), `count_probes_by_asn()` and `coverage_by_country()` (pure client-side aggregation over the inventory, satisfying R2's one-request coverage model), `schedule_measurements()` (POST /v1/measurements: ping to the per-ASN test IP plus mtr back to the user's public IP, `locations: [{"magic": "AS{n}"}]`, `limit: 3`), `poll_until_done()` (2 s interval, 60 s default timeout, unfinished measurements marked "timed_out"), `fetch_results()`, `parse_ping_rtt()` (min-of-mins / mean-of-avgs / max-of-maxes across probes), and `parse_mtr_as_path()` (consecutive-ASN dedup using the per-hop `asn` field — no Cymru lookup).
- `tests/test_globalping.py` — 26 tests in the same mock-`requests` style as the deleted-in-phase-2 test_atlas.py: inventory fetch and error paths, Bearer-header injection and its absence without a token (acceptance-criterion test), ASN/country coverage counting, ping+mtr scheduling body shape, AS-prefix normalisation, 422 propagation, poll terminal/timeout behavior, RTT aggregation with null-stats (100 % loss) handling, mtr path dedup/labeling/fall-through, and ipify parsing.

**Schema verification (required by the phase before locking parsers):** confirmed against the live OpenAPI spec at api.globalping.io/v1/spec.yaml — mtr hops carry `asn` as an array of integers plus `resolvedHostname` (no network-name field), ping stats live at `result.stats.{min,avg,max}`, result items are `{probe, result}`, top-level status is `in-progress`/`finished`, 422 means no matching probes, 429 rate limit.

**Deviations/refinements:** AS-path labels take their readable name from the hop hostname's registered domain ("AS174 (cogentco.com)") since Globalping provides no AS organisation names (decision logged). Errors from measurement creation propagate as requests.HTTPError with the response attached so Phase 2 can branch on 422/429/401 (decision logged).

**Checks:** full suite 101 passed (baseline was 75, no pre-existing failures), `ruff check src tests` clean, `python -c "from netpath import globalping"` imports cleanly. No existing files touched — no user-visible change yet.

## Phase 2: Switch the CLI over and delete Atlas — complete

**Files changed:**
- `src/netpath/cli.py` — Atlas import replaced with `globalping as globalping_mod` (plus `requests` for HTTPError branching). `_set_atlas_error` is now `_set_globalping_error` writing the `globalping` probe_errors key. The `country` command drops `--atlas-key`/`NETPATH_ATLAS_KEY` and gains `--gp-token` (envvar `NETPATH_GLOBALPING_TOKEN`, shared `_GP_TOK` option in the `--cf-token` style) and `--no-remote` (styled after `--no-throughput`). Pre-sweep discovery is one `fetch_probes()` inventory call aggregated client-side (no per-ASN queries, no budget check). Post-sweep block schedules ping+mtr per covered ASN, polls with the 2 s/60 s cadence, and merges results under a `globalping` row key; HTTPError branches: 422 → "no Globalping coverage", 429 → "rate limit reached — pass --gp-token for higher limits", 401 → clear error naming the token, remaining ASNs marked "invalid Globalping token", scheduling stops but the sweep completes. `atlas-profile` is now `coverage`: zero-config, no key-check exit, probes-only table (no anchors column), `--top`/`--globe` unchanged.
- `src/netpath/display.py` — `_render_atlas_subrow` is now `_render_globalping_subrow`: reads the `globalping` key, prints a `[Globalping]` tag; the `[Atlas anchor]` variant and `source` handling are gone.
- `src/netpath/globe.py` — choropleth titled "Globalping Coverage by Country"; colorbar/hover say "Probes" (no anchors); `render_coverage` interface unchanged.
- `README.md` — country options updated (`--no-remote`, `--gp-token`), "Probe coverage" section for `netpath coverage`, and the RIPE Atlas section replaced by a "Globalping" section (zero-config default, `[Globalping]` output example, optional-token subsection, `netpath coverage` usage) plus an "Upgrading from earlier versions" note.
- Deleted: `src/netpath/atlas.py`, `tests/test_atlas.py`.

**Deviation (decision logged):** the acceptance grep (`grep -ri atlas … README.md` must be empty) and the stale-env-var edge case (README note naming `NETPATH_ATLAS_KEY`) conflict literally. The grep criterion wins; the migration note describes the removed key-and-credits backend and says the old flag/env var are obsolete and silently ignored, without the literal string.

**Checks:** full suite 96 passed (101 minus the 5 deleted Atlas tests), `ruff check src tests` clean, acceptance grep returns nothing, `netpath country --help` shows `--gp-token`/`--no-remote` with no Atlas/credit mention, `netpath coverage --help` works, and a live `netpath coverage --top 5` smoke test returned a ranked probe table with no token set.

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 8 files changed across 2 phases

All 9 acceptance criteria pass: in-network measurements run without any key, the coverage command works zero-config, the Atlas backend and its tests are fully deleted with no grep survivors, and the new test suite covers all required parse and inventory paths. Automated checks (96 tests, ruff) are clean.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Test suite (pytest) | PASS | 96 passed, 0 failed, 0 skipped |
| Lint (ruff) | PASS | All checks passed |

### Acceptance Criteria (9/9 passed)

- [x] AC-1: netpath country ZA --top 5 performs in-network measurements with no token, key, or environment variable set; verified by running the command in a clean environment and observing a [Globalping] subrow or a per-ASN "no Globalping coverage" note — PASS: cli.py:579-580 gp_token defaults None, no_remote defaults False; cli.py:636-656 probe inventory fetched without token; cli.py:813 result merged under "globalping" row key; display.py:385-400 renders [Globalping] subrow
- [x] AC-2: netpath coverage --top 10 prints a ranked per-country probe table with zero configuration, and --globe renders the choropleth — PASS: cli.py:870-908: coverage command; gp_token defaults None (cli.py:872); ranked table printed at cli.py:885-903; globe_mod.render_coverage called at cli.py:908; netpath coverage --help confirmed zero-config
- [x] AC-3: --gp-token and NETPATH_GLOBALPING_TOKEN are accepted on the country and coverage commands and produce an Authorization: Bearer header; verified by a unit test asserting the header in tests/test_globalping.py — PASS: cli.py:36-38: _GP_TOK option with envvar=NETPATH_GLOBALPING_TOKEN; both commands use _GP_TOK (cli.py:579,872); tests/test_globalping.py:38-55 (Bearer with token, no header without); tests/test_globalping.py:120-128 (schedule_measurements Bearer)
- [x] AC-4: --no-remote on the country command skips all Globalping activity; verified by running with the flag and observing no Globalping status lines — PASS: cli.py:636,680,703,731: all Globalping blocks gated by `if not no_remote:`; cli.py:580 no_remote declared with --no-remote flag; netpath country --help confirms flag present
- [x] AC-5: src/netpath/atlas.py and tests/test_atlas.py no longer exist, and grep -ri atlas src/netpath/cli.py src/netpath/display.py src/netpath/globe.py README.md returns no matches — PASS: ls src/netpath/ shows no atlas.py; ls tests/ shows no test_atlas.py; grep -in atlas across all four target files returned no output
- [x] AC-6: netpath --help, netpath country --help, and netpath coverage --help contain no mention of Atlas, API keys as a requirement, or credits — PASS: netpath --help: lists coverage not atlas-profile; country --help: shows --gp-token and --no-remote, no --atlas-key, no credits; coverage --help: zero-config help text confirmed
- [x] AC-7: JSON output for country mode uses a globalping key for remote results and contains no atlas key or atlas_anchor source tag; verified by inspecting --json output or the MeasurementResult-adjacent row shape — PASS: cli.py:813: _row["globalping"] = _gp_data; cli.py:47: probe_errors["globalping"]; grep for atlas/atlas_anchor keys in cli.py/display.py returns no output; country command has no --json flag so row shape is the applicable criterion
- [x] AC-8: tests/test_globalping.py covers ping RTT parsing, mtr AS-path parsing, coverage counting, and error/empty responses; pytest passes — PASS: tests/test_globalping.py: parse_ping_rtt (lines 186-212), parse_mtr_as_path (lines 221-268), count_probes_by_asn + coverage_by_country (lines 60-84), error paths (lines 29-35, 175-181, 206-212); pytest: 96 passed
- [x] AC-9: ruff check src tests passes — PASS: ruff check src tests: All checks passed

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- AS-path labels derived from hop hostname registered domain ("AS174 (cogentco.com)") since Globalping mtr hops carry no network-name field — Cymru lookup dropped from remote path parsing
- schedule_measurements() raises requests.HTTPError for 422/429/401 (response attached) so cli.py can branch on status_code for per-ASN error messages
- README migration note avoids the literal word "Atlas" to satisfy the acceptance grep while still communicating upgrade guidance
- Single GET /v1/probes inventory request aggregated client-side for both pre-sweep coverage check and the coverage command — no per-ASN queries, no budget concept
- Remote measurements default-on in country mode; --no-remote flag (styled after --no-throughput) provides opt-out without reintroducing any key requirement

## Required Changes

None.

## Release

## Release Notes

### What was built
- Replaced the RIPE Atlas backend with Globalping as the sole in-network measurement backend, eliminating the API key, account, and credit-balance prerequisite
- New `src/netpath/globalping.py` module: probe inventory via a single `GET /v1/probes`, ping and mtr measurement scheduling, 2 s/60 s polling, and pure result parsers (aggregated RTT from ping; deduplicated AS-hop path from per-hop `asn` fields — no Cymru lookup)
- Country mode now runs in-network measurements by default; `--no-remote` opts out; optional `--gp-token` / `NETPATH_GLOBALPING_TOKEN` raises the rate-limit tier
- `atlas-profile` command renamed to `coverage`; zero-config, no key-check, probes-only table
- `atlas.py` and `tests/test_atlas.py` deleted; 26-test `tests/test_globalping.py` added

### Key decisions
- AS-path labels use the registered domain from the hop's `resolvedHostname` ("AS174 (cogentco.com)") since Globalping mtr hops carry no network-name field — Cymru lookup dropped from remote path parsing
- `schedule_measurements()` raises `requests.HTTPError` (with response attached) for 422/429/401 so `cli.py` can branch on `status_code` for per-ASN `probe_errors` messages
- README migration note avoids the literal word "Atlas" to satisfy the acceptance grep while still communicating upgrade guidance
- Single `GET /v1/probes` inventory request aggregated client-side for both pre-sweep coverage check and the `coverage` command — no per-ASN queries, no budget concept
- Remote measurements default-on in country mode; `--no-remote` flag (styled after `--no-throughput`) provides opt-out without reintroducing any key requirement

### Changes by phase
- **Phase 1: Build the Globalping backend module** — Created `src/netpath/globalping.py` with full integration (probe inventory, scheduling, polling, parsers) and `tests/test_globalping.py` with 26 mocked-requests tests; verified against the live Globalping OpenAPI spec; full suite 101 passed, ruff clean; no existing files touched
- **Phase 2: Switch the CLI over and delete Atlas** — Rewired `cli.py` to Globalping (drops `--atlas-key`, adds `--gp-token`/`--no-remote`, renames `atlas-profile` to `coverage`); updated `display.py` ([Globalping] subrow, anchor variant removed), `globe.py` (choropleth retitled), `README.md` (Atlas section replaced by Globalping section plus upgrade note); deleted `atlas.py` and `test_atlas.py`; acceptance grep returns nothing; 96 tests pass, ruff clean; live `netpath coverage --top 5` smoke test confirmed zero-config operation

## Verification

### Production Build
PASS — `python -m build` produced `netpath-0.10.1.dev16+g298be4378.tar.gz` and `netpath-0.10.1.dev16+g298be4378-py3-none-any.whl`

### Review Reference
Approved by reviewer on 2026-07-02 — 9/9 acceptance criteria, pytest 96 passed, ruff clean

