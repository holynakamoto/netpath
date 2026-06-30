---
defract:
  id: task-no-pypi-release-manual-commit-push-01kwcmdv35gm
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

# Automated PyPI Publishing with VCS Versioning

# Automated PyPI Publishing with VCS Versioning

## What We're Building

We are wiring up an automated release pipeline for netpath so that pushing a version tag to GitHub triggers a PyPI publish without any manual steps. At the same time, we are switching the version string from a hardcoded constant to one derived from the git tag, so there is no longer a separate version file to update before each release.

## Expected Outcome

- Pushing a tag like `v0.2.0` to GitHub automatically builds and publishes that version to PyPI — no manual `twine upload` needed.
- The package version shown in `netpath --help` and in pip/uv installs matches the git tag exactly, without anyone editing a version file by hand.
- Authentication to PyPI uses GitHub's OIDC identity (trusted publishing), so no API token is stored in GitHub Secrets.
- Users installing via `pip install netpath` or `uvx netpath` receive the latest tagged release automatically.
- The existing CI test suite (pytest across Python 3.9–3.13) continues to run on every push and pull request, unchanged.

## Phase Outcomes

- **Phase 1: Wire up VCS versioning and automated publish** — Maintainers can release a new version by pushing a single annotated git tag; PyPI publishing happens automatically with no manual upload step, and the installed package version always reflects that tag.

## Out of Scope

- The manual `git push` step after defract tasks complete — that is an orchestrator behavior, not a netpath code change, and resolving it requires changes outside this repository.
- Automating the one-time PyPI trusted-publisher registration — that is a manual browser action in the PyPI web UI that must be done once before the first tag push.
- Adding a `--json` flag to the `country` subcommand or any other feature work unrelated to the release pipeline.

## Scope Summary

**Size:** 6 requirements, 7 acceptance criteria, 1 implementation phase
**Key decisions:**
- Use `hatch-vcs` (the first-party hatchling VCS plugin) rather than `setuptools-scm` or a custom script, keeping the build stack homogeneous
- Use PyPI trusted publishing (OIDC) rather than a stored API token, eliminating secret rotation overhead
- Single phase: all file changes are tightly coupled and can be reviewed together
**Biggest risk:** The one-time PyPI trusted-publisher registration must be completed in the PyPI web UI before the first tag push; the workflow silently fails with a 403 until that step is done.

## Context

netpath currently hardcodes `version = "0.1.0"` in both `pyproject.toml` and `src/netpath/__init__.py`. Releases require manually editing these files, building locally, and running `twine upload`. The project uses `hatchling` as its build backend (`pyproject.toml` lines 1–2), which has a first-party VCS plugin (`hatch-vcs`) that derives the version from `git describe --tags` at build/install time. The CI workflow at `.github/workflows/ci.yml` runs pytest across Python 3.9–3.13 on pushes and PRs to `main`; a separate publish workflow triggered by version tags is the standard pattern for PyPI projects using trusted publishing.

## Requirements

### VCS Versioning

- R1: The package version is derived from git tags at build and install time using `hatch-vcs`, with no hardcoded version string remaining in `pyproject.toml` or `src/netpath/__init__.py`.
- R2: When no git tag is reachable (fresh clone with no tags, local dev before first tag), the version falls back to a non-crashing sentinel rather than raising an import error; `netpath.__version__` always returns a string.
- R3: The generated `src/netpath/_version.py` file (written by hatch-vcs during editable install or build) is listed in `.gitignore` so it is never committed.

### Publish Workflow

- R4: A new GitHub Actions workflow triggers on any tag matching `v*.*.*` pushed to the repository, builds sdist and wheel distribution packages, and publishes them to PyPI.
- R5: PyPI authentication uses OIDC trusted publishing (`pypa/gh-action-pypi-publish@release/v1` with `id-token: write` permission); no API token or secret is stored in GitHub repository settings.
- R6: The publish workflow checks out the repository with `fetch-depth: 0` so that `git describe` can reach all tags and `hatch-vcs` computes the correct version.

