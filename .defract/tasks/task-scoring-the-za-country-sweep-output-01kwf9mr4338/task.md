---
defract:
  id: task-scoring-the-za-country-sweep-output-01kwf9mr4338
  type: bug
  status: active
  stage: release
  phase: 0
  total_phases: 1
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

## Story Brief

# Scoring the ZA Country-Sweep Output

# Scoring the ZA Country-Sweep Output

# Scoring the ZA Country-Sweep Output

## What We're Building

Fix four diagnostic accuracy issues surfaced by a South Africa country sweep, and add pre-validation of iperf3 test servers so sweeps only probe against confirmed-live endpoints. The diagnostic fixes address: overstated severity for paths where downstream routers silently drop ICMP probes, jitter readings that may reflect cross-destination spread rather than true variance, undetected routing loops, and duplicated operator names in output.

## Expected Outcome

- Paths where downstream routers filter ICMP probes — but the route itself is healthy — are reported as informational rather than triggering a high-severity "Incomplete Path" warning
- Jitter readings reflect actual variance at a single stable endpoint rather than RTT spread across multiple distinct destination routers
- Routing loops (a repeating sequence of hops past the target network boundary) are detected and surfaced as a distinct diagnostic signal with appropriate severity
- Operator names display cleanly without duplication (e.g., "Dimension Data" instead of "Dimension Data - Dimension Data")
- Country sweeps only probe iperf3 servers that are confirmed live at sweep time — unresponsive entries from the server list are filtered out before probing begins, improving overall result quality

## Phase Outcomes

- **Phase 1: Fix diagnostic accuracy, jitter, name display, and server liveness** — Country sweeps produce fewer false alarms, operator names are clean in summary output, and probe attempts skip servers known to be dead.

## Out of Scope

- No changes to how country sweeps select, rank, or filter ASNs
- No changes to the iperf3 server list format or sourcing — validation happens at runtime, not at list-build time
- No new CLI flags or user-facing configuration options

## Scope Summary

**Size:** 9 requirements, 12 acceptance criteria, 1 implementation phase
**Key decisions:**
- ICMP-filtering is inferred from trailing `???` hops after the last responsive hub — keeps `diagnosis.py` a pure function with no new data dependencies
- Jitter uses the last responsive hub's `StDev` rather than the mean across all hubs — single stable endpoint, not a cross-hop average
- Server liveness check lives in `find_servers_in_asn()` rather than `_fetch_and_resolve()` — validates only ASN-matched candidates, not the entire list
**Biggest risk:** Existing `test_incomplete_path_with_stall_hop` and `test_incomplete_path_without_stall_hop` both pass `hubs=[]`; the new logic guards on an empty hub list and falls back to "warning", so those tests are unaffected — but this needs to be confirmed in the verification pass.

## Context

The South Africa country sweep produced three categories of false alarms. First, paths through ISP networks that filter ICMP TTL-exceeded responses were flagged as "Incomplete Path" warnings even when the destination was fully reachable — in the ZA case, many ISPs drop all ICMP probes inside their own AS, so the traceroute shows `???` hops from the AS boundary onward but traffic flows fine. Second, jitter computed as the mean `StDev` across all path hops was inflated by natural per-hop variance rather than measuring true end-to-end stability. Third, routing loops went undetected while some operator names appeared duplicated ("Dimension Data - Dimension Data") because `clean_asn_name()` only handled short-code prefixes, not identical prefix–rest pairs.

The five changes touch `diagnosis.py` (check 0 logic and a new check 10), `cli.py:_measure()` (jitter calculation at lines 254–258), `display.py:clean_asn_name()` (lines 23–31), and `servers.py:find_servers_in_asn()` (new `_is_alive()` helper).

## Requirements

### Diagnostic: ICMP-Filtered Paths

- R1: When `path_complete is False` and the hub list is empty, the existing `incomplete_path` warning is preserved — no trace data at all is a genuine problem, not ICMP filtering. (`diagnosis.py`, check 0)
- R2: When `path_complete is False` and all hubs are `???` (all-stars path), emit an `icmp_filtered_path` signal with severity `"ok"` — the entire path filtered ICMP probes; the destination may still be reachable. (`diagnosis.py`, check 0)
- R3: When `path_complete is False` and there are responsive hubs followed by trailing `???` hops (last responsive hub `count` < maximum hub `count` in the list), emit `icmp_filtered_path` with severity `"ok"` — downstream routers inside the target ISP filter ICMP TTL-exceeded; the route is likely healthy. (`diagnosis.py`, check 0)
- R4: When `path_complete is False` and the last hub in the path is responsive (no trailing `???`), retain the existing `incomplete_path` signal with severity `"warning"` — the path genuinely stalled before the target ASN. (`diagnosis.py`, check 0)

