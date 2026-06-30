---
defract:
  id: task-ways-to-improve-netpath-01kwc564vewr
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

# Ways to Improve Netpath

## What We're Building

Three targeted improvements that make netpath more reliable and scripting-friendly: a test suite covering the most fragile parsing and verdict logic with a GitHub Actions CI workflow, a refactor that separates measurement from display in the core test function, and exit codes that reflect diagnosed network health so netpath can participate in monitoring pipelines.

## Expected Outcome

- Running `netpath asn` or `netpath country` on a path with diagnosed issues exits with a non-zero code (1 for warning, 2 for critical), making netpath usable in shell scripts and alerting setups
- A test suite validates the traceroute parser, verdict classifier, and related pure functions on every pull request across Python 3.9 through 3.13
- Developers install all development tools (pytest, ruff) with a single `pip install -e ".[dev]"` step
- The core test function has a clear internal boundary between the code that measures network state and the code that renders it, reducing the risk of silent regressions when either side changes

## Out of Scope

- Adding `--json` output to the `country` subcommand (enabled by the refactor but a follow-on change)
- New CLI subcommands, flags, or user-visible features beyond exit-code behavior
- Performance improvements to measurement speed or parallelism
