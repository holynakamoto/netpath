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

## What We're Building

We are wiring up an automated release pipeline for netpath so that pushing a version tag to GitHub triggers a PyPI publish without any manual steps. At the same time, we are switching the version string from a hardcoded constant to one derived from the git tag, so there is no longer a separate version file to update before each release.

## Expected Outcome

- Pushing a tag like `v0.2.0` to GitHub automatically builds and publishes that version to PyPI — no manual `twine upload` needed.
- The package version shown in `netpath --help` and in pip/uv installs matches the git tag exactly, without anyone editing a version file by hand.
- Authentication to PyPI uses GitHub's OIDC identity (trusted publishing), so no API token is stored in GitHub Secrets.
- Users installing via `pip install netpath` or `uvx netpath` receive the latest tagged release automatically.
- The existing CI test suite (pytest across Python 3.9–3.13) continues to run on every push and pull request, unchanged.

## Out of Scope

- The manual `git push` step after defract tasks completes — that is an orchestrator behavior, not a netpath code change, and resolving it requires changes outside this repository.
- Automating the one-time PyPI trusted-publisher registration — that is a manual browser action in the PyPI web UI that must be done once before the first tag push.
- Adding a `--json` flag to the `country` subcommand or any other feature work unrelated to the release pipeline.
