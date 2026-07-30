---
name: Release Notes Generator
description: Drafts human-readable release highlights and prepends them to the GitHub release notes.
on:
  release:
    types: [published]
  workflow_dispatch:
engine: copilot
model: gpt-5
permissions:
  contents: read
  issues: read
  pull-requests: read
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
  cli-proxy: true
safe-outputs:
  update-release:
    max: 1
  threat-detection: false
steps:
  - name: Fetch release context
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    run: |
      set -e
      mkdir -p /tmp/gh-aw/agent/release-data
      if [ "${{ github.event_name }}" = "release" ]; then
        RELEASE_TAG="${{ github.event.release.tag_name }}"
        RELEASE_ID="${{ github.event.release.id }}"
      else
        RELEASE_TAG=$(gh release list --limit 1 --json tagName --jq '.[0].tagName')
        RELEASE_ID=$(gh release view "$RELEASE_TAG" --json databaseId --jq .databaseId)
      fi
      gh api "/repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID" > /tmp/gh-aw/agent/release-data/current_release.json
      PREV_TAG=$(gh release list --limit 2 --json tagName --jq '.[1].tagName // empty')
      if [ -n "$PREV_TAG" ]; then
        PREV_AT=$(gh release view "$PREV_TAG" --json publishedAt --jq .publishedAt)
        CURR_AT=$(gh release view "$RELEASE_TAG" --json publishedAt --jq .publishedAt)
        gh pr list --state merged --limit 200 --json number,title,author,labels,mergedAt,url \
          --jq "[.[] | select(.mergedAt >= \"$PREV_AT\" and .mergedAt <= \"$CURR_AT\")]" \
          > /tmp/gh-aw/agent/release-data/pull_requests.json
      else
        echo "[]" > /tmp/gh-aw/agent/release-data/pull_requests.json
      fi
      printf '{"release_tag":"%s","release_id":"%s"}' "$RELEASE_TAG" "$RELEASE_ID" > /tmp/gh-aw/agent/release-data/meta.json
---

# Release Notes Generator

## Data

Pre-fetched in `/tmp/gh-aw/agent/release-data/`:

- `meta.json` — `release_tag`, `release_id`
- `current_release.json` — release metadata and the auto-generated notes body
- `pull_requests.json` — PRs merged since the previous release (empty array for the first release)

## Task

1. Read `meta.json`, `current_release.json`, and `pull_requests.json`.
2. Categorize the merged PRs: **Breaking Changes**, **New Features**, **Bug Fixes**, **Documentation**, **Internal** (omit Internal from the highlights unless it's user-impacting).
3. Write a concise "## Release Highlights" section that's scannable in 30 seconds.
4. Call `update_release` with the `release_tag` from `meta.json`, `operation: "prepend"`, to add the highlights before the existing auto-generated notes. Never use `replace`.
5. Call `noop` with a short explanation only if there are no user-facing changes since the previous release.

## Report Style

- Use GitHub-flavored markdown, `###` for subsections.
- Do not repeat the auto-generated PR list — that's already in the notes below your section.
