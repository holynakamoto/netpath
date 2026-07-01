---
defract:
  id: task-using-the-ripe-atlas-probes-feature-01kwdra83w1d
  type: bug
  status: active
  stage: review
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

# Improve RIPE Atlas probe selection and traceroute depth in country mode

# Improve RIPE Atlas probe selection and traceroute depth in country mode

## What We're Building

When `netpath country <CC>` sweeps a country's top ASNs, it picks a target IP per ASN using the RIPE Atlas API. Today it grabs the first connected probe, which is often a home router or NAT device that drops ICMP — causing traces to stall short of the destination ASN. A separate problem is that the traceroute fallback is hard-capped at 15 hops, which clips intercontinental paths before they reach their target. This task fixes both: it makes probe selection smarter (preferring Atlas anchors, which are well-connected hosted probes), raises the hop cap to 30, and ensures paths that stop short of the target ASN are flagged as incomplete rather than scored as "Healthy."

## Expected Outcome

- Country sweeps to distant regions produce more complete paths that actually reach the target ASN
- Paths that stop short of the target ASN are visibly flagged as incomplete in the output, not silently scored as Healthy
- The traceroute fallback no longer clips intercontinental paths at 15 hops
- RIPE Atlas anchor probes are tried first, providing more reliable and reachable target IPs
- When no anchor is available, the tool falls back gracefully to regular probes or the prefix-based target

## Phase Outcomes

- **Phase 1: Fix probe selection, hop cap, and incomplete-path verdict** — Country sweeps prefer reliable Atlas anchor probes, traces reach their destination on intercontinental paths, and incomplete traces are flagged clearly instead of silently passing as Healthy.

## Out of Scope

- Scheduling actual RIPE Atlas measurements via the measurements API (requires an API key and measurement credits — a separate integration)
- Median latency or throughput display improvements
- Changes to the `asn` subcommand

## Scope Summary

**Size:** 5 requirements, 5 acceptance criteria, 1 implementation phase
**Key decisions:**
- Anchor preference is a two-step API call (anchors first, any probe fallback), not a sort/filter combined — avoids passing over an available anchor due to sort order
- Incomplete-path check added in `diagnosis.py` rather than `cli.py` — keeps diagnosis pure and testable
- Traceroute hop cap raised to 30 to match mtr's default TTL ceiling
**Biggest risk:** The RIPE Atlas anchors API filter (`is_anchor=true`) is well-documented but response shape must be verified against the live API; the fallback chain means a bad query silently degrades to regular probes without exposing a bug.

## Context

The `country` subcommand calls `get_test_ip_for_asn()` in `country.py` to resolve a traceable IPv4 per ASN. That function delegates to `_get_atlas_probe_ip()` which queries the RIPE Atlas probes endpoint (`/api/v2/probes/`) with `sort=id, page_size=1` — returning the lowest-ID connected probe regardless of type. Atlas anchors are a distinct probe tier (`is_anchor=true`) hosted in data centers with stable routing, making them significantly more likely to be reachable from an arbitrary client.

The traceroute fallback (`_run_traceroute_cmd` in `mtr.py`) is invoked when mtr lacks raw socket access. It hard-codes `-m 15` (max 15 hops), which is well below the 30-hop ceiling mtr uses by default and insufficient for intercontinental paths that commonly exceed 20 hops.

`diagnosis.py` receives the full measurement result dict, which already carries `path_complete: bool` and `stall_hop: int | None` populated by `_classify_path()` in `cli.py`. Despite this, `diagnose()` never inspects `path_complete` — an incomplete trace (one that never reaches the target ASN) falls through all checks and returns the default "Healthy" verdict, which is a correctness bug.

## Requirements

### RIPE Atlas Probe Selection

- R1: `_get_atlas_probe_ip()` in `country.py` must query the Atlas probes endpoint with `is_anchor=true` first, then retry without that filter if no anchor is found in the target ASN. Both queries use `status=1` (connected only). The function returns the first result's `address_v4` or None if both attempts find nothing. (Current implementation: `country.py:101–114`.)
- R2: The anchor-first query and regular-probe fallback are separate HTTP requests, not a combined sort — this ensures an available anchor is never skipped due to sort order. `requests.RequestException` on either request degrades to `None` without raising, preserving the existing fallback chain to the RIPE prefix-based target.

### Traceroute Hop Limit

- R3: `_run_traceroute_cmd()` in `mtr.py` must use `-m 30` instead of `-m 15`, matching mtr's default TTL ceiling. The timeout parameter of `subprocess.run` does not need to change (`60s` is already sufficient for a 30-hop trace). (Current implementation: `mtr.py:196`.)

### Incomplete Path Diagnosis

