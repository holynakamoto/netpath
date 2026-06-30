---
defract:
  id: task-publish-netpath-0-2-0-install-on-macos-01kwcs4s6hz6
  type: improvement
  status: active
  stage: release
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

# Publish netpath 0.2.0 + install on macOS

# Publish netpath 0.2.0 + install on macOS

## What We're Building

This task captures the work completed to publish netpath 0.2.0 to PyPI and get it running on macOS, then delivers the one remaining code change: upgrading the GitHub Actions versions in the publish and CI workflows to eliminate Node 20 deprecation warnings. The PyPI publish failure (a missing trusted publisher registration) and the macOS install confusion (PEP 668 block, competing uv and pipx installs) were both resolved during a prior chat session; the workflow version bump is the outstanding change that needs to land in the codebase.

## Expected Outcome

- GitHub Actions CI and publish workflows no longer emit Node 20 deprecation warnings
- Future tag-based releases publish cleanly through the updated workflow
- netpath 0.2.0 is confirmed on PyPI and installable on macOS via `uv tool install netpath`

## Phase Outcomes

- **Phase 1: Bump GitHub Actions versions in both workflows** — CI and release publishing runs stop emitting Node 20 deprecation warnings, keeping the automation clean and forward-compatible.

## Out of Scope

- Adding a `--version` flag to the netpath CLI (separate task if desired)
- Enabling `--json` output for the `country` subcommand (separate task)
- Changes to netpath's measurement, display, or diagnostic logic
- Resolving the dual-install (uv vs pipx) situation on the user's machine — a user-side action, not a code change

## Scope Summary

**Size:** 2 requirements, 3 acceptance criteria, 1 implementation phase
**Key decisions:**
- Single-phase config-change: version bumps in two YAML files, no logic affected
- No review stage: the change is mechanical; CI run output is the verification signal
**Biggest risk:** A major version bump on an action (e.g. upload-artifact v4 → v5) may change artifact retention defaults or URL format — verify changelogs before committing.

## Context

The project's CI runs on GitHub Actions across Python 3.9–3.13 (`.github/workflows/ci.yml`). Releases are triggered by a `v*.*.*` tag push and publish to PyPI via OIDC trusted publishing (`.github/workflows/publish.yml`). Both workflows currently use action versions that internally run on Node 20, which GitHub has deprecated in favour of Node 24. The specific actions involved are `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`, and `actions/download-artifact`. The `pypa/gh-action-pypi-publish` action is Docker-based and does not contribute to Node deprecation warnings.

## Requirements

### Workflow Maintenance

- R1: The CI workflow must use the latest stable versions of all referenced GitHub Actions, such that no Node deprecation warnings appear in subsequent CI runs.
- R2: The publish workflow must use the latest stable versions of all referenced GitHub Actions for the same reason; verify each action's changelog for breaking changes before bumping.

## Acceptance Criteria

- [ ] A CI run triggered after merging this change (push or PR against main) produces no "Node.js 20 is deprecated" warnings in its output.
- [ ] Both `.github/workflows/ci.yml` and `.github/workflows/publish.yml` are syntactically valid YAML (no parse errors).
- [ ] The publish workflow structure — build job producing dist artifacts, publish job consuming them via OIDC — remains functionally identical after the version bumps.

## Implementation Phases

### Phase 1: Bump action versions in both workflows
**Scope:** Update the version tags for every `uses:` step in `.github/workflows/ci.yml` and `.github/workflows/publish.yml` to their current latest stable releases. Check each action's GitHub Releases page for the latest tag and review its changelog for any breaking changes before applying the bump.
**Files:**
- `.github/workflows/ci.yml` — bump `actions/checkout` and `actions/setup-python`
- `.github/workflows/publish.yml` — bump `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`, and `actions/download-artifact`
**Verification:**
- [ ] `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` exits 0
- [ ] `python -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml'))"` exits 0
- [ ] Push the branch and confirm no "Node.js 20 is deprecated" warning appears in the CI run log
**Estimated effort:** Small

## Edge Cases

