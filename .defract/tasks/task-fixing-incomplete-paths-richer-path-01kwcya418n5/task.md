---
defract:
  id: task-fixing-incomplete-paths-richer-path-01kwcya418n5
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

# Fixing incomplete paths + richer path metrics

## What We're Building

Three targeted improvements to netpath's path analysis accuracy. First, fix a false-positive "Mid-path Packet Loss" warning that fires on healthy paths crossing ICMP rate-limited transit routers — currently it produces spurious warnings and non-zero exit codes on routes that have no actual loss. Second, make incomplete path reports meaningful by surfacing where the trace stalled and the last measured RTT, rather than a flat "incomplete" label that discards data already collected. Third, improve end-to-end path completion in `country` mode by selecting smarter destination IPs and preferring TCP-based probing for hosts that filter ICMP.

## Expected Outcome

- Paths that cross ICMP rate-limited transit hops no longer produce packet loss warnings or non-zero exit codes when there is no genuine end-to-end loss
- Incomplete path reports show the stall point (transit ASN + hop number) and last measured RTT instead of an uninformative "incomplete" label
- More `country` mode paths complete end-to-end due to smarter destination IP selection and TCP-443 probing as a primary option
- Network operators can distinguish a rate-limited transit router from real packet loss without manually cross-referencing downstream hops

## Out of Scope

- Advanced metric additions such as jitter/IPDV, PMTU black-hole detection, TCP/TLS application latency measurement, IPv6/dual-stack path comparison, and route stability/flap detection (separate follow-on improvements)
- Paris/Dublin ECMP-aware traceroute mode (separate investigation with broader impact)
- Statistical loss confidence improvements requiring more probe cycles (separate task)
