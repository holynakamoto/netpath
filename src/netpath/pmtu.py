from __future__ import annotations

import subprocess


def probe(host: str) -> dict:
    """
    Detect PMTU black-holes by probing at 1472-byte and 64-byte ICMP payload sizes.
    Returns {"blackhole": bool, "mtu_floor_bytes": int | None}.
    Returns {"blackhole": False, "mtu_floor_bytes": None} gracefully when ICMP is
    unavailable or the host blocks all probes — a black-hole cannot be confirmed
    unless both probe sizes run and the small one succeeds.
    """
    def _ping(size: int) -> bool:
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-s", str(size), host],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    try:
        large_ok = _ping(1472)
        small_ok = _ping(64)
        if small_ok and not large_ok:
            return {"blackhole": True, "mtu_floor_bytes": 64}
        return {"blackhole": False, "mtu_floor_bytes": None}
    except Exception:
        return {"blackhole": False, "mtu_floor_bytes": None}