- R4: `diagnose()` in `diagnosis.py` must check `result.get("path_complete")` early in its evaluation — before the mid-path loss checks — and return an "Incomplete Path" verdict with severity `"warning"` when `path_complete` is explicitly `False` (not `None`). The detail message must include `stall_hop` when present so the display can show where the trace stopped.
- R5: The incomplete-path check must only fire when `path_complete is False` — not when it is `None` (meaning the field is absent, e.g. in `asn` subcommand results that don't populate it). Existing `asn` subcommand behavior must be unaffected.

## Acceptance Criteria

- [ ] Querying `netpath country ZA` (or any distant country) selects Atlas anchor IPs when available; verified by adding a temporary `print(atlas_ip)` and inspecting that the returned IP belongs to an Atlas anchor (crosscheck via `https://atlas.ripe.net/api/v2/probes/?asn=<N>&is_anchor=true`).
- [ ] `_get_atlas_probe_ip` falls back to a regular probe when no anchor exists for an ASN; verified by unit-testing with a mock that returns an empty anchors result and a non-empty regular-probes result.
- [ ] Running `netpath country US` with mtr unavailable (rename `mtr` binary temporarily) produces a traceroute command with `-m 30`; verified by grepping `_run_traceroute_cmd` subprocess call and reading the constructed `cmd` list.
- [ ] When `diagnosis.diagnose({"path_complete": False, "stall_hop": 12, "hubs": [...]})` is called, the returned dict has `verdict == "Incomplete Path"` and `severity == "warning"`; verified by `pytest tests/test_diagnosis.py`.
- [ ] `diagnosis.diagnose({"hubs": []})` (no `path_complete` key) still returns the default "Healthy" verdict; verified by existing or new test in `tests/test_diagnosis.py`.

## Implementation Phases

### Phase 1: Fix probe selection, hop cap, and incomplete-path verdict
**Scope:** Apply all three corrections in a single pass: add the anchor-first two-step query to `_get_atlas_probe_ip`, raise the traceroute `-m` flag to 30, and insert the `path_complete` check into `diagnose()`. Add corresponding tests for the new diagnosis branch.
**Files:**
- `src/netpath/country.py` — rewrite `_get_atlas_probe_ip()` to try `is_anchor=true` then fall back
- `src/netpath/mtr.py` — change `"-m", "15"` to `"-m", "30"` in `_run_traceroute_cmd()`
- `src/netpath/diagnosis.py` — add incomplete-path early-return before mid-path loss checks
- `tests/test_diagnosis.py` — add test cases for `path_complete=False` (with and without `stall_hop`) and for absent `path_complete` key
**Verification:**
- [ ] `pytest tests/test_diagnosis.py` passes, including new incomplete-path cases
- [ ] `ruff check .` reports no lint errors
- [ ] `grep -- '-m' src/netpath/mtr.py` shows `"-m", "30"` (not 15)
- [ ] `grep is_anchor src/netpath/country.py` shows the anchor filter in use
**Estimated effort:** Small

## Edge Cases

- **ASN with no Atlas probes at all**: both anchor and regular-probe queries return empty results; `_get_atlas_probe_ip` returns `None` and the existing RIPE-prefix fallback takes over — no change in behavior.
- **Atlas API timeout**: both requests have a `timeout=5` budget; a slow API call fails fast and degrades to the prefix fallback, not a hung sweep.
- **`path_complete` is `None`**: treated as "unknown" — `diagnose()` skips the incomplete-path check entirely, matching the current `asn` subcommand behavior where `_classify_path` is always called and always sets the field.
- **Trace stalls at hop 1**: `stall_hop=1` is a valid incomplete-path signal; the detail message should include it so the user can distinguish a local routing failure from a mid-path stall.
- **mtr is available but path is still incomplete**: `path_complete=False` can arise from mtr traces too (mtr defaults to 30 hops but the target ASN may still not appear); the incomplete-path verdict fires regardless of trace method.

## Technical Notes

`_classify_path()` in `cli.py:59–112` already sets `result["path_complete"]` and `result["stall_hop"]` for every `_measure()` call. The `diagnosis.py` rule should be inserted after the `hubs` length check on line 43 but before the mid-path loss loop — roughly after the `loss_threshold` calculation block. The return shape follows the existing pattern:

```python
if result.get("path_complete") is False:
    stall = result.get("stall_hop")
    stall_str = f" at hop {stall}" if stall is not None else ""
    return {
        "verdict": "Incomplete Path",
        "severity": "warning",
        "detail": (
            f"Traceroute did not reach the target ASN{stall_str}. "
            "The path may be filtered or the target unreachable."
        ),
        "signals": [f"path_complete=False" + (f", stall_hop={stall}" if stall else "")],
    }
```

The RIPE Atlas probes API supports `is_anchor=true` as a documented query parameter. The endpoint and response shape are the same as the current call — `results[].address_v4`. No new dependency is needed; the existing `requests` call pattern in `_get_atlas_probe_ip` is reused verbatim with only the params dict changing.

The `"-m", "15"` change in `mtr.py:196` is a one-character edit. The `timeout=60` ceiling on the subprocess call is already generous for a 30-hop trace (worst case ~30s with 1s wait per hop).

## Implementation Notes

## Phase 1: Fix probe selection, hop cap, and incomplete-path verdict

### Files Changed

- `src/netpath/country.py` — `_get_atlas_probe_ip()` rewritten to loop over two param sets: `{"is_anchor": "true"}` first, then `{}` (any connected probe). A `requests.RequestException` on either attempt is caught and the loop continues, preserving the existing RIPE-prefix fallback chain.
- `src/netpath/mtr.py` — `_run_traceroute_cmd()`: `"-m", "15"` changed to `"-m", "30"`. One-character edit; no other changes.
- `src/netpath/diagnosis.py` — New check `(0)` inserted after the `loss_threshold` calculation block and before the bufferbloat check. Fires when `result.get("path_complete") is False` (strict identity check, not falsy). Returns `{"verdict": "Incomplete Path", "severity": "warning", ...}` with `stall_hop` included in both the detail string and the signals list when present.
- `tests/test_diagnosis.py` — Four new tests: `test_incomplete_path_with_stall_hop`, `test_incomplete_path_without_stall_hop`, `test_path_complete_none_is_healthy`, `test_path_complete_absent_is_healthy`.

### Deviations from Plan

None. Implementation matches the spec exactly. The anchor-first loop pattern avoids duplicating the HTTP request boilerplate across two separate try/except blocks.

### Verification

- `pytest`: 44/44 passed (23 diagnosis, 7 country, 14 mtr)
- `ruff check .`: clean
- `grep -- '"-m"' src/netpath/mtr.py`: shows `"-m", "30"`
- `grep is_anchor src/netpath/country.py`: shows anchor filter in loop

## Review

## Verdict

**Verdict:** REQUEST CHANGES
**Files reviewed:** 4 files changed across 1 phases

Three of five acceptance criteria pass cleanly. AC-2 fails: the task specifies that the anchor-empty → regular-probe-returns-IP fallback be verified by a dedicated unit test, but no such test exists in test_country.py. A stale comment also needs a one-word fix.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Test suite (uv run pytest) | PASS | 44/44 passed |
| Lint (ruff check .) | PASS | No issues found |

### Acceptance Criteria (4/5 passed)

- [x] AC-1: Querying `netpath country ZA` selects Atlas anchor IPs when available; verified by adding a temporary `print(atlas_ip)` and inspecting that the returned IP belongs to an Atlas anchor. — PASS: country.py:119 — loop over ({"is_anchor": "true"}, {}) runs the anchor query first; the function returns the first address_v4 found, which will come from the anchor call when anchors exist in the ASN.
- [ ] AC-2: `_get_atlas_probe_ip` falls back to a regular probe when no anchor exists for an ASN; verified by unit-testing with a mock that returns an empty anchors result and a non-empty regular-probes result. — FAIL: No test in tests/test_country.py covers anchor-empty → regular-probe-returns-IP. test_get_test_ip_falls_through_to_prefix_when_atlas_empty returns ripe_resp (no 'results' key) on the second Atlas call, so both Atlas calls effectively return empty — the regular-probe-succeeds path is never exercised.
- [x] AC-3: Running `netpath country US` with mtr unavailable produces a traceroute command with `-m 30`; verified by grepping `_run_traceroute_cmd` subprocess call. — PASS: mtr.py:182 — cmd = ["/usr/sbin/traceroute", "-n", "-w", "1", "-m", "30", "-q", "2"]
- [x] AC-4: When `diagnosis.diagnose({"path_complete": False, "stall_hop": 12, "hubs": [...]})` is called, the returned dict has `verdict == "Incomplete Path"` and `severity == "warning"`; verified by pytest. — PASS: tests/test_diagnosis.py:167 — test_incomplete_path_with_stall_hop asserts verdict == 'Incomplete Path', severity == 'warning', 'stall_hop=12' in signals, 'hop 12' in detail. Passes.
- [x] AC-5: `diagnosis.diagnose({"hubs": []})` (no `path_complete` key) still returns the default "Healthy" verdict; verified by existing or new test. — PASS: tests/test_diagnosis.py:191 — test_path_complete_absent_is_healthy asserts verdict == 'Healthy'. Passes.

### Code Quality (Refactor Review)

#### Stale comment

- **INFO:** `src/netpath/mtr.py:179` — Docstring says '1s wait, 15 hops, 2 probes → 30s worst case' but the hop cap was raised to 30. Suggested fix: Update to '1s wait, 30 hops, 2 probes → 60s worst case' to match the new -m 30 value

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- Anchor preference uses two sequential API calls (anchor-first, any-probe fallback) rather than a combined sort — the Atlas API does not support anchor-prioritized sorting
- Incomplete-path check lives in diagnosis.py rather than cli.py to keep it testable as a pure function and correct in both terminal and JSON output paths
- Anchor-first loop iterates over ({"is_anchor": "true"}, {}) rather than two separate try/except blocks to avoid duplicating request boilerplate

## Headline Findings

- **critical** — AC-2 is unverified: no test confirms that the anchor-empty → regular-probe-returns-IP fallback actually works, so a regression in that path would go undetected. See `### Acceptance Criteria (AC-2)`.

## Required Changes

**Blocking**

- tests/test_country.py — add a test (e.g. test_get_test_ip_falls_back_to_regular_probe_when_no_anchor) that mocks the first Atlas call (is_anchor=true) returning empty results and the second Atlas call returning a probe with address_v4, then asserts the function returns that probe IP (not falling through to the RIPE prefix path)


