---
defract:
  id: task-scoring-the-za-country-sweep-output-01kwf9mr4338
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

## Out of Scope

- No changes to how country sweeps select, rank, or filter ASNs
- No changes to the iperf3 server list format or sourcing — validation happens at runtime, not at list-build time
- No new CLI flags or user-facing configuration options
