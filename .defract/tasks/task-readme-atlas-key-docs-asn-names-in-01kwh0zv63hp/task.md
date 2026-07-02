---
defract:
  id: task-readme-atlas-key-docs-asn-names-in-01kwh0zv63hp
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

# README atlas-key docs + ASN names in trace/AS-path display

# README atlas-key docs + ASN names in trace/AS-path display

## What We're Building

Two usability improvements: first, adding missing README documentation for the `--atlas-key` option (RIPE Atlas integration) and the `--globe` flag — covering how to supply the key, what the output looks like when Atlas probes are found, and what the fallback message means when no probes exist in the target ASNs; second, enriching the traceroute display so ASN organization names appear alongside ASN numbers — users will see `AS209 (Lumen)` instead of bare `AS209` in both the hop-by-hop trace table and the AS path summary line.

## Expected Outcome

- The README contains a "RIPE Atlas" section documenting how to supply the key via `NETPATH_ATLAS_KEY` or `--atlas-key <KEY>` inline, mirroring the existing Cloudflare Radar section
- The README explains what the `[Atlas]` sub-rows in the summary table mean (RTT and outbound AS path from probe measurements) and why "No Atlas probes found" appears when the target ASNs have no registered probes
- The country command's options block in the README lists both `--atlas-key` and `--globe` (currently omitted)
- The traceroute hop table's ASN column shows numbers with organization names, e.g. `AS209 (Lumen)`
- The AS path summary line shows named ASNs, e.g. `AS209 (Lumen) → AS3356 (Level 3) → ...`
- ASN names are included in `--json` output per hub at no extra cost

## Out of Scope

- Adding a bare `--atlas` boolean flag or changing how `--atlas-key` parses its argument (the current value-option design is intentional)
- Changes to what RIPE Atlas measurements are performed or when they are triggered
- Expanding documentation beyond README (man pages, `--help` text rewrites)
