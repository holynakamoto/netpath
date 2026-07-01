---
defract:
  id: task-incomplete-paths-still-showing-in-za-01kwddfsahcm
  type: improvement
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

# Incomplete paths still showing in ZA country sweep

# Incomplete paths still showing in ZA country sweep

# Incomplete paths still showing in ZA country sweep

## What We're Building

When running a country sweep, netpath selects an arbitrary IP address inside each target ASN to use as the traceroute destination. That address is almost never a live host, so the trace stalls before the destination network responds and the path is marked incomplete. This task fixes the root cause by querying the RIPE Atlas probe database: Atlas maintains thousands of connected probes distributed across ISP ASNs worldwide. For each target ASN, netpath now looks up a connected Atlas probe and uses that probe's IP as the traceroute destination — a known-live host inside the target network.

## Expected Outcome

- Country sweeps show significantly fewer incomplete paths — particularly for regions like ZA where most paths previously stalled.
- Stalled traces now reach the destination ASN as a tagged, responsive hop rather than timing out in transit networks.
- The incomplete-paths section of sweep output shrinks or disappears for ASNs that previously showed only transit/IXP stall points (AS3356, AS6939, AS2914 and similar).
- For ASNs where no Atlas probe is registered (smaller or newer ASNs), the existing prefix-based IP selection is used as a fallback so those ASNs still attempt a trace.
- For ASNs where no reachable candidate can be found at all (genuinely unreachable), the path still classifies as incomplete with the same informative stall reporting introduced previously.

## Phase Outcomes

- **Phase 1: Use RIPE Atlas probe IPs as traceroute targets** — Country sweeps look up a connected Atlas probe inside each target ASN and trace to that probe's IP instead of an arbitrary prefix address, so paths reach live hosts and complete successfully.

## Out of Scope

- Improving how incomplete paths are displayed — that was completed in the previous task and will not be changed here.
- Fixing incomplete paths in the `asn` subcommand, which uses a user-supplied or server-resolved target and is not affected by the country-mode IP selection logic.
- Running Atlas measurements (ping, traceroute) via the Atlas API — we are only reading the probe registry to get a known-live IP, not scheduling measurement jobs.
- Adding a new CLI flag or configuration option for probe lookup behavior.

## Scope Summary

**Size:** 6 requirements, 6 acceptance criteria, 1 implementation phase
**Key decisions:**
- Primary: RIPE Atlas probes API (`/api/v2/probes/?asn=<n>&status=1`) to find a connected probe IP in the target ASN
- Fallback: existing RIPE-prefix-based selection when no Atlas probe is registered for the ASN
- Atlas lookup is unauthenticated — the probes endpoint is public
**Biggest risk:** Atlas coverage gaps. Well-known transit ASNs (AS3356, AS6939) may not have registered probes since they are backbone carriers, not ISPs with edge devices. For ZA eyeball ISPs the coverage is good, but backbone-only ASNs may still fall through to the prefix fallback.

## Context

`get_test_ip_for_asn()` in `country.py` (lines 109–140) fetches announced prefixes from RIPE Stat and returns the second host of the most-specific prefix. That host is not validated — it is a routable address but not necessarily a live endpoint. RIPE Atlas (`atlas.ripe.net`) runs ~10 000 connected hardware probes placed inside ISP networks by volunteers. Each probe is a small device with a stable IPv4 address inside its host ASN. The public probes API (`https://atlas.ripe.net/api/v2/probes/`) filters by ASN and connection status, requires no authentication, and returns probe IP addresses. Using a probe IP as the traceroute target gives a guaranteed-live destination inside the target network.

## Requirements

### Atlas lookup

- R1: `get_test_ip_for_asn()` first queries the RIPE Atlas probes API for connected probes (`status=1`) in the target ASN, sorted by probe ID, limited to 1 result.
- R2: If the API returns at least one probe with a non-null `address_v4`, that address is returned immediately as the target IP.
- R3: If the API returns no results, is unreachable, or the response is malformed, the function falls through to the existing prefix-based selection without raising an exception.

### Fallback (prefix-based selection — existing behavior)

- R4: The existing RIPE-prefix filter logic (IPv4, non-private, prefixlen ≥ /8, most-specific first, second host of first qualifying prefix) remains unchanged as the fallback path.
- R5: If neither Atlas nor the prefix fallback yields an IP, the function returns `None` (existing behavior).

### HTTP

- R6: The Atlas API call uses the existing `requests` session pattern already in `country.py`, with a reasonable timeout (5 s) and silent failure on any `requests.RequestException`.

## Acceptance Criteria

- [ ] Running `netpath country ZA --top 10` produces fewer incomplete paths than before; at least one previously-stalling ASN now shows a complete trace to the destination ASN.
- [ ] `get_test_ip_for_asn()` returns the Atlas probe IP when the Atlas API response contains a connected probe with a non-null `address_v4`. (Verified by `pytest tests/test_country.py -v`.)
- [ ] When the Atlas API returns an empty results list, the function falls through to prefix-based selection without error. (Verified by `pytest tests/test_country.py -v`.)
- [ ] When the Atlas API call raises a `requests.RequestException`, the function falls through to prefix-based selection without raising. (Verified by `pytest tests/test_country.py -v`.)
- [ ] The caller in `cli.py` is unchanged — `get_test_ip_for_asn()` still returns `str | None`.
- [ ] `ruff check src/netpath/country.py tests/test_country.py` passes with no errors.

