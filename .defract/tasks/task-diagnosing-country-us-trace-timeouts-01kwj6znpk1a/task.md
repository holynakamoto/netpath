---
defract:
  id: task-diagnosing-country-us-trace-timeouts-01kwj6znpk1a
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

## Story Brief

# Trace only valid probe targets in country mode

## What We're Building

Country sweeps currently guess an address inside each ISP's network when no real test server exists, and those guessed addresses usually do not answer — producing long timeouts and empty results for large ISPs. We are changing the sweep so it only measures against targets known to be alive (a real test server or a live measurement probe), and clearly marks ISPs that have no usable target as "no coverage" instead of waiting on a dead host. When a trace does time out, the partial path collected so far is shown instead of a bare error.

## Expected Outcome

- Country sweeps no longer stall on ISPs whose guessed address never answers; the four US ISPs that previously timed out either get a live target or are skipped quickly
- Each ISP is measured against the best available live target: a real test server first, then a live probe address, then remote-only probe measurements when only remote coverage exists
- ISPs with no live target at all are labelled "no coverage" and skipped, rather than reported as a timeout failure
- When a trace does time out, the hops collected before the timeout are still displayed so the run produces useful partial data
- Overall run verdicts and exit codes are no longer skewed by unreachable guessed addresses

## Out of Scope

- A new batch mode that sweeps the top 50 countries ranked by allocated address space — a substantial feature that deserves its own task
- Any change to the one-time baseline speed test in country mode — its recent failure was a transient network issue on the tester's connection, not a defect
- Installing or bundling the mtr path-probing tool; the sweep continues to work with whichever prober is available on the machine
