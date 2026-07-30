---
name: Daily Activity Report
description: Summarizes recent repository activity and posts it as a daily issue.
on:
  schedule: daily on weekdays
  workflow_dispatch:
  skip-if-match: 'is:issue is:open in:title "Daily Activity Report:"'
engine: claude
permissions:
  contents: read
  issues: read
  pull-requests: read
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
safe-outputs:
  create-issue:
    title-prefix: "Daily Activity Report: "
    labels: [report]
    close-older-issues: true
    expires: 7
---

# Daily Activity Report

## Task

Summarize activity in this repository over the last 24 full hours ending at workflow start (UTC):

- Pull requests opened, merged, or closed
- Issues opened or closed
- Notable commits pushed to the default branch

Report window: last 24 full hours ending at workflow start (UTC).

If there is no qualifying activity in the window, call `noop` with the evaluated window in the message, e.g. `noop("No activity in last 24 full hours ({{window_start_utc}} to {{window_end_utc}})")`.

## Safe Outputs

- Use `create-issue` to publish the report.
- Use `noop` with a short explanation when no action is required.

## Report Style

- Use GitHub-flavored markdown.
- Start nested headings at `###`.
- Use `<details><summary>...</summary>` for long sections such as full commit or PR lists.
- Keep the overview and key metrics visible; wrap verbose detail in collapsible sections.
- Use `> [!NOTE]` / `> [!WARNING]` alerts instead of emoji severity markers.
