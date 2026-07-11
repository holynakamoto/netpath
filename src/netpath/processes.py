"""Small process-lifecycle helpers shared by interactive workflows."""

from __future__ import annotations

import os
import signal
import subprocess
import time


def terminate_process_tree(
    process: subprocess.Popen,
    *,
    grace_seconds: float = 0.25,
) -> None:
    """Terminate a process and any children in its dedicated process group.

    Netpath starts cancellable subprocesses in new sessions on POSIX. Sending
    signals to that group prevents mtr, traceroute, tcpdump, and planner child
    processes from surviving after the owning TUI operation stops.
    """

    group_id: int | None = None
    if os.name == "posix" and isinstance(getattr(process, "pid", None), int):
        # Every caller starts the process with start_new_session=True, making
        # its PID the stable process-group ID.  Using the PID directly also
        # lets us clean up surviving children after the group leader exits.
        group_id = process.pid
        try:
            os.killpg(group_id, signal.SIGTERM)
        except (OSError, ValueError):
            group_id = None

    if group_id is None:
        try:
            if process.poll() is not None:
                return
        except (OSError, ValueError):
            return
        try:
            process.terminate()
        except OSError:
            return

    deadline = time.monotonic() + max(0.0, grace_seconds)
    while time.monotonic() < deadline:
        if group_id is None and process.poll() is not None:
            return
        time.sleep(min(0.025, max(0.0, deadline - time.monotonic())))

    if group_id is not None:
        try:
            os.killpg(group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            try:
                process.kill()
            except OSError:
                pass
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


__all__ = ["terminate_process_tree"]
