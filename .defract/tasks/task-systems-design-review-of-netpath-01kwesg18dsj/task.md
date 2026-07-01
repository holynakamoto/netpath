---
defract:
  id: task-systems-design-review-of-netpath-01kwesg18dsj
  type: improvement
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

# Systems-design review of netpath

## What We're Building

A structural overhaul of netpath addressing six architectural problems identified in a design review: measurement logic tangled into the CLI layer, a diagnostic engine that reports only the first problem found instead of all of them, silently swallowed probe failures that make a "Healthy" verdict untrustworthy, fragile untyped data contracts, hand-rolled concurrency that leaks processes on timeout, and missing retry/caching for external service calls. The goal is a codebase where each concern lives in its own layer, failures are visible, and both probe modes (ASN and country) share the same full feature set.

## Expected Outcome

- When a path has multiple problems simultaneously — bufferbloat, mid-path loss, high jitter — all of them appear in the report instead of only the first one detected
- A "partial results" indicator appears when one or more probes fail silently, so a clean "Healthy" verdict is trustworthy rather than ambiguous
- Country-mode sweeps get the same full probe set as ASN mode — ECMP detection, IPv6 comparison, PMTU, and TCP/TLS latency no longer silently absent in country scans
- Independent probes run concurrently instead of sequentially, reducing total wall-clock time per target
- Transient failures in external lookups (BGP origin data, iperf3 server lists) are retried automatically and do not silently drop data

## Out of Scope

- New probe types or network metrics not already implemented in the codebase
- Changes to the command-line interface, flag names, or output format visible to users
- On-disk caching, persistent configuration, or anything that requires writing state between runs
