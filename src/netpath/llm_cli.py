"""Invoke a locally-authenticated AI CLI (claude or codex) for one-shot,
schema-constrained generation — no API keys, reuses whatever login the
user's Claude Code or Codex CLI already has. Every call is sandboxed,
ephemeral, ignores project/user config, and non-interactive.

Callers must always have a deterministic fallback: this never raises, and
returns None on any failure (CLI not installed, timeout, invalid output),
so a missing or misbehaving CLI degrades a feature rather than breaking it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_PROVIDERS = {"claude", "codex"}


def available(provider: str) -> bool:
    return provider in _PROVIDERS and shutil.which(provider) is not None


def run_schema_constrained(
    provider: str,
    prompt: str,
    schema: dict[str, Any],
    *,
    timeout: int = 60,
) -> dict[str, Any] | None:
    """Run `provider` ("claude" or "codex") non-interactively, constrained to `schema`.

    Returns the parsed structured output, or None on any failure.
    """
    if provider not in _PROVIDERS:
        return None
    executable = shutil.which(provider)
    if not executable:
        return None
    schema_json = json.dumps(schema, separators=(",", ":"))
    try:
        if provider == "claude":
            result = subprocess.run(
                [
                    executable,
                    "--print",
                    "--safe-mode",
                    "--tools", "",
                    "--no-session-persistence",
                    "--permission-mode", "dontAsk",
                    "--output-format", "json",
                    "--json-schema", schema_json,
                    prompt,
                ],
                capture_output=True,
                text=True,
                cwd=tempfile.gettempdir(),
                timeout=timeout,
            )
            payload = json.loads(result.stdout or "{}")
            if not isinstance(payload, dict):
                return None
            structured = payload.get("structured_output") or payload.get("result") or payload
            if isinstance(structured, str):
                structured = json.loads(structured)
            return structured if isinstance(structured, dict) else None

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False,
        ) as schema_file:
            schema_file.write(schema_json)
            schema_path = schema_file.name
        try:
            result = subprocess.run(
                [
                    executable,
                    "exec",
                    "--ephemeral",
                    "--sandbox", "read-only",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--skip-git-repo-check",
                    "--cd", tempfile.gettempdir(),
                    "--output-schema", schema_path,
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            structured = json.loads(result.stdout or "{}")
            return structured if isinstance(structured, dict) else None
        finally:
            Path(schema_path).unlink(missing_ok=True)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None
