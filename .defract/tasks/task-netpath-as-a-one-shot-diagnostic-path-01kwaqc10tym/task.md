---
defract:
  id: task-netpath-as-a-one-shot-diagnostic-path-01kwaqc10tym
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

# netpath as a One-Shot Diagnostic Path CLI

## What We're Building

We are transforming netpath from a metrics-display tool into a genuine "what's wrong right now" diagnostic instrument. The upgraded tool will measure the full picture of a network path — throughput, latency under load, jitter, and hop-by-hop loss — and then synthesize those measurements into a plain-language verdict that identifies where in the path the problem is and what kind of failure it is.

## Expected Outcome

- Running `netpath asn <ASN>` produces a structured diagnosis: a clear verdict naming the failure mode (last-mile congestion, mid-path loss, throughput cap, etc.) rather than a raw metrics dump
- Results are available in machine-readable JSON (`--json` flag), so network engineers can pipe netpath output into other tools or scripts without screen-scraping
- Latency is reported with richer statistics (median, p95, p99) in addition to avg/best/worst, giving a more accurate picture of real-world user experience
- Bufferbloat is detected and reported: the tool shows how much latency increases during an active transfer, which is the metric network engineers most associate with real congestion
- The tool remains a single command with no setup, no persistent storage, and no daemon — run once, get an answer

## Out of Scope

- Continuous monitoring, scheduled runs, or time-series storage — this tool diagnoses a single moment, not trends over time
- Prometheus, InfluxDB, or any metrics-export integration — structured output stops at `--json`
- ECMP-aware multi-path discovery and IPv6 dual-stack testing — high-value but deferred to a follow-up task to keep this scope bounded
