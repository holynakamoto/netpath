import re
import subprocess

import pytest


def test_no_generated_python_artifacts_are_tracked():
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git metadata is unavailable")

    offenders = [
        path for path in result.stdout.splitlines()
        if re.search(r"(^\.venv/|__pycache__/|\.pyc$|^src/netpath/_version\.py$)", path)
    ]
    assert offenders == []
