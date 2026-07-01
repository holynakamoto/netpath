import time
from typing import Callable, TypeVar

import requests

T = TypeVar("T")


def _with_retry(fn: Callable[[], T], attempts: int = 3, base_delay: float = 1.0) -> T:
    """
    Retry callable up to `attempts` times on transient failures.

    Retries on: requests.ConnectionError, requests.Timeout, and HTTP 5xx responses
    (detected by duck-typing status_code on the return value).
    Delay sequence: base_delay, base_delay*2, base_delay*4, ... (exponential backoff).
    Re-raises the last exception after all attempts are exhausted.
    """
    last_exc: Exception = RuntimeError("_with_retry called with attempts=0")
    for attempt in range(attempts):
        if attempt > 0:
            time.sleep(base_delay * (2 ** (attempt - 1)))
        try:
            result = fn()
            # Duck-type: if the callable returned a Response-like object with a 5xx status,
            # treat it as a transient failure and retry.
            if (
                hasattr(result, "status_code")
                and isinstance(result.status_code, int)  # type: ignore[union-attr]
                and result.status_code >= 500  # type: ignore[union-attr]
            ):
                last_exc = requests.HTTPError(f"HTTP {result.status_code}")
                continue
            return result
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
    raise last_exc
