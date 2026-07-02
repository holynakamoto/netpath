---
defract:
  id: task-netpath-review-mtr-fallback-host-lists-01kwjkby9hqw
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

# Netpath review fixes: mtr fallback, host lists, Globalping verdicts

## Story Brief

From chat: Netpath review: mtr fallback, host lists, Globalping verdicts (2026-07-02T23:39:05.722Z)

### Bugs

- **_check_deps() hard-exits when mtr absent, contradicting README's traceroute-fallback promise** — cli.py:152-156 _check_deps() calls raise typer.Exit(1) the moment mtr.available() is false, so `netpath country US --top 1 --no-throughput` exits 1 on a VM without mtr — even though _fallback_trace() (cli.py:159-167) and mtr.run_traceroute() already implement a working Paris/traceroute fallback. README claims mtr "falls back to traceroute if unavailable". The dependency gate should not require mtr when a fallback prober (paris.detect() or /usr/sbin/traceroute) is available; gate on "no path prober at all" instead.
  - Files: src/netpath/cli.py, README.md
- **traceroute fallback hardcodes /usr/sbin/traceroute path** — mtr.py:222 builds the command with a literal "/usr/sbin/traceroute". On Linux and many distros traceroute lives at /usr/bin/traceroute or elsewhere on PATH, so the permission-denied fallback fails outright on systems where the binary is not at that exact path. Should resolve via shutil.which("traceroute") (or PATH lookup) rather than a hardcoded absolute path.
  - Files: src/netpath/mtr.py
- **get_top_asns() materializes list(net.hosts()) per prefix just to read hosts[0]** — country.py:66-69 does hosts = list(net.hosts()) then uses only hosts[0]. For a large prefix (/8, /9) this allocates millions of IPv4Address objects per prefix. Replace with arithmetic: str(net.network_address + 1) (guarding /31 and /32 edge cases). Tiny change, removes a huge memory/time blast radius during country ranking. Note entries are already capped at 2000 via random.sample (country.py:58), but any single wide prefix still triggers the blowup.
  - Files: src/netpath/country.py
- **Remote-only Globalping rows never get a verdict, so they cannot affect exit code** — Remote-only summary rows are appended at cli.py:789-794 with only asn/name/remote_only/rum — no "verdict" key. The post-merge verdict recomputation at cli.py:916-925 is gated on `if _row.get("verdict")`, so diagnose() is never called for these rows. Result: a Globalping-only ISP can surface loss/jitter data but produce no diagnostic verdict and cannot raise the nonzero exit code (verdicts collected at cli.py:931 filter on row.get("verdict")). Fix: run diagnose() on remote-only rows once their remote metrics are merged, rather than only re-deriving when a verdict already exists.
  - Files: src/netpath/cli.py
- **fetch_probes() swallows 401 and reports invalid token as "no coverage"** — globalping.py:42-52 wraps the whole request in `except Exception: return []`, so an invalid-token 401 (raised by r.raise_for_status()) is indistinguishable from a genuinely empty probe list. The CLI then prints "No Globalping probes found in any target ASN" (cli.py:717), sending users to debug coverage when the real problem is auth. Fix: let 401/403 propagate or surface distinctly so the CLI can report "invalid Globalping token".
  - Files: src/netpath/globalping.py, src/netpath/cli.py
- **3,278 generated/venv paths tracked in git despite .gitignore entries** — .gitignore lists .venv/, __pycache__/, *.pyc, and _version.py, but git ls-files reports 3,278 tracked generated/venv paths — they were committed before the ignore rules or added with -f. _version.py is self-described as "don't track in version control" yet is tracked, and a stale tracked .venv path made uv rebuild the venv during review. Fix: git rm --cached the offending paths (bulk, keeping working copies) and commit, so .gitignore actually takes effect.
  - Files: .gitignore
- **RIPE Atlas only half-removed: atlas.py still exposes scheduling/key APIs README says were removed** — README claims the Atlas-backed measurement backend was "fully removed", but src/netpath/atlas.py still exists with live scheduling and key-based measurement APIs (schedule_measurements, parse_traceroute_as_path, etc. at atlas.py:99-278), and country.py:149 still describes Atlas probe targets in fallback. Either Atlas is genuinely gone (delete the dead measurement code + any tests and correct the fallback text) or it survives only as a live-target discovery fallback (rename/document that narrower boundary). Right now the code and the README disagree.
  - Files: src/netpath/atlas.py, src/netpath/country.py, README.md

