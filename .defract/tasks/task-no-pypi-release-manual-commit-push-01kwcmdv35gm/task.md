---
defract:
  id: task-no-pypi-release-manual-commit-push-01kwcmdv35gm
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
