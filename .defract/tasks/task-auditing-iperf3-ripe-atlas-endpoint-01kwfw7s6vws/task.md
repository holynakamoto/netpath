---
defract:
  id: task-auditing-iperf3-ripe-atlas-endpoint-01kwfw7s6vws
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

# Auditing iperf3 + RIPE Atlas endpoint validity

## What We're Building

Two complementary improvements to how netpath selects and measures endpoints. First, we are fixing two bugs in the iperf3 server selection logic that cause country sweeps to silently skip valid servers and accept broken ones as healthy. Second, we are adding an opt-in RIPE Atlas measurement mode that schedules real traceroute and ping measurements from probes physically located inside each target network, replacing today's single-vantage outbound view with a true multi-region picture of each ISP's path characteristics.

## Expected Outcome

- Country sweeps consistently find and use working iperf3 servers rather than skipping valid ones because dead servers appeared first in the list
- Servers that accept a connection but cannot complete an iperf3 test are rejected during validation rather than being counted as healthy
- Users with a RIPE Atlas API key can run a country sweep and receive path data measured from inside each target network, not just from their own vantage point
- Each target network's paths are characterized from two directions: traffic leaving the ISP and traffic arriving at the ISP from the rest of the country
- Country sweeps that exceed the user's Atlas credit budget are refused or trimmed before any credits are spent
- The tool exits gracefully when a target network has no Atlas probes available, recording the gap without failing the whole sweep

## Out of Scope

- Changes to single-ASN probe mode — only the country sweep gains the Atlas measurement path
- Scheduling Atlas measurements toward targets outside the country being swept
- A separate "fetch results later" command — Atlas polling runs inline within the same sweep command