### Diagnostic: Jitter Accuracy

- R5: `jitter_ms` is set to the `StDev` of the last responsive hub in the path rather than the mean `StDev` across all responsive hubs. The last responsive hub's `StDev` represents end-to-end latency variance to the destination endpoint. (`cli.py:_measure()`, lines 254–258)

### Diagnostic: Routing Loop Detection

- R6: A new check 10 in `diagnose()` inspects `result["as_path"]` for repeated ASNs, excluding `"AS???"`. If any known ASN appears more than once in the de-adjacent AS path list, a `routing_loop` signal with severity `"warning"` is emitted, naming the first repeated ASN in the detail string. (`diagnosis.py`)
- R7: `_CONDITION_VERDICT` gains `"routing_loop": "Routing Loop"` and `"icmp_filtered_path": "Healthy"` entries so both new conditions map to human-readable verdict labels. (`diagnosis.py`)

### Display: Operator Name Deduplication

- R8: `clean_asn_name()` adds an exact-duplicate guard — when `prefix.strip() == rest.strip()` (e.g., `"Dimension Data - Dimension Data"`), return the cleaned rest without duplication. This check runs before the existing short-code check so multi-word duplicates are caught first. (`display.py:clean_asn_name()`, lines 23–31)

### Server Pre-Validation

- R9: `find_servers_in_asn()` filters candidate servers through a TCP socket check on each server's IP and port before returning them. Servers that do not accept a connection within 3 seconds are excluded. A new private `_is_alive(ip, port, timeout=3.0)` function in `servers.py` encapsulates the check using `socket.create_connection()`, catching `OSError`. (`servers.py`)

## Acceptance Criteria

- [ ] `pytest tests/test_diagnosis.py` passes with no regressions in the 19 existing tests after the incomplete_path logic change
- [ ] New test `test_icmp_filtered_path_all_stars`: `path_complete=False` with all-`???` hubs and a non-empty hub list produces condition `icmp_filtered_path`, severity `"ok"`
- [ ] New test `test_icmp_filtered_path_trailing_stars`: `path_complete=False` with some responsive hubs followed by `???` hubs (stall_hop < max hub count) produces condition `icmp_filtered_path`, severity `"ok"`
- [ ] New test `test_incomplete_path_genuine_stall`: `path_complete=False` where the last hub is responsive and equals the max hub count produces condition `incomplete_path`, severity `"warning"`
- [ ] New test `test_routing_loop_detected`: `as_path=["AS1","AS2","AS3","AS2"]` produces condition `routing_loop`, severity `"warning"`, verdict `"Routing Loop"`
- [ ] New test `test_routing_loop_no_repeat`: unique AS path produces no `routing_loop` signal
- [ ] `tests/test_display.py` created; `clean_asn_name("Dimension Data - Dimension Data")` returns `"Dimension Data"`
- [ ] `clean_asn_name("Acme Corp - Acme Corp")` returns `"Acme Corp"` (multi-word exact duplicate handled)
- [ ] `clean_asn_name("PARTNER-AS - Partner Comms")` still returns `"Partner Comms"` (existing behavior preserved)
- [ ] `tests/test_servers.py` created; `_is_alive` returns `False` when `socket.create_connection` raises `OSError` (verified via `unittest.mock.patch`)
- [ ] `ruff check src tests` passes with no new lint errors
- [ ] `pytest` full suite green

## Implementation Phases

