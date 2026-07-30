---
name: Dependency & Vulnerability Triage
description: Validates Dependabot version-bump PRs against actual codebase usage and test results.
on:
  pull_request:
    types: [opened, synchronize]
    paths:
      - "pyproject.toml"
      - "uv.lock"
  bots: ["dependabot[bot]"]
engine: copilot
model: gpt-5
permissions:
  contents: read
  issues: read
  pull-requests: read
  copilot-requests: write
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
network:
  allowed:
    - defaults
    - python
safe-outputs:
  add-comment:
    max: 1
  add-labels:
    allowed: [dependency-validated, needs-review]
    max: 2
---

# Dependency & Vulnerability Triage

## Task

This PR was opened by Dependabot, bumping one or more dependencies in `pyproject.toml` / `uv.lock`.

1. Identify exactly which package(s) changed and the old→new version(s) from the diff.
2. Check actual usage of the changed package(s) in `src/netpath/**` (imports, API calls) to assess whether the bump touches code paths this project actually exercises.
3. If the PR description or a linked advisory references a CVE/GHSA, summarize its real impact on this codebase — is the vulnerable code path actually used here, or not applicable?
4. Run the test suite: `pip install -e ".[dev]"` then `pytest`. Capture pass/fail and any relevant failure output.
5. Post one `add-comment` summarizing: package(s) + version delta, CVE relevance (if any), and the test result.
6. Add label `dependency-validated` if tests pass and there are no compatibility concerns. Add `needs-review` instead if tests fail, it's a major version bump, or the CVE-relevant code path is actually exercised by this project.
7. Never modify code, push commits, or alter the PR itself beyond the comment and label — this workflow only validates and reports.

## Safe Outputs

- `add-comment` — one validation summary per run.
- `add-labels` — exactly one of `dependency-validated` or `needs-review`.