- **Breaking changes on major bumps**: `actions/upload-artifact` v4 → v5 may change artifact retention periods or access patterns between jobs; review the changelog and confirm the `download-artifact` step in the publish job still finds the `dist` artifact by name.
- **Pinned vs floating tags**: The existing workflows use floating major-version tags (e.g. `@v4`). Bumping to `@v5` continues that convention; pinning to a SHA is out of scope.

## Technical Notes

Current action versions in the workflows (as found in the worktree):
- `ci.yml`: `actions/checkout@v4`, `actions/setup-python@v5`
- `publish.yml`: `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`, `pypa/gh-action-pypi-publish@release/v1`

The `pypa/gh-action-pypi-publish` action uses a Docker container and does not run Node at all — it is not a source of Node deprecation warnings and does not need a version bump for this task (the `release/v1` floating tag already tracks the latest v1 release).

Version is managed via `hatch-vcs` (git tags drive the build version); no `pyproject.toml` version field exists to update.

## Implementation Notes

## Phase 1: Bump action versions in both workflows

### What was built

Updated `.github/workflows/ci.yml` and `.github/workflows/publish.yml` to use the latest stable major versions of all referenced GitHub Actions, resolving Node 20 deprecation warnings.

**Version changes:**
- `actions/checkout@v4` → `@v7` (both workflows)
- `actions/setup-python@v5` → `@v6` (both workflows)
- `actions/upload-artifact@v4` → `@v7` (publish.yml)
- `actions/download-artifact@v4` → `@v8` (publish.yml)

### Changelog review summary

- **checkout@v7**: ESM upgrade + security fix (blocks fork PR checkout for pull_request_target). Transparent for our usage.
- **setup-python@v6**: Upgrades internal runtime to Node 24 — exactly the fix needed. Requires runner v2.327.1+ (ubuntu-latest is always current).
- **upload-artifact@v7**: ESM upgrade + new optional direct-upload feature. Existing name+path usage unchanged.
- **download-artifact@v8**: ESM upgrade + direct-download support + hash-mismatch now errors by default (security hardening). Name-based download still works identically.

### Verification results

- `ci.yml` YAML: valid
- `publish.yml` YAML: valid
- 14 pytest tests: all passed
- Ruff: 9 pre-existing lint issues in unrelated files (display.py, speedtest.py, zoom_analyze.py) — not introduced by this phase

## Release

## Release Notes

### What was built
- Bumped `actions/checkout` from v4 to v7 in both CI and publish workflows
- Bumped `actions/setup-python` from v5 to v6 in both CI and publish workflows
- Bumped `actions/upload-artifact` from v4 to v7 in the publish workflow
- Bumped `actions/download-artifact` from v4 to v8 in the publish workflow
- All version bumps reviewed for breaking changes; none affect existing usage patterns

### Key decisions
- Chose latest stable major versions (checkout@v7, setup-python@v6, upload-artifact@v7, download-artifact@v8) rather than intermediate versions to maximise the time before the next required upgrade
- `pypa/gh-action-pypi-publish@release/v1` left unchanged — it is Docker-based and does not run Node, so it is not a source of Node deprecation warnings
- Confirmed upload-artifact@v7 + download-artifact@v8 cross-version compatibility: name-based artifact handoff between the build and publish jobs continues to work identically

### Changes by phase
- **Phase 1: Bump action versions in both workflows** — Updated `.github/workflows/ci.yml` (checkout v4→v7, setup-python v5→v6) and `.github/workflows/publish.yml` (same two plus upload-artifact v4→v7, download-artifact v4→v8). Both YAML files validate cleanly; 14 pytest tests pass; 9 pre-existing ruff issues in unrelated files are unchanged.

## Verification

- Production build: PASS (`uv build` produced `netpath-0.2.1.dev7+g47bba3979` wheel and sdist)
- Code pushed to remote branch: `feature/task-publish-netpath-0-2-0-install-on-macos-01kwcs4s6hz6`
- YAML syntax: both workflow files validated cleanly during implementation phase
- Tests: 14 passed, 0 failed during implementation phase
- Review stage: skipped (config-change workflow — CI run output is the verification signal)