### Phase 1: Fix diagnostic accuracy, jitter, name display, and server liveness
**Scope:** Apply all five targeted fixes across four source modules and add covering tests for each change.
**Files:**
- `src/netpath/diagnosis.py` — update check 0 (ICMP-filtered path branching), add check 10 (routing loop), update `_CONDITION_VERDICT`
- `src/netpath/cli.py` — replace mean-StDev jitter with last-hub StDev in `_measure()` (lines 254–258)
- `src/netpath/display.py` — add exact-duplicate guard in `clean_asn_name()` (lines 23–31)
- `src/netpath/servers.py` — add `import socket`, add `_is_alive()`, integrate into `find_servers_in_asn()`
- `tests/test_diagnosis.py` — add 5 new test cases (icmp_filtered all-stars, icmp_filtered trailing stars, genuine stall, routing loop detected, routing loop no-repeat)
- `tests/test_display.py` — create; add 3 `clean_asn_name` test cases
- `tests/test_servers.py` — create; add `_is_alive` mock test
**Verification:**
- `pytest tests/test_diagnosis.py` — all 24 tests pass (19 existing + 5 new)
- `pytest tests/test_display.py` — 3 clean_asn_name cases pass
- `pytest tests/test_servers.py` — `_is_alive` mock test passes
- `pytest` — full suite green
- `ruff check src tests` — no errors
**Estimated effort:** Medium

## Edge Cases

- **All-`???` path**: no responsive hubs at all — `icmp_filtered_path` ok (not a genuine stall)
- **Empty hub list**: `hubs=[]` — fall back to `incomplete_path` warning; avoids vacuously true all-`???` check
- **Single-hop path**: only one hub; jitter = that hub's StDev; no mid-path loss check runs (requires ≥ 2 hubs)
- **AS path with only `"AS???"` entries**: routing loop check skips all entries — no false positive
- **`stall_hop` equals max hub count**: last hub is responsive, no trailing `???` — genuine stall, keep "warning"
- **All candidate servers dead**: `find_servers_in_asn()` returns `[]`; country command falls back to `get_test_ip_for_asn()` via the existing no-servers path — no changes to that fallback needed
- **Port refused vs timeout**: `_is_alive` catches both under `OSError`; both count as dead

## Technical Notes

**Check 0 logic (ICMP-filtered path):** Read `hubs_local = result.get("hubs") or []`. Guard: `if not hubs_local` → genuine problem, emit `incomplete_path` warning with stall detail as today. Otherwise: `all_stars = all(h.get("host") in ("???", None, "") for h in hubs_local)`. If `all_stars` → `icmp_filtered_path` ok. Otherwise: `max_count = max(h.get("count", 0) for h in hubs_local)`, `stall = result.get("stall_hop")`. If `stall is not None and max_count > stall` → `icmp_filtered_path` ok. Else → `incomplete_path` warning.

**Routing loop (check 10):** `as_path = result.get("as_path") or []`; `known = [a for a in as_path if a and a != "AS???"]`; `if len(known) != len(set(known))` → loop detected. To find the first repeat: iterate `known` with a `seen` set.

**Jitter fix:** Replace the averaging loop with a backward scan: `for h in reversed(hubs): if h.get("host") not in ("???", None, "") and h.get("StDev") is not None: result["jitter_ms"] = round(h["StDev"] or 0.0, 2); break`.

**`_is_alive`:** `import socket` at top of `servers.py`. Function: `try: socket.create_connection((ip, port), timeout).close(); return True` / `except OSError: return False`. In `find_servers_in_asn()`, replace the final return with: `live = [s for s in candidates if _is_alive(s["ip"], s["port"])]`.

### Dependencies

No external dependencies added. `socket` is stdlib.

## Implementation Notes

## Phase 1: Fix diagnostic accuracy, jitter, name display, and server liveness

All five targeted fixes implemented across four source modules, with covering tests.

### Changes

**`src/netpath/diagnosis.py`**
- Updated `_CONDITION_VERDICT` with `"icmp_filtered_path": "Healthy"` and `"routing_loop": "Routing Loop"`.
- Rewrote check 0: empty hub list → `incomplete_path` warning (unchanged); all-stars hub list → `icmp_filtered_path` ok; trailing `???` hops (`max_count > stall_hop`) → `icmp_filtered_path` ok; last hub responsive → `incomplete_path` warning.
- Added check 10: de-adjacent AS path iteration with a `seen` set to find the first repeated known ASN; emits `routing_loop` warning when found.

**`src/netpath/cli.py`**
- Replaced the mean-StDev averaging loop (lines 254–258) with a backward scan over `hubs` that picks the last responsive hub's `StDev` as `jitter_ms`.

**`src/netpath/display.py`**
- Added exact-duplicate guard in `clean_asn_name()` before the short-code check: when `prefix.strip() == rest.strip()`, return the cleaned rest.