Originating chat: Netpath review: mtr fallback, host lists, Globalping verdicts (232a41e0-7baa-4071-8e33-fccfc67a2c2e)

## What We're Building

A batch of seven fixes surfaced by a code review of netpath. The tool will honour its documented promise to keep working when the preferred path prober is not installed, country sweeps will stop wasting large amounts of memory when ranking providers, providers measured only through remote probes will receive proper health verdicts, an invalid remote-probing token will be reported as an authentication problem instead of missing coverage, thousands of generated files will stop being tracked in version control, and the documentation will be brought back in line with what the code actually does regarding the removed Atlas measurement backend.

## Expected Outcome

- Probing a country or a specific network succeeds on machines without mtr installed, falling back to traceroute as the documentation promises — and the fallback works regardless of where traceroute is installed on the system
- Country sweeps rank providers without stalling or consuming excessive memory when a provider announces very large address blocks
- Providers measured only through remote Globalping probes receive a health verdict and count toward the exit code, the same as locally measured providers
- Supplying an invalid Globalping token produces a clear authentication error instead of a misleading "no probes found" message
- Generated and virtual-environment files are no longer tracked in version control, so ignore rules actually take effect
- The documentation and the code agree on what remains of the removed RIPE Atlas measurement backend

## Phase Outcomes

- **Phase 1: Behaviour fixes for probing, ranking, and remote verdicts** — Users on machines without the preferred prober can still run measurements, country rankings no longer waste memory on large address blocks, remotely measured providers get real health verdicts that affect the exit code, and a bad token is reported as an authentication problem.
- **Phase 2: Retire the dead Atlas measurement code and reconcile the docs** — The leftover code from the removed Atlas measurement backend is deleted so the codebase matches what the documentation promises, preventing confusion for future contributors.
- **Phase 3: Stop tracking generated and virtual-environment files** — Version control stops carrying thousands of machine-generated files, making the repository smaller, diffs cleaner, and local tooling more reliable.

## Out of Scope

- No new measurement capabilities, probes, or backends — this task strictly fixes existing behaviour and cleans up inconsistencies
- Re-introducing Atlas-backed measurements is not included; the fix only reconciles the code and documentation with the removal decision already made
- No broader redesign of the Globalping integration beyond verdict computation and authentication error reporting

## Scope Summary

**Size:** 14 requirements, 12 acceptance criteria, 3 implementation phases
**Key decisions:**
- Delete `atlas.py` outright rather than keep it as a narrower module — nothing in production imports it; the keyless live-target discovery in `country.py` calls the public Atlas API directly and is unaffected
- Surface Globalping auth failure via a distinct exception from `fetch_probes()` rather than a sentinel return value, mirroring the 401 handling that already exists for measurement scheduling
- Isolate the bulk git-untracking into its own phase so the thousands-of-deletions diff does not drown the code-fix review
**Biggest risk:** `diagnose()` has never been exercised on a row that contains only remote Globalping metrics (no local trace, no hubs); it must produce a sensible verdict on that shape without regressing locally measured rows.

## Context

A code review of netpath surfaced seven defects across the CLI dependency gate, the traceroute fallback, country ranking, the Globalping integration, git hygiene, and the Atlas removal. The fallback machinery already exists and works: `_fallback_trace()` (src/netpath/cli.py:159-167) prefers a Paris prober via `paris.detect()` and falls back to `mtr.run_traceroute()` — but `_check_deps()` (cli.py:152-156) hard-exits before it can ever run, and `_trace()` (cli.py:170-174) only reaches the fallback on `MtrPermissionError`, not on mtr being absent. Codebase exploration confirmed that `src/netpath/atlas.py` is imported only by `tests/test_atlas.py` — no production module uses it; the keyless trace-target discovery in `country.py` (`_get_atlas_probe_ip`, country.py:110-136) queries the public Atlas probes API directly without a key and without importing atlas.py. The CLI already reports a 401 distinctly when *scheduling* Globalping measurements (cli.py:849-855); only the earlier `fetch_probes()` inventory call swallows it.

## Requirements

### Prober fallback (bugs 1 and 2)