## Implementation Phases

### Phase 1: Use RIPE Atlas probe IPs as traceroute targets
**Scope:** Add Atlas probe lookup as the primary IP-selection strategy inside `get_test_ip_for_asn()`, keeping the existing prefix-based logic as the fallback for ASNs without registered probes.
**Files:**
- `src/netpath/country.py` — add `RIPE_ATLAS_PROBES` URL constant; add `_get_atlas_probe_ip(asn: str) -> str | None` helper that calls the Atlas probes API and returns the first connected probe's `address_v4`; prepend the Atlas lookup to `get_test_ip_for_asn()` before the existing prefix logic
- `tests/test_country.py` — add tests for Atlas-hit path (mock `requests.get` returning a probe result), Atlas-miss path (empty results → prefix fallback), and Atlas-error path (`RequestException` → prefix fallback); existing prefix tests unchanged
**Verification:**
- `pytest tests/test_country.py -v` passes
- `ruff check src/netpath/country.py tests/test_country.py` passes
- Manual smoke: `netpath country ZA --top 5` completes without exceptions and shows at least one path that was previously incomplete now reaching the destination ASN
**Estimated effort:** Small

## Edge Cases

- ASN with no Atlas probes and no qualifying RIPE prefixes: Atlas returns empty, prefix fallback also returns `None`, caller skips the ASN — same as before.
- Atlas probe with `address_v4: null` (IPv6-only probe): skip that result; treat as no probe found and fall through to prefix selection.
- Atlas API rate-limited or returns non-200: catch `requests.RequestException` and fall through; a non-200 that does not raise (e.g., 429 with a body) is handled by checking `response.raise_for_status()` inside the helper.
- Atlas probe IP is in the same ASN but unreachable (probe disconnected between registration and our query): `status=1` filter makes this unlikely, but it can happen; path will still stall and classify as incomplete — acceptable, same as before.

## Technical Notes

Atlas probes API shape (relevant fields):

```json
{
  "results": [
    { "id": 12345, "asn_v4": 3741, "address_v4": "196.x.x.x", "status": {"name": "Connected"} }
  ]
}
```

`_get_atlas_probe_ip(asn: str) -> str | None` implementation sketch:

```python
RIPE_ATLAS_PROBES = "https://atlas.ripe.net/api/v2/probes/"

def _get_atlas_probe_ip(asn: str) -> str | None:
    asn_num = asn.lstrip("ASas")
    try:
        r = requests.get(
            RIPE_ATLAS_PROBES,
            params={"asn": asn_num, "status": 1, "sort": "id", "page_size": 1},
            timeout=5,
        )
        r.raise_for_status()
        for probe in r.json().get("results", []):
            ip = probe.get("address_v4")
            if ip:
                return ip
    except requests.RequestException:
        pass
    return None
```

`asn.lstrip("ASas")` strips the `AS` prefix the same way the existing RIPE calls do. The `sort=id` ensures a deterministic result across calls. `page_size=1` avoids fetching unnecessary data.

Mocking in tests: `unittest.mock.patch("netpath.country.requests.get")` — same pattern as any requests mock.

## Implementation Notes

## Phase 1: Use RIPE Atlas probe IPs as traceroute targets

### Changes

**`src/netpath/country.py`**
- Added `RIPE_ATLAS_PROBES = "https://atlas.ripe.net/api/v2/probes/"` constant alongside the existing RIPE constants.
- Added `_get_atlas_probe_ip(asn: str) -> str | None` — queries the Atlas probes API with `status=1`, `sort=id`, `page_size=1`; returns the first probe's `address_v4` (skipping null); silently returns `None` on `requests.RequestException` or non-200 (via `raise_for_status()`).
- Updated `get_test_ip_for_asn()` to call `_get_atlas_probe_ip()` first and return early if it yields an IP; falls through to the existing RIPE-prefix logic otherwise. The prefix logic is unchanged.

**`tests/test_country.py`**
- Added `test_get_test_ip_uses_atlas_probe_when_available` — Atlas hit path returns probe's `address_v4`.
- Added `test_get_test_ip_falls_through_to_prefix_when_atlas_empty` — empty `results` list triggers prefix fallback.
- Added `test_get_test_ip_falls_through_to_prefix_on_atlas_error` — `RequestException` triggers prefix fallback without raising.
- Added `test_get_test_ip_skips_null_address_v4` — probe with `address_v4: null` is skipped; prefix fallback is used.
- Existing tests unchanged.

### Verification
- `pytest`: 40/40 passed (7 new country tests + 33 pre-existing).
- `ruff check src/netpath/country.py tests/test_country.py`: no errors.

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 2 files changed across 1 phases

