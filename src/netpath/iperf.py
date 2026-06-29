import json
import shutil
import subprocess


def available() -> bool:
    return shutil.which("iperf3") is not None


def run_bidirectional(host: str, port: int = 5201, duration: int = 5) -> tuple[dict, dict]:
    """
    Run iperf3 upload then download to host:port.
    Returns (upload_stats, download_stats) in the format display expects.
    Raises RuntimeError on failure.
    """
    ul_raw = _run(host, port, duration, reverse=False)
    dl_raw = _run(host, port, duration, reverse=True)
    return _extract(ul_raw, reverse=False), _extract(dl_raw, reverse=True)


def _run(host: str, port: int, duration: int, reverse: bool) -> dict:
    cmd = ["iperf3", "-c", host, "-p", str(port), "-t", str(duration), "-J"]
    if reverse:
        cmd.append("-R")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 30)
    except subprocess.TimeoutExpired:
        raise RuntimeError("iperf3 timed out")

    raw = r.stdout or r.stderr
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError((r.stderr or r.stdout).strip() or "iperf3 failed (no output)")

    if r.returncode != 0:
        err = data.get("error", "")
        raise RuntimeError(err or (r.stderr.strip() or "iperf3 exited non-zero"))

    return data


def _extract(data: dict, reverse: bool) -> dict:
    end = data.get("end", {})
    if reverse:
        s = end.get("sum_received", end.get("sum", {}))
        return {
            "bps":      s.get("bits_per_second", 0),
            "recv_bps": s.get("bits_per_second", 0),
            "bytes":    s.get("bytes", 0),
        }
    else:
        s = end.get("sum_sent", end.get("sum", {}))
        return {
            "bps":         s.get("bits_per_second", 0),
            "bytes":       s.get("bytes", 0),
            "retransmits": s.get("retransmits"),
        }