- R1: Running `netpath asn` or `netpath country` on a machine without mtr proceeds using the fallback prober instead of exiting. (`_check_deps()` at cli.py:152-156 exits only when no prober exists at all: `mtr.available()` is false AND `paris.detect()` is None AND no traceroute binary can be resolved.)
- R2: When mtr is absent, the trace path routes directly to the fallback prober rather than attempting to run mtr. (`_trace()` at cli.py:170-174 currently reaches `_fallback_trace()` only via `MtrPermissionError`; it must also branch on `mtr.available()` being false, or catch the resulting `FileNotFoundError`.)
- R3: When falling back because mtr is missing, the user sees a one-line notice naming the prober actually used, so degraded path detail (mtr's richer stats vs traceroute's) is not silent.
- R4: The traceroute binary is resolved via PATH lookup instead of a hardcoded absolute path, with `/usr/sbin/traceroute` retained as a last-resort candidate for macOS environments where `/usr/sbin` is not on PATH. (`_run_traceroute_cmd()` at mtr.py:222; resolve once via `shutil.which("traceroute")`, falling back to an existence check on `/usr/sbin/traceroute`, and raise a clear error naming the missing binary when neither resolves.)
- R5: The error message shown when no prober exists at all names both install options (e.g. mtr via brew/apt, or traceroute), replacing the current mtr-only message at cli.py:154.

### Country ranking memory (bug 3)

- R6: Sampling one representative address per announced prefix during country ranking uses constant memory regardless of prefix size. (country.py:66-69: replace `list(net.hosts())` with `str(net.network_address + 1)` arithmetic; for /31 and /32 use the network address itself; `ip_to_size` keeps using `net.num_addresses` unchanged.)

### Globalping verdicts and auth (bugs 4 and 5)

- R7: Remote-only summary rows receive a diagnostic verdict once their Globalping metrics are merged, so they render a verdict in the summary table and contribute to the exit code. (cli.py:916-925: run `diagnose()` on rows where Globalping loss/jitter data landed, whether or not the row already has a verdict; the exit-code collection at cli.py:931 then picks them up with no further change.)
- R8: `diagnose()` produces a sensible verdict for a row containing only remote metrics and optional RUM data — no hubs, no local trace, no throughput — without crashing and without spurious signals from absent local probes.
- R9: An invalid Globalping token is reported as an authentication failure at the probe-inventory step, not as missing coverage. (`fetch_probes()` at globalping.py:40-52 raises a distinct auth error on HTTP 401/403 instead of returning `[]`; the caller at cli.py:699 catches it and prints a message consistent with the existing scheduling-time 401 wording at cli.py:849-855.)
- R10: Non-auth failures of the probe inventory (timeouts, 5xx) keep the current graceful behaviour of skipping remote measurements.

### Repository hygiene (bug 6)

- R11: All tracked paths matching the existing .gitignore rules (`.venv/`, `__pycache__/`, `*.pyc`, `src/netpath/_version.py`) are removed from git tracking while keeping the working copies on disk, in a single dedicated commit. (`git rm -r --cached` on the offending paths; `git ls-files` afterwards reports none of them.)

### Atlas reconciliation (bug 7)

- R12: `src/netpath/atlas.py` is deleted along with `tests/test_atlas.py`, its only importer. Production behaviour is unchanged — no production module imports atlas.py.
- R13: The keyless Atlas-based trace-target discovery that remains (`_get_atlas_probe_ip` in country.py) is documented as exactly that: a public, no-key lookup of a live probe address used only as a trace target. (Docstrings around country.py:110-158 and the fallback-origin wording; the "Atlas probe trace target" display strings at cli.py:759, 798, 800 stay, as they accurately describe this surviving lookup.)
- R14: The README statement that the Atlas measurement backend is "fully removed" (README.md:165) becomes true, and a sentence clarifies that a public keyless Atlas probe lookup survives solely for discovering live trace targets. The traceroute-fallback claim at README.md:23 is verified accurate against the fixed gate behaviour.

## Acceptance Criteria

