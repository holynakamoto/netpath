---
defract:
  id: task-netpath-review-mtr-fallback-host-lists-01kwjkby9hqw
  type: bug
  status: active
  stage: scope
  phase: 0
  total_phases: 1
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

## Out of Scope

- No new measurement capabilities, probes, or backends — this task strictly fixes existing behaviour and cleans up inconsistencies
- Re-introducing Atlas-backed measurements is not included; the fix only reconciles the code and documentation with the removal decision already made
- No broader redesign of the Globalping integration beyond verdict computation and authentication error reporting