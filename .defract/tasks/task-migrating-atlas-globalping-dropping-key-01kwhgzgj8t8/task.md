---
defract:
  id: task-migrating-atlas-globalping-dropping-key-01kwhgzgj8t8
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

# Migrate from RIPE Atlas to Globalping and drop the API key requirement

## Story Brief

From chat: Migrating Atlas → Globalping + dropping key requirement (2026-07-02). The builder chose a full replacement: delete the Atlas backend and all its wiring, make Globalping the sole in-network measurement backend for zero-config operation. Accepted trade-offs: smaller probe network, no anchor fallback (Globalping has no anchor class), renaming the atlas-profile command, and rewriting the README's RIPE Atlas section. An optional token may be kept for a higher rate-limit tier, but no key is required by default.

## What We're Building

Today, measuring network paths from vantage points inside the target networks requires a RIPE Atlas account, an API key, and a credit balance — a setup hurdle that stops most users before they see any value. This task replaces that backend with Globalping, a free service that needs no account or key, so in-network measurements and the coverage report work out of the box for everyone.

## Expected Outcome

- Users can run in-network path measurements and country sweeps without creating an account, obtaining a key, or managing a credit balance
- The probe-coverage report works with zero configuration, showing where measurement vantage points are available
- Users who want higher usage limits can optionally supply a token, but nothing requires one
- Documentation describes the new service and no longer mentions API keys or credits as a prerequisite
- Error messages and command names no longer reference the old service

## Out of Scope

- Keeping the old RIPE Atlas backend as an alternative or fallback — this is a full replacement, and the recently added anchor-based coverage boost goes away with it (the new service has no equivalent, by accepted trade-off)
- Publishing a new release to the package index and cleaning up the builder's local install — that is a separate release runbook, not part of this change
- Any changes to the local measurement features (traceroute, throughput, latency probes run from the user's own machine) — only the remote in-network measurement backend changes