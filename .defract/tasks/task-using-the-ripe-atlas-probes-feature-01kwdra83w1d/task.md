---
defract:
  id: task-using-the-ripe-atlas-probes-feature-01kwdra83w1d
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

# Improve RIPE Atlas probe selection and traceroute depth in country mode

## What We're Building

When `netpath country <CC>` sweeps a country's top ASNs, it picks a target IP per ASN using the RIPE Atlas API. Today it grabs the first connected probe, which is often a home router or NAT device that drops ICMP — causing traces to stall short of the destination ASN. A separate problem is that the traceroute fallback is hard-capped at 15 hops, which clips intercontinental paths before they reach their target. This task fixes both: it makes probe selection smarter (preferring Atlas anchors, which are well-connected hosted probes), raises the hop cap to 30, and ensures paths that stop short of the target ASN are flagged as incomplete rather than scored as "Healthy."

## Expected Outcome

- Country sweeps to distant regions produce more complete paths that actually reach the target ASN
- Paths that stop short of the target ASN are visibly flagged as incomplete in the output, not silently scored as Healthy
- The traceroute fallback no longer clips intercontinental paths at 15 hops
- RIPE Atlas anchor probes are tried first, providing more reliable and reachable target IPs
- When no anchor is available, the tool falls back gracefully to regular probes or the prefix-based target

## Out of Scope

- Scheduling actual RIPE Atlas measurements via the measurements API (requires an API key and measurement credits — a separate integration)
- Median latency or throughput display improvements
- Changes to the `asn` subcommand