**`src/netpath/servers.py`**
- Added `import socket`.
- Added `_is_alive(ip, port, timeout=3.0)` using `socket.create_connection`, catching `OSError`.
- Updated `find_servers_in_asn()` to filter candidates through `_is_alive` before returning.

### Tests

- `tests/test_diagnosis.py` — 5 new cases: `test_icmp_filtered_path_all_stars`, `test_icmp_filtered_path_trailing_stars`, `test_incomplete_path_genuine_stall`, `test_routing_loop_detected`, `test_routing_loop_no_repeat`.
- `tests/test_display.py` — created; 3 `clean_asn_name` cases.
- `tests/test_servers.py` — created; 2 `_is_alive` mock cases.

### Results

62/62 tests pass (up from 52). `ruff check src tests` clean.

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 7 files changed across 1 phases

All 12 acceptance criteria pass. Five targeted fixes are correctly implemented across four source modules with 10 new covering tests. Automated checks (62/62 tests, ruff clean) pass with no regressions.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Test suite | PASS | 62/62 tests pass (uv run pytest tests/ -q) |
| Lint | PASS | ruff check src tests — no errors |

### Acceptance Criteria (12/12 passed)

- [x] AC-1: `pytest tests/test_diagnosis.py` passes with no regressions in the 19 existing tests after the incomplete_path logic change — PASS: 31/31 tests pass in test_diagnosis.py. The AC says 19 but the actual pre-existing count is 26 (previous tasks added more); all pre-existing tests still pass with the updated check-0 logic.
- [x] AC-2: New test `test_icmp_filtered_path_all_stars`: `path_complete=False` with all-`???` hubs and a non-empty hub list produces condition `icmp_filtered_path`, severity `"ok"` — PASS: tests/test_diagnosis.py:221-231 — test present and passes. diagnosis.py:70-81 performs all_stars check and emits icmp_filtered_path severity ok.
- [x] AC-3: New test `test_icmp_filtered_path_trailing_stars`: `path_complete=False` with some responsive hubs followed by `???` hubs (stall_hop < max hub count) produces condition `icmp_filtered_path`, severity `"ok"` — PASS: tests/test_diagnosis.py:234-245 — test passes with stall_hop=2 and max_count=4. diagnosis.py:83-93 checks max_count > stall.
- [x] AC-4: New test `test_incomplete_path_genuine_stall`: `path_complete=False` where the last hub is responsive and equals the max hub count produces condition `incomplete_path`, severity `"warning"` — PASS: tests/test_diagnosis.py:248-258 — test passes with stall_hop=3 and max_count=3. Condition max_count > stall is False (3 > 3 is False), so falls to incomplete_path warning.
- [x] AC-5: New test `test_routing_loop_detected`: `as_path=["AS1","AS2","AS3","AS2"]` produces condition `routing_loop`, severity `"warning"`, verdict `"Routing Loop"` — PASS: tests/test_diagnosis.py:261-267 — test passes. diagnosis.py:244-261 (check 10) detects repeated AS2 and emits routing_loop warning. _CONDITION_VERDICT maps to 'Routing Loop'.
- [x] AC-6: New test `test_routing_loop_no_repeat`: unique AS path produces no `routing_loop` signal — PASS: tests/test_diagnosis.py:270-273 — test passes. as_path=[AS1,AS2,AS3,AS4] has no repeats; len(known)==len(set(known)) so no routing_loop emitted.
- [x] AC-7: `tests/test_display.py` created; `clean_asn_name("Dimension Data - Dimension Data")` returns `"Dimension Data"` — PASS: tests/test_display.py:4-6 — test present and passes. display.py:31 exact-duplicate guard: prefix==rest returns rest.
- [x] AC-8: `clean_asn_name("Acme Corp - Acme Corp")` returns `"Acme Corp"` (multi-word exact duplicate handled) — PASS: tests/test_display.py:9-11 — test present and passes. Same prefix==rest guard handles multi-word case.
- [x] AC-9: `clean_asn_name("PARTNER-AS - Partner Comms")` still returns `"Partner Comms"` (existing behavior preserved) — PASS: tests/test_display.py:14-16 — test present and passes. PARTNER-AS != Partner Comms, falls to short-code check (no spaces, len 10 <= 25), returns Partner Comms.
- [x] AC-10: `tests/test_servers.py` created; `_is_alive` returns `False` when `socket.create_connection` raises `OSError` (verified via `unittest.mock.patch`) — PASS: tests/test_servers.py:6-9 — patches socket.create_connection with side_effect=OSError; _is_alive returns False. servers.py:68-72 catches OSError.
- [x] AC-11: `ruff check src tests` passes with no new lint errors — PASS: uv run ruff check src tests — 'All checks passed!'
- [x] AC-12: `pytest` full suite green — PASS: uv run pytest tests/ -q — 62 passed in 0.09s

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- ICMP-filtered path detection uses trailing-??? hub inspection (stall_hop vs max_count) rather than a TCP connectivity cross-check — preserves diagnosis.py as a pure function with no new data dependencies
- Server liveness validation placed in find_servers_in_asn() rather than _fetch_and_resolve() — checks only ASN-matched candidates, keeping per-ASN overhead small while leaving the module-level cache unaffected
- _extract_as_path() already de-duplicates adjacent ASNs, so check 10's routing loop detection operates on a de-adjacent path — no false positives from consecutive same-AS hops