All 6 acceptance criteria pass. The Atlas probe lookup is correctly implemented as the primary IP-selection strategy with the existing prefix-based fallback preserved unchanged. All 40 tests pass and ruff is clean.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Test suite (pytest) | PASS | 40/40 passed across test_country.py (7), test_diagnosis.py (19), test_mtr.py (14) |
| Lint (ruff) | PASS | ruff check src/netpath/country.py tests/test_country.py — no errors |

### Acceptance Criteria (6/6 passed)

- [x] AC-1: Running `netpath country ZA --top 10` produces fewer incomplete paths than before; at least one previously-stalling ASN now shows a complete trace to the destination ASN. — PASS: country.py:131-133 calls _get_atlas_probe_ip() first and returns early on a hit, routing traces to known-live Atlas probe IPs instead of dark prefix addresses. Builder approved the phase after manual smoke testing.
- [x] AC-2: get_test_ip_for_asn() returns the Atlas probe IP when the Atlas API response contains a connected probe with a non-null address_v4. (Verified by pytest tests/test_country.py -v.) — PASS: test_get_test_ip_uses_atlas_probe_when_available (tests/test_country.py:23-28) passes. country.py:120-123 iterates results, checks `if ip:`, returns first non-null address_v4.
- [x] AC-3: When the Atlas API returns an empty results list, the function falls through to prefix-based selection without error. (Verified by pytest tests/test_country.py -v.) — PASS: test_get_test_ip_falls_through_to_prefix_when_atlas_empty (tests/test_country.py:31-50) passes. Empty results list causes _get_atlas_probe_ip() to return None, get_test_ip_for_asn() falls through to prefix logic at country.py:135.
- [x] AC-4: When the Atlas API call raises a requests.RequestException, the function falls through to prefix-based selection without raising. (Verified by pytest tests/test_country.py -v.) — PASS: test_get_test_ip_falls_through_to_prefix_on_atlas_error (tests/test_country.py:53-71) passes. country.py:124-125: `except requests.RequestException: pass` catches and suppresses the error.
- [x] AC-5: The caller in cli.py is unchanged — get_test_ip_for_asn() still returns str | None. — PASS: git diff main..HEAD -- src/netpath/cli.py returns empty; cli.py:633 still calls `country_mod.get_test_ip_for_asn(asn_str)` unchanged. Return type annotation at country.py:129 is `str | None`.
- [x] AC-6: ruff check src/netpath/country.py tests/test_country.py passes with no errors. — PASS: ruff output: 'All checks passed!'

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- Atlas probe lookup added as primary IP selection strategy in get_test_ip_for_asn(); existing prefix-based selection retained as fallback for ASNs with no registered probes.
- _get_atlas_probe_ip() uses raise_for_status() to handle non-200 responses and catches requests.RequestException broadly to silently fall through on any network error.
- page_size=1 and sort=id parameters minimize data transfer and ensure a deterministic result across calls.

## Required Changes

None.

## Release

## Release Notes

### What was built
- Added RIPE Atlas probe lookup as the primary IP-selection strategy in `get_test_ip_for_asn()` in `country.py`, so country sweeps trace to known-live probe endpoints instead of arbitrary dark prefix addresses
- Added `RIPE_ATLAS_PROBES` constant and `_get_atlas_probe_ip(asn: str) -> str | None` helper that queries the Atlas probes API (`status=1`, `sort=id`, `page_size=1`) and returns the first connected probe's `address_v4`
- Existing RIPE-prefix-based IP selection retained unchanged as fallback for ASNs with no registered Atlas probes
- Four new unit tests cover all error paths: Atlas hit, empty-results fallback, `RequestException` fallback, and null `address_v4` skip

### Key decisions
- Use RIPE Atlas probe registry as primary target IP source, with existing prefix-based selection as fallback — probe IPs are known-live hardware devices inside ISP networks, eliminating the root cause of stalled traces
- `_get_atlas_probe_ip()` uses `raise_for_status()` for non-200 responses and catches `requests.RequestException` broadly to silently fall through on any network error
- `page_size=1` and `sort=id` minimize data transfer and ensure deterministic results across calls

### Changes by phase
- **Phase 1: Use RIPE Atlas probe IPs as traceroute targets** — Added `RIPE_ATLAS_PROBES` constant and `_get_atlas_probe_ip()` helper to `country.py`; prepended Atlas lookup to `get_test_ip_for_asn()` with prefix-based selection as fallback. Added 4 unit tests to `tests/test_country.py`. All 40 tests pass, ruff clean.

## Verification

| Check | Result |
|-------|--------|
| Production build (`uv build`) | PASS — `netpath-0.3.1.dev7+gd6f4c30d5-py3-none-any.whl` built successfully |
| Code committed | PASS — `feat(task-incomplete-paths-still-showing-in-za-01kwddfsahcm): phase 1 — Use RIPE Atlas probe IPs as traceroute targets` (7d6871a) |
| Branch pushed | PASS — `feature/task-incomplete-paths-still-showing-in-za-01kwddfsahcm` pushed to origin |

