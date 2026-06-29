---
defract:
  id: task-country-as-path-visual-binat-rtt-anomaly-01kwaw3774eb
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

# Country AS-path visual + Binat RTT anomaly

## What We're Building

Two related improvements to the `country` subcommand. First, a bug fix: when a traceroute path never reaches the target ISP's network, the tool currently reports the RTT of the last transit router as if it were an in-country measurement — this produces misleadingly fast numbers (e.g. 26 ms when the true path is unreachable). Second, a new visual tree display groups destination ISPs by their shared transit entry point and color-codes each by latency, making it immediately clear which transit networks serve a country and which paths are actually verified.

## Expected Outcome

- ISPs whose paths never entered their own network are labeled as incomplete rather than showing a falsely low RTT from a mid-ocean transit router
- The country summary gains a tree view grouping ISPs under their shared network entry point (e.g. "reached via Lumen", "reached via Telia")
- Each ISP row shows a color-coded latency bar: green for fast (<120 ms), yellow for moderate (120–200 ms), red for slow (>200 ms), grey for incomplete
- Incomplete paths appear in a separate dimmed branch with a warning indicator rather than competing in the ranking
- A star marker and a footer line identify the single fastest verified entry point into the country

## Out of Scope

- Changes to how traceroute or iperf3 data is collected — this task is limited to classification and display logic
- Changes to the `asn` subcommand or its output format
- Adding JSON output mode to the `country` subcommand