- [ ] With mtr unavailable but traceroute present, `netpath country US --top 1 --no-throughput` runs to completion instead of exiting 1; verified by a test monkeypatching `mtr.available` to False, or manually on a VM without mtr
- [ ] With mtr, a Paris prober, and traceroute all unavailable, the CLI exits 1 with an error naming the install options for both mtr and traceroute
- [ ] `src/netpath/mtr.py` contains no hardcoded `"/usr/sbin/traceroute"` literal in the command construction; the binary is resolved via `shutil.which` with `/usr/sbin/traceroute` only as an existence-checked fallback
- [ ] `country.py` no longer calls `list(net.hosts())`; a unit test in `tests/test_country.py` covers first-host derivation for a normal prefix, a /31, and a /32
- [ ] A summary row shaped like a remote-only Globalping row (asn/name/remote_only plus merged loss/jitter metrics, no hubs) passed through `diagnose()` returns a verdict dict without raising; covered by a test in `tests/test_diagnosis.py`
- [ ] A country run where a remote-only ASN shows Globalping loss above the critical threshold exits non-zero (verdict reaches the exit-code collection at cli.py:931)
- [ ] `fetch_probes()` raises a distinct auth error on HTTP 401/403 and still returns `[]` on other failures; covered by a test mocking the HTTP layer
- [ ] Supplying an invalid Globalping token to `netpath country` prints an authentication-failure message, not "No Globalping probes found in any target ASN"
- [ ] `git ls-files` reports zero paths under `.venv/`, zero `__pycache__/` or `*.pyc` paths, and does not include `src/netpath/_version.py`; the working copies remain on disk
- [ ] `src/netpath/atlas.py` and `tests/test_atlas.py` no longer exist; `grep -r "netpath.atlas\|from .atlas" src tests` returns nothing
- [ ] README accurately describes both the traceroute fallback and the surviving keyless Atlas target-discovery lookup
- [ ] `pytest` and `ruff check src tests` pass after each phase

## Implementation Phases

### Phase 1: Behaviour fixes for probing, ranking, and remote verdicts
**Scope:** Fixes the five runtime defects: measurements proceed without the preferred prober installed, the fallback prober is found wherever it is installed, country ranking stops allocating memory proportional to address-block size, remotely measured providers receive health verdicts that affect the exit code, and an invalid remote-probing token is reported as an authentication error.
**Files:** src/netpath/cli.py (`_check_deps`, `_trace`, remote-only verdict recomputation, fetch_probes call site), src/netpath/mtr.py (`_run_traceroute_cmd` binary resolution), src/netpath/country.py (first-host arithmetic in `get_top_asns`), src/netpath/globalping.py (`fetch_probes` auth error), src/netpath/diagnosis.py (only if remote-only rows need guarding), tests/test_country.py, tests/test_diagnosis.py, tests/test_globalping.py, README.md (only if the fallback wording needs a touch-up)
**Verification:**
- `pytest` passes, including new tests for first-host derivation (/24, /31, /32), remote-only `diagnose()` rows, and `fetch_probes` 401 vs other failures
- `netpath country US --top 1 --no-throughput` with `mtr.available` forced False completes using the fallback prober and prints the fallback notice
- No `list(net.hosts())` call remains in country.py; no `"/usr/sbin/traceroute"` literal remains in the mtr.py command builder
- `ruff check src tests` passes
**Estimated effort:** Medium

### Phase 2: Retire the dead Atlas measurement code and reconcile the docs
**Scope:** Deletes the leftover measurement backend from the earlier Atlas removal and updates the documentation so code and README tell the same story, including how live trace targets are still discovered.
**Files:** src/netpath/atlas.py (delete), tests/test_atlas.py (delete), src/netpath/country.py (docstring wording for `_get_atlas_probe_ip` / `get_test_target_for_asn`), README.md (Atlas removal note and surviving keyless lookup)
**Verification:**
- `src/netpath/atlas.py` and `tests/test_atlas.py` are gone; `grep -r "netpath.atlas\|from .atlas" src tests` is empty
- `pytest` passes with the deleted test file absent
- README section on the removed backend mentions the surviving keyless probe-address lookup
- `ruff check src tests` passes
**Estimated effort:** Small

### Phase 3: Stop tracking generated and virtual-environment files
**Scope:** Removes the thousands of generated and virtual-environment files from version control in one dedicated commit so the existing ignore rules take effect, keeping all working copies on disk.
**Files:** No source edits — a bulk `git rm -r --cached` over tracked paths matching `.venv/`, `__pycache__/`, `*.pyc`, and `src/netpath/_version.py`; .gitignore itself already lists the right rules and likely needs no change
**Verification:**
- `git ls-files | grep -E "\.venv/|__pycache__|\.pyc$|_version\.py"` returns nothing
- The working tree still contains the files (`.venv/` intact, editable install still works)
- `git status` is clean after the commit; `pytest` still passes
**Estimated effort:** Small