## Required Changes

None.

## Release

## Release Notes

### What was built
- Fixed ICMP-filtered path false alarms: paths where downstream routers silently drop ICMP probes are now reported as informational (`icmp_filtered_path`, severity `ok`) rather than triggering a `warning`-level "Incomplete Path" signal
- Fixed jitter accuracy: `jitter_ms` now reflects the last responsive hub's `StDev` (single stable endpoint) rather than the mean `StDev` across all path hubs
- Added routing loop detection: a new check 10 in `diagnose()` identifies repeated ASNs in the de-adjacent AS path and emits a `routing_loop` warning naming the first repeated ASN
- Fixed operator name deduplication: `clean_asn_name()` now collapses exact-duplicate prefix/rest pairs (e.g., "Dimension Data - Dimension Data" → "Dimension Data") before the short-code check
- Added iperf3 server pre-validation: `find_servers_in_asn()` filters candidates through a TCP socket check (`_is_alive`) before returning them, so sweeps only probe confirmed-live endpoints

### Key decisions
- ICMP-filtered path detection uses trailing-??? hub inspection (stall_hop vs max_count) rather than a TCP connectivity cross-check — preserves `diagnosis.py` as a pure function with no new data dependencies
- Server liveness validation placed in `find_servers_in_asn()` rather than `_fetch_and_resolve()` — checks only ASN-matched candidates, keeping per-ASN overhead small while leaving the module-level cache unaffected
- `_extract_as_path()` already de-duplicates adjacent ASNs, so routing loop detection operates on a de-adjacent path — no false positives from consecutive same-AS hops

### Changes by phase
- **Phase 1: Fix diagnostic accuracy, jitter, name display, and server liveness** — Five targeted fixes shipped across four source modules (`diagnosis.py`, `cli.py`, `display.py`, `servers.py`) with 10 new covering tests (5 in `test_diagnosis.py`, 3 in `test_display.py`, 2 in `test_servers.py`). Full test suite: 62/62 green (up from 52). Lint clean.

## Verification

### Production Build
PASS — `uv build` produced `netpath-0.7.1.dev9+ga31f59539.tar.gz` and `netpath-0.7.1.dev9+ga31f59539-py3-none-any.whl`

### Review Reference
Approved on 2026-07-01 — 12/12 acceptance criteria, automated checks passed (62/62 tests, ruff clean)

### Release Checklist
- [x] Approved review exists (2026-07-01, 12/12 AC)
- [x] Production build passes (`uv build` — sdist + wheel built)
- [x] Code committed and pushed (`6aa27f6`, branch pushed to origin)
- [x] Release notes prepared
- [x] Stage content updated
- [x] Completion event logged

### Task Timeline
- Created: 2026-07-01T16:54:21Z
- Scope approved: 2026-07-01T17:36:24Z
- Implementation started: 2026-07-01T17:36:25Z
- Phase 1 completed: 2026-07-01T17:40:34Z
- Phase 1 approved: 2026-07-01T17:47:11Z
- Review started: 2026-07-01T17:47:12Z
- Review approved (APPROVE): 2026-07-01T17:51:14Z
- Release validated: 2026-07-01

### Warnings
None

