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