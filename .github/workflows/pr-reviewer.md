---
name: PR Reviewer
description: Reviews pull requests touching the netpath package and comments on quality issues.
on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - "src/netpath/**"
      - "tests/**"
      - "pyproject.toml"
engine: claude
model: claude-sonnet-5
permissions:
  contents: read
  issues: read
  pull-requests: read
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
safe-outputs:
  add-comment:
---

# PR Reviewer

## Task

Review the changes in this pull request to `src/netpath/**`, `tests/**`, or `pyproject.toml`.

Look for:

- Correctness bugs and edge cases the tests don't cover
- Missing or inadequate test coverage for the changed code
- Unnecessary complexity, duplication, or opportunities to simplify
- Inconsistencies with existing patterns in the codebase

Post one comment summarizing findings. If nothing notable is found, call `noop` with a short explanation instead of posting a comment.

## Safe Outputs

- Use `add-comment` to post review findings.
- Use `noop` with a short explanation when there is nothing worth flagging.

## Report Style

- Use GitHub-flavored markdown.
- Start nested headings at `###`.
- Keep the summary and any blocking issues visible; wrap long code excerpts in `<details><summary>...</summary>`.
- Use `> [!WARNING]` for issues that should block merge, `> [!NOTE]` for minor suggestions.