## Acceptance Criteria

- [ ] Running `pip install -e .` in a clean checkout generates `src/netpath/_version.py` and `python -c "import netpath; print(netpath.__version__)"` prints a non-empty string.
- [ ] `pyproject.toml` contains `dynamic = ["version"]` with no residual `version = "0.1.0"` field; `[tool.hatch.version]` sets `source = "vcs"`.
- [ ] `grep 'hatch-vcs' pyproject.toml` matches inside the `[build-system] requires` list.
- [ ] `src/netpath/_version.py` appears in `.gitignore`; after an editable install, `git status --short` does not show it as an untracked file.
- [ ] `.github/workflows/publish.yml` exists and contains `on: push: tags: - "v*.*.*"`, `pypa/gh-action-pypi-publish`, and `id-token: write` with no `password:` input.
- [ ] The publish workflow's checkout step contains `fetch-depth: 0`.
- [ ] With no git tags reachable, `python -c "import netpath; print(netpath.__version__)"` completes without exception and prints a non-empty string.

## Implementation Phases

### Phase 1: Wire up VCS versioning and automated publish
**Scope:** Switch the build system to derive the package version from git tags and add a GitHub Actions workflow that publishes to PyPI automatically when a version tag is pushed.
**Files:**
- `pyproject.toml` — add `hatch-vcs` to `[build-system].requires`; replace `version = "0.1.0"` with `dynamic = ["version"]`; add `[tool.hatch.version]` (`source = "vcs"`) and `[tool.hatch.build.hooks.vcs]` (`version-file = "src/netpath/_version.py"`) sections
- `src/netpath/__init__.py` — replace `__version__ = "0.1.0"` with an import from the generated `_version.py`, wrapped in a try/except that falls back to `"0.0.0+unknown"` when the file does not yet exist
- `.gitignore` — append `src/netpath/_version.py`
- `.github/workflows/publish.yml` — create new workflow: two jobs (`build` and `publish`), triggered on `v*.*.*` tag push; `build` uses `fetch-depth: 0`, installs `build`, runs `python -m build`, uploads dist/ as an artifact; `publish` downloads the artifact, runs `pypa/gh-action-pypi-publish@release/v1` with `permissions: id-token: write`
**Verification:**
- [ ] `pip install -e .` succeeds and `python -c "import netpath; print(netpath.__version__)"` prints a version string
- [ ] `grep -c 'version = "0.1.0"' pyproject.toml` returns `0`
- [ ] `grep 'hatch-vcs' pyproject.toml` returns a match
- [ ] `grep '_version.py' .gitignore` returns a match
- [ ] `grep 'id-token: write' .github/workflows/publish.yml` returns a match
- [ ] `grep 'fetch-depth: 0' .github/workflows/publish.yml` returns a match
**Estimated effort:** Small

## Edge Cases

- **Fresh checkout with no tags**: `hatch-vcs` calls `git describe` which fails when no tag exists; the `try/except` in `__init__.py` catches any exception during the import of `_version.py` and sets `__version__ = "0.0.0+unknown"` so `import netpath` never raises.
- **Shallow clone in the publish workflow**: Omitting `fetch-depth: 0` causes `git describe` to fail and `hatch-vcs` to embed `0.0.0+unknown` in the built wheel. The workflow must always fetch full history.
- **First publish before trusted-publisher registration**: PyPI returns a 403 and the workflow fails. This is expected and requires the one-time browser setup at pypi.org — not resolvable in code.
- **Local dev without running editable install**: If a contributor runs `python src/netpath/cli.py` directly without installing, `_version.py` may not exist. The fallback string handles this without a crash.

## Technical Notes

The build backend is `hatchling` (`pyproject.toml` line 1). `hatch-vcs` is its first-party VCS plugin and integrates via `[tool.hatch.version]`. No third-party alternatives are needed.

`hatch-vcs` generates `src/netpath/_version.py` at install/build time with a `__version__` variable. At runtime, `__init__.py` reads it with:

```python
try:
    from netpath._version import __version__
except Exception:
    __version__ = "0.0.0+unknown"
```

The publish workflow splits into two jobs so that `id-token: write` is scoped only to the upload step. Artifact handoff uses `actions/upload-artifact@v4` (build job) and `actions/download-artifact@v4` (publish job).

`pypa/gh-action-pypi-publish@release/v1` handles the OIDC token exchange with PyPI automatically — no `password:` input. The matching trusted publisher on PyPI must specify: owner `holynakamoto`, repo `netpath`, workflow filename `publish.yml`.

`uv.lock` tracks project runtime and dev dependencies, not build-system dependencies, so adding `hatch-vcs` to `[build-system].requires` does not require a lockfile update.

## Implementation Notes

## Phase 1: Wire up VCS versioning and automated publish

### Files Changed

- **`pyproject.toml`** — Added `hatch-vcs` to `[build-system].requires`; replaced `version = "0.1.0"` with `dynamic = ["version"]`; added `[tool.hatch.version]` (`source = "vcs"`) and `[tool.hatch.build.hooks.vcs]` (`version-file = "src/netpath/_version.py"`) sections.
- **`src/netpath/__init__.py`** — Replaced hardcoded `__version__ = "0.1.0"` with a try/except import from the generated `_version.py`, falling back to `"0.0.0+unknown"` when the file is absent.
- **`.gitignore`** — Appended `src/netpath/_version.py` so the generated file is never committed.
- **`.github/workflows/publish.yml`** — Created new two-job workflow: `build` checks out with `fetch-depth: 0`, builds sdist + wheel via `python -m build`, uploads dist/ as an artifact; `publish` downloads the artifact and runs `pypa/gh-action-pypi-publish@release/v1` with `permissions: id-token: write`. Triggered on `v*.*.*` tag pushes.

### Verification Results

- `grep -c 'version = "0.1.0"' pyproject.toml` → 0 (no hardcoded version)
- `grep 'hatch-vcs' pyproject.toml` → matches in `[build-system].requires`
- `grep '_version.py' .gitignore` → matches
- `grep 'id-token: write' publish.yml` → matches
- `grep 'fetch-depth: 0' publish.yml` → matches
- Editable install generates `src/netpath/_version.py`; `git status --short` does not show it as untracked
- `python -c "import netpath; print(netpath.__version__)"` → `0.1.dev50+gc737241b7.d20260630`
- All 14 tests pass (unchanged from baseline)

### Deviations from Plan

None. Implementation follows the phase spec exactly.

## Review

## Verdict

**Verdict:** APPROVE
**Files reviewed:** 4 files changed across 1 phases

All 7 acceptance criteria pass with concrete evidence. The VCS versioning via hatch-vcs is correctly wired, the fallback for missing tags works, and the publish workflow is structured correctly with OIDC trusted publishing scoped to the publish job only.

### Automated Checks

| Check | Result | Details |
|-------|--------|---------|
| Test suite (pytest) | PASS | 14 passed, 0 failed across test_diagnosis.py and test_mtr.py |
| Lint (ruff, changed files) | PASS | No issues in pyproject.toml or src/netpath/__init__.py |

### Acceptance Criteria (7/7 passed)

