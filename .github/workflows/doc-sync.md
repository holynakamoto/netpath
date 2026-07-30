---
name: Documentation Sync
description: Keeps README.md and docs/**/*.md in sync when a PR changes CLI flags or public API surface.
on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - "src/netpath/cli*.py"
      - "pyproject.toml"
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
  push-to-pull-request-branch:
    allowed-files:
      - "README.md"
      - "docs/**/*.md"
    if-no-changes: "warn"
  add-comment:
    max: 1
---

# Documentation Sync

## Task

This PR changes `src/netpath/cli*.py` or `pyproject.toml` — files that define CLI flags, public API surface, or configuration schema.

1. Diff this PR's branch against its base to see exactly what changed: new/removed/renamed CLI flags, options, arguments, or config fields.
2. Check `README.md` and any relevant files under `docs/**/*.md` for documentation of the changed behavior.
3. If the docs are stale, incomplete, or missing the new/changed behavior, update them to match. Edit minimally and precisely — keep the existing structure, tone, and formatting conventions of the file you're editing.
4. Push the updated docs to this PR's branch via `push_to_pull_request_branch`.
5. Post one `add-comment` summarizing what was updated (or confirming no changes were needed).
6. If the docs already accurately describe the new behavior, call `noop` explaining why no changes were needed. Do not push a no-op commit.

## Safe Outputs

- `push_to_pull_request_branch` — only touch `README.md` and `docs/**/*.md`. Never touch source or test files.
- `add-comment` — one summary comment per run.
- `noop` — when documentation is already accurate.