## Edge Cases

- **mtr absent AND paris absent AND traceroute absent**: the gate exits 1 with the combined install message — the only remaining hard-exit path
- **mtr present but lacking raw-socket permission**: existing `MtrPermissionError` fallback path must keep working unchanged alongside the new mtr-absent branch
- **/31 and /32 prefixes in RIPE data**: `net.hosts()` semantics differ (a /32 has one host, `network_address + 1` would leave the prefix); use the network address itself for prefixlen >= 31
- **IPv6-mapped or malformed prefix strings**: the existing `except ValueError: continue` in the sampling loop must keep swallowing them
- **Remote-only row where Globalping times out**: no loss/jitter metrics merge, so no verdict is computed — the row stays verdict-less and excluded from the exit code, matching today's skipped-ASN convention
- **Remote-only row with RUM data but no Globalping metrics**: also stays verdict-less; RUM alone has no diagnostic thresholds today and inventing them is out of scope
- **401 from Globalping with no token supplied**: should not happen (anonymous access is allowed), but if it does, the auth message must not tell the user their nonexistent token is invalid — word the message to cover both cases or gate on token presence
- **Case-variant traceroute environments (BSD vs Linux flags)**: only binary *location* changes; the flag set at mtr.py:222 stays as-is since flag portability is not part of this task
- **`git rm --cached` on paths with spaces or unusual names inside .venv**: use pathspec/batch invocation robust to such names (e.g. `git rm -r --cached .venv src/netpath/_version.py` plus pattern-based removal for scattered `__pycache__` dirs)

## Technical Notes

- `_trace()` (cli.py:170-174) is the single choke point for the mtr-absent branch: check `mtr.available()` once before attempting `mtr.run()`, or catch `FileNotFoundError` — prefer the availability check since `mtr.available()` (mtr.py:57-58, `shutil.which`) is already the established pattern. Cache the resolved prober decision rather than re-running `shutil.which` per hop-trace in a country sweep.
- `_check_deps()` gains a "no prober at all" condition: `not mtr.available() and paris.detect() is None and <traceroute unresolvable>`. Expose the traceroute resolution from mtr.py (e.g. a small `mtr.traceroute_available()` or a resolver function returning the path) so cli.py does not duplicate the which/`/usr/sbin` logic that R4 adds.
- `diagnose()` (diagnosis.py) already runs on merged rows that had local measurements plus Globalping data; the new call site feeds it rows lacking `hubs`, `as_path`, and throughput keys entirely. `MeasurementResult` is `total=False` and access is via `.get()`, so absent keys are representable — but verify none of the nine signal checks misfire on absent-vs-failed distinctions (e.g. a missing trace must not be reported as an incomplete path, and `probe_errors` is absent on these rows). Rate-limited-hop and path checks should simply find nothing to evaluate.
- For the auth error, define an exception in globalping.py (e.g. `class GlobalpingAuthError(RuntimeError)`) raised from `fetch_probes()` when `r.raise_for_status()` yields an `requests.HTTPError` with `response.status_code in (401, 403)`; all other exceptions keep the `return []` contract. The call site (cli.py:699) wraps the fetch in try/except and reuses the wording pattern of the existing scheduling-time 401 message (cli.py:849-855).
- The first-host arithmetic in country.py must stay inside the existing `try/except ValueError` block; `net.network_address + 1` on an `IPv4Network` returns an `IPv4Address`, so `str()` conversion matches the current `str(hosts[0])` output exactly for prefixes /30 and wider.
- Phase 3 is deliberately last and isolated: its diff is thousands of index-only deletions and would bury the Phase 1/2 review if combined. It touches no Python source, so a broken rebase risk is minimal; `.gitignore` already contains the correct rules (verified — 7 lines, all four patterns present).
- Test placement follows the established strategy (pure functions and mockable modules): new tests go in tests/test_country.py, tests/test_diagnosis.py, and tests/test_globalping.py, all of which exist.

### Dependencies

Phase 2 should land after Phase 1 only because both edit README.md and country.py — no functional dependency. Phase 3 is independent of both.
