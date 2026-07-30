---
name: Issue Routing
description: Triages new issues, applies labels, and drafts a minimal repro test or implementation plan.
on:
  issues:
    types: [opened]
  roles: all
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
safe-outputs:
  add-labels:
    allowed: [bug, enhancement, question, documentation, needs-info]
    max: 3
  add-comment:
    max: 1
  create-pull-request:
    title-prefix: "[repro] "
    labels: [bug, needs-triage]
    draft: true
    allowed-files:
      - "tests/**"
    if-no-changes: "warn"
---

# Issue Routing

## Task

Triage the newly opened issue in this repository.

1. Read the issue body carefully. Classify it as one of: bug, enhancement, question, or documentation.
2. Check whether the description is clear enough to act on (steps to reproduce, expected vs. actual behavior, environment details for bugs). If it's unclear, post an `add-comment` asking targeted clarifying questions — do not label or open a PR until it's actionable.
3. If clear, identify the file(s) under `src/netpath/**` most likely responsible, based on the described symptom.
4. Apply `add-labels` for the classification. Only use labels from the allowed list — never invent new ones.
5. For a clear, reproducible **bug** report: draft a minimal failing test under `tests/**` that demonstrates the reported behavior (it should fail against the current code, proving the bug exists). Open it as a draft `create-pull-request` referencing the issue number. Do not attempt to fix the bug — only reproduce it.
6. For **enhancement**, **question**, or **documentation** issues, skip step 5. Instead post a brief `add-comment` with your assessment, and for enhancements, a short implementation-plan outline (relevant files, rough approach).
7. Call `noop` if the automatic triage above is already complete and nothing further is needed.

## Safe Outputs

- `add-labels` — classification label(s), max 3.
- `add-comment` — clarifying questions, or a triage/plan summary.
- `create-pull-request` — only for clear bug reports, draft, scoped to `tests/**` only, referencing the issue.
