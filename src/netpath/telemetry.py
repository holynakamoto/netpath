"""Optional, privacy-preserving usage telemetry.

Nothing is ever sent unless both conditions hold: the user has explicitly
opted in (`netpath telemetry on`) *and* set `NETPATH_TELEMETRY_KEY` to a
PostHog project key of their own choosing. No key ships with netpath, so
installing or running the tool is inert by default (see INV-7).

Only `check_type` and `result` are ever captured — never a target host,
resolved IP, or any other value that could identify what the user is
diagnosing (see INV-3).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

_STATE_PATH = Path.home() / ".netpath" / "telemetry.json"
_POSTHOG_HOST = "https://us.i.posthog.com"

_client = None
_client_unavailable = False


def _load() -> dict:
    try:
        data = json.loads(_STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _STATE_PATH.with_suffix(_STATE_PATH.suffix + ".tmp")
    temporary.write_text(json.dumps(data))
    temporary.chmod(0o600)
    temporary.replace(_STATE_PATH)


def set_enabled(enabled: bool) -> None:
    data = _load()
    data["enabled"] = enabled
    _save(data)


def is_enabled() -> bool:
    return bool(_load().get("enabled", False))


def status() -> dict:
    return {
        "enabled": is_enabled(),
        "key_configured": bool(os.environ.get("NETPATH_TELEMETRY_KEY")),
    }


def _client_id() -> str:
    data = _load()
    existing = data.get("client_id")
    if isinstance(existing, str) and existing:
        return existing
    new_id = str(uuid.uuid4())
    data["client_id"] = new_id
    _save(data)
    return new_id


def _get_client():
    global _client, _client_unavailable
    if _client is not None or _client_unavailable:
        return _client
    key = os.environ.get("NETPATH_TELEMETRY_KEY")
    if not key:
        _client_unavailable = True
        return None
    try:
        from posthog import Posthog
    except ImportError:
        _client_unavailable = True
        return None
    _client = Posthog(key, host=_POSTHOG_HOST)
    return _client


def capture(check_type: str, result: str) -> None:
    """Record that a diagnostic check ran, if the user has opted in."""
    if not is_enabled():
        return
    client = _get_client()
    if client is None:
        return
    client.capture(
        distinct_id=_client_id(),
        event="diagnostic_run",
        properties={"check_type": check_type, "result": result},
    )
