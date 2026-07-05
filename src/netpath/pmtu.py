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
                ["ping", "-c", "1", "-W", "1", "-s", str(size), host],
                capture_output=True, text=True, timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    try:
        small_size = 64
        large_size = 1472
        large_ok = _ping(large_size)
        small_ok = _ping(small_size)
        if small_ok and not large_ok:
            lo, hi = small_size, large_size - 1
            best = small_size
            while lo <= hi:
                mid = (lo + hi) // 2
                if _ping(mid):
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            return {
                "blackhole": True,
                "mtu_floor_bytes": small_size,
                "effective_mtu_bytes": best + 28,
                "max_payload_bytes": best,
                "large_payload_bytes": large_size,
                "small_payload_bytes": small_size,
            }
        return {
            "blackhole": False,
            "mtu_floor_bytes": None,
            "effective_mtu_bytes": large_size + 28 if large_ok else None,
            "max_payload_bytes": large_size if large_ok else None,
            "large_payload_bytes": large_size,
            "small_payload_bytes": small_size,
        }
    except Exception:
        return {"blackhole": False, "mtu_floor_bytes": None}