- [x] AC-1: Running `pip install -e .` in a clean checkout generates `src/netpath/_version.py` and `python -c "import netpath; print(netpath.__version__)"` prints a non-empty string. — PASS: src/netpath/_version.py exists (575 bytes, generated by hatch-vcs); `python3 -c 'import netpath; print(netpath.__version__)'` prints `0.1.dev50+gc737241b7.d20260630`
- [x] AC-2: `pyproject.toml` contains `dynamic = ["version"]` with no residual `version = "0.1.0"` field; `[tool.hatch.version]` sets `source = "vcs"`. — PASS: pyproject.toml:7 `dynamic = ["version"]`; pyproject.toml:46-47 `[tool.hatch.version]` / `source = "vcs"`; `grep -c 'version = "0.1.0"' pyproject.toml` → 0
- [x] AC-3: `grep 'hatch-vcs' pyproject.toml` matches inside the `[build-system] requires` list. — PASS: pyproject.toml:2 `requires = ["hatchling", "hatch-vcs"]` under `[build-system]`
- [x] AC-4: `src/netpath/_version.py` appears in `.gitignore`; after an editable install, `git status --short` does not show it as an untracked file. — PASS: .gitignore:7 `src/netpath/_version.py`; `git status --short` output is clean — no _version.py entry
- [x] AC-5: `.github/workflows/publish.yml` exists and contains `on: push: tags: - "v*.*.*"`, `pypa/gh-action-pypi-publish`, and `id-token: write` with no `password:` input. — PASS: publish.yml:6 `- "v*.*.*"`; publish.yml:51 `uses: pypa/gh-action-pypi-publish@release/v1`; publish.yml:39 `id-token: write`; no `password:` key found in file
- [x] AC-6: The publish workflow's checkout step contains `fetch-depth: 0`. — PASS: publish.yml:15 `fetch-depth: 0` under the `actions/checkout@v4` step in the `build` job
- [x] AC-7: With no git tags reachable, `python -c "import netpath; print(netpath.__version__)"` completes without exception and prints a non-empty string. — PASS: Tested by temporarily renaming _version.py and re-importing: prints `0.0.0+unknown` with no exception. src/netpath/__init__.py:1-4 wraps the import in `try/except Exception`

### Code Quality (Refactor Review)

No code quality issues found in changed files.

### Security Assessment (Security Review)

No security issues found in changed files.

### Decisions Made During Implementation

- hatch-vcs chosen over setuptools-scm to keep the build stack homogeneous with the existing hatchling backend
- PyPI OIDC trusted publishing used instead of a stored API token — eliminates secret rotation overhead
- publish.yml splits build and publish into two jobs so id-token: write is scoped only to the upload step (least privilege)

## Required Changes

None.

## Release

## Release Notes

### What was built
- Switched version management from a hardcoded `"0.1.0"` string to VCS-derived versioning via `hatch-vcs`, eliminating the need to manually edit version files before each release
- Added `hatch-vcs` to `[build-system].requires` and configured `[tool.hatch.version]` with `source = "vcs"` in `pyproject.toml`
- Updated `src/netpath/__init__.py` to import from the hatch-vcs-generated `_version.py` with a safe `"0.0.0+unknown"` fallback for environments where the file does not exist
- Added `src/netpath/_version.py` to `.gitignore` to prevent the generated file from being committed
- Created `.github/workflows/publish.yml` — a two-job OIDC trusted publish workflow triggered on `v*.*.*` tag pushes, eliminating the need for stored PyPI API tokens

### Key decisions
- Use `hatch-vcs` (hatchling's first-party VCS plugin) rather than `setuptools-scm` or a custom script, keeping the build stack homogeneous with the existing hatchling backend
- Use PyPI OIDC trusted publishing instead of a stored API token, eliminating secret rotation overhead
- Split `publish.yml` into separate build and publish jobs so `id-token: write` is scoped only to the upload step (least privilege)

### Changes by phase
- **Phase 1: Wire up VCS versioning and automated publish** — Switched `pyproject.toml` to hatch-vcs dynamic versioning, updated `__init__.py` with try/except `_version` import, added `_version.py` to `.gitignore`, and created `.github/workflows/publish.yml` with two-job OIDC trusted publish workflow triggered on `v*.*.*` tags.

## Verification

### Production Build
- `python -m build` (via `uv run`) succeeded
- Built: `netpath-0.1.dev53+gb808873cb.d20260630.tar.gz` and `netpath-0.1.dev53+gb808873cb.d20260630-py3-none-any.whl`

### Push
- Branch `feature/task-no-pypi-release-manual-commit-push-01kwcmdv35gm` pushed to `origin` with upstream tracking set
- Implementation commit: `0059285 feat(task-no-pypi-release-manual-commit-push-01kwcmdv35gm): phase 1 — Wire up VCS versioning and automated publish`

