"""PostHog analytics helper for netpath.

Initializes a PostHog client from environment variables and exposes a thin
capture() wrapper. All calls are no-ops when POSTHOG_PROJECT_TOKEN is unset
so the CLI continues to work without any PostHog configuration.

The anonymous install ID is a UUID stored in ~/.netpath/install_id so every
event from the same installation is correlated without sending any PII.
"""
from __future__ import annotations

import atexit
import json
import os
import platform
import sys
import uuid
from pathlib import Path

_client = None
_install_id: str | None = None
_is_new_install = False

_INSTALL_ID_FILE = Path.home() / ".netpath" / "install_id"


def _get_install_id() -> str:
    global _install_id, _is_new_install
    if _install_id:
        return _install_id
    try:
        _INSTALL_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _INSTALL_ID_FILE.exists():
            data = json.loads(_INSTALL_ID_FILE.read_text())
            if isinstance(data.get("id"), str) and data["id"]:
                _install_id = data["id"]
                return _install_id
        new_id = f"netpath_{uuid.uuid4().hex}"
        _INSTALL_ID_FILE.write_text(json.dumps({"id": new_id}))
        _install_id = new_id
        _is_new_install = True
    except Exception:
        _install_id = "netpath_anonymous"
    return _install_id


def init() -> None:
    """Initialize the PostHog client. Call once at CLI startup."""
    global _client
    if _client is not None:
        return

    token = os.getenv("POSTHOG_PROJECT_TOKEN")
    if not token:
        debug = os.getenv("NETPATH_DEBUG", "").lower() in ("1", "true", "yes")
        if debug:
            raise RuntimeError(
                "POSTHOG_PROJECT_TOKEN variable required by PostHog is missing or "
                "un-configured, this causes events to be silently missed. "
                "This error stops appearing once POSTHOG_PROJECT_TOKEN is configured"
            )
        return

    from posthog import Posthog  # noqa: PLC0415 — deferred to keep import cost low

    host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    _client = Posthog(
        token,
        host=host,
        enable_exception_autocapture=True,
    )
    atexit.register(_client.shutdown)

    # Record installation-level person properties on first run and update on
    # every run so the profile stays current (no PII — OS/Python/version only).
    distinct_id = _get_install_id()
    try:
        from netpath import __version__ as _version
    except Exception:
        _version = "unknown"
    _client.set(
        distinct_id=distinct_id,
        properties={
            "netpath_version": _version,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "os_platform": sys.platform,
            "os_name": platform.system(),
        },
    )


def capture(event: str, properties: dict | None = None) -> None:
    """Capture an analytics event. Safe to call even when PostHog is not configured."""
    if _client is None:
        return
    _client.capture(
        distinct_id=_get_install_id(),
        event=event,
        properties=properties or {},
    )
