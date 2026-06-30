---
defract:
  id: task-publish-netpath-0-2-0-install-on-macos-01kwcs4s6hz6
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

# Publish netpath 0.2.0 + install on macOS

## Story Brief

## Story Brief

From chat: Publish netpath 0.2.0 + install on macOS (2026-06-30T17:07:55.596Z)

### Findings

- **publish.yml triggers only on v*.*.* tag push and uses PyPI trusted publishing** — .github/workflows/publish.yml fires only on `push` of tags matching `v*.*.*` (lines 3-6); a plain commit/branch push does not trigger it. It build (sdist+wheel via `python -m build`) then publishes via pypa/gh-action-pypi-publish using OIDC trusted publishing — no API token, `id-token: write`, and `environment: pypi` (lines 38-42, 50-51). Version is VCS-derived through hatch-vcs (pyproject.toml:46-47), so the tag also stamps the package version.
  - Files: .github/workflows/publish.yml, pyproject.toml
- **"Didn't deploy" diagnostic fork hinges on whether a Publish run appeared in Actions** — Two distinct failure modes. (A) No workflow run at all = trigger problem: the v0.2.0 tag likely never reached the remote (plain `git push` does not push tags; need `git push origin v0.2.0` or `--follow-tags`), or Actions is disabled. (B) A "Publish to PyPI" run appeared but didn't publish = trigger worked, fault is downstream: the `pypi` GitHub environment may require reviewer approval (job parked), the PyPI trusted publisher may not be registered for project netpath (must match owner holynakamoto, repo netpath, workflow publish.yml, environment pypi), or the build failed. Checking the Actions tab for a v0.2.0 run is the decisive disambiguator.
  - Files: .github/workflows/publish.yml
- **v0.2.0 run fired and built, but the PyPI publish step failed (not an approval gate)** — Actions shows "Publish to PyPI #1" ran for tag v0.2.0 and the pypi environment deployment status is "Failed to deploy (completed)" — so the tag trigger and build succeeded and the failure is in the publish step itself. Because status is "failed" rather than "waiting", a required-reviewer environment gate is ruled out. For a first release via OIDC trusted publishing this is almost certainly either (1) no trusted/pending publisher registered on PyPI, or (2) the project name 'netpath' is already owned by another PyPI account (403). The exact error in the publish step disambiguates.
  - Files: .github/workflows/publish.yml
- **Root cause confirmed: PyPI invalid-publisher — no trusted publisher registered** — The publish step failed with "Trusted publishing exchange failure: invalid-publisher: valid token, but no corresponding publisher". The OIDC token GitHub issued is valid; PyPI has no trusted-publisher config matching the claims. Workflow, tag, and build are all fine. The token's actual claims to match are: repository_owner=holynakamoto, repository=holynakamoto/netpath, workflow_ref publish.yml, environment=pypi. This is purely a missing one-time PyPI-side registration, not a name conflict and not a workflow bug.
  - Files: .github/workflows/publish.yml
- **v0.2.0 published to PyPI successfully after adding the trusted publisher** — After registering the pending publisher on PyPI and re-running the failed publish job, the publish step succeeded — netpath 0.2.0 is now on PyPI. Confirms the only fault was the missing trusted-publisher registration; no workflow or code change was required to publish.
  - Files: .github/workflows/publish.yml
- **macOS install of netpath blocked by PEP 668; use uv tool/uvx or pipx, not system pip** — `pip3 install --upgrade netpath` failed with externally-managed-environment (PEP 668) because the user's Python is Homebrew-managed, and bare `pip` is not on PATH at all. netpath is a CLI application, so the correct install is an isolated per-tool environment: `uv tool install netpath` (upgrade via `uv tool upgrade netpath`) or run ephemerally with `uvx netpath`; alternatively `brew install pipx && pipx install netpath`. Avoid `--break-system-packages`, which risks the Homebrew Python and is the wrong approach for an application. Recommended: uv, since the project already standardizes on uv.
- **Dual netpath installs: uv tool owns the PATH symlink, pipx 0.2.0 is orphaned** — The user has both a uv tool install and a pipx install of netpath. ~/.local/bin/netpath points to the uv-managed binary (~/.local/share/uv/tools/netpath/bin/netpath), so pipx refused to overwrite the symlink and its upgraded 0.2.0 (~/.local/pipx/venvs/netpath) is orphaned — not on PATH. The netpath actually invoked is the uv one (likely still 0.1.0). Fix: pick one manager. Recommended (project uses uv): `pipx uninstall netpath` then `uv tool upgrade netpath` (or `uv tool install netpath --force`); verify with `which netpath` and `uv tool list`. Note there is no `netpath --version` flag — version is only printed in the run header (cli.py:348 and cli.py:451), so check version via `uv tool list`/`pipx list`.
  - Files: src/netpath/cli.py

### Proposed actions

- **Register a PyPI pending publisher matching repo/workflow/environment for first release** — If the publish-step error is a trusted-publishing exchange failure, create a pending publisher on PyPI (Your projects → Publishing) matching exactly: project name `netpath`, owner `holynakamoto`, repository `netpath`, workflow filename `publish.yml`, environment `pypi`. The environment name in particular must match the `environment: pypi` set in publish.yml line 41. If instead the error is a 403 'not allowed to upload to project netpath', the name is taken by another account and the fix is to rename the distribution (project.name in pyproject.toml) or claim/transfer the existing project — no publisher config will resolve that case.
  - Files: .github/workflows/publish.yml, pyproject.toml
- **Add PyPI pending publisher with exact claim values, then re-run the failed job** — Fix: at https://pypi.org/manage/account/publishing/ add a pending publisher (first release, project not yet on PyPI) with PyPI Project Name=netpath, Owner=holynakamoto, Repository name=netpath, Workflow filename=publish.yml, Environment name=pypi. If PyPI reports the name is already taken, that is a separate name-conflict problem requiring a different distribution name. After saving the publisher, re-run failed jobs on the existing "Publish to PyPI #1" run rather than re-tagging — it reuses the build artifact and the OIDC exchange will then match. No code or workflow change needed.
  - Files: .github/workflows/publish.yml, pyproject.toml
- **Bump GitHub Actions off Node 20 in publish.yml and ci.yml** — The publish run emitted a Node 20 deprecation warning (actions/download-artifact@v4 forced onto Node 24; v4 will stop running once the grace period ends). Non-fatal now but will break the workflow later. Fix in .github/workflows/publish.yml: actions/download-artifact@v4 -> @v5, actions/upload-artifact@v4 -> @v5, actions/checkout@v4 -> @v5, actions/setup-python@v5 -> @v6. ci.yml also uses checkout@v4 and setup-python@v5 and will warn the same way, so bump both files in one change. Pure version bumps, no logic change.
  - Files: .github/workflows/publish.yml, .github/workflows/ci.yml

Originating chat: Publish netpath 0.2.0 + install on macOS (65566a87-f2d7-41a6-9dab-b588e98e50ec)
