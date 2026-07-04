from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STORE_DIR = "~/.netpath/monitor"


def store_dir(path: str | None = None) -> Path:
    return Path(os.path.expanduser(path or DEFAULT_STORE_DIR))


def history_path(asn: str, path: str | None = None) -> Path:
    safe_asn = re.sub(r"[^A-Za-z0-9_.-]+", "_", asn)
    return store_dir(path) / f"{safe_asn}.jsonl"


def _last_responsive_hop(path: list[dict[str, Any]]) -> dict[str, Any] | None:
    for hop in reversed(path):
        if hop.get("host") not in ("???", None, ""):
            return hop
    return None


def _as_path_from_hops(path: list[dict[str, Any]]) -> list[str]:
    as_path: list[str] = []
    for hop in path:
        asn = hop.get("asn")
        if asn and asn != "AS???" and (not as_path or as_path[-1] != asn):
            as_path.append(asn)
    return as_path


def snapshot_from_result(
    result: dict[str, Any],
    *,
    asn: str,
    target_host: str,
    monitor_key: str | None = None,
) -> dict[str, Any]:
    path = result.get("path") or []
    last_hop = _last_responsive_hop(path)
    throughput = result.get("throughput") or {}
    verdict = result.get("verdict") or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asn": asn,
        "monitor_key": monitor_key or asn,
        "target_host": target_host,
        "target_input": result.get("target_input"),
        "resolved_ip": result.get("resolved_ip"),
        "target_asn": result.get("target_asn"),
        "target_name": result.get("target_name"),
        "as_path": _as_path_from_hops(path),
        "last_rtt_ms": last_hop.get("avg_ms") if last_hop else None,
        "p95_rtt_ms": last_hop.get("p95_ms") if last_hop else None,
        "loss_pct": last_hop.get("loss_pct") if last_hop else None,
        "jitter_ms": result.get("jitter_ms"),
        "download_mbps": throughput.get("download_mbps"),
        "upload_mbps": throughput.get("upload_mbps"),
        "path_changes": result.get("path_changes"),
        "verdict": verdict.get("verdict"),
        "severity": verdict.get("severity"),
    }


def load_latest(asn: str, path: str | None = None) -> dict[str, Any] | None:
    file_path = history_path(asn, path)
    try:
        with file_path.open() as f:
            latest = None
            for line in f:
                line = line.strip()
                if line:
                    try:
                        latest = json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return latest
    except FileNotFoundError:
        return None


def append_snapshot(snapshot: dict[str, Any], path: str | None = None) -> Path:
    file_path = history_path(snapshot.get("monitor_key") or snapshot["asn"], path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a") as f:
        f.write(json.dumps(snapshot, sort_keys=True) + "\n")
    return file_path


def _fmt_path(path: list[str]) -> str:
    return " → ".join(path) if path else "unknown"


def _num(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) else None


def compare_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    rtt_threshold_ms: float = 25.0,
    loss_threshold_pct: float = 1.0,
    throughput_drop_pct: float = 30.0,
) -> list[str]:
    if previous is None:
        return ["No previous baseline — saved current measurement."]

    changes: list[str] = []
    prev_path = previous.get("as_path") or []
    cur_path = current.get("as_path") or []
    if prev_path != cur_path:
        changes.append(f"AS path changed: {_fmt_path(prev_path)} → {_fmt_path(cur_path)}")

    prev_rtt = _num(previous.get("p95_rtt_ms"))
    if prev_rtt is None:
        prev_rtt = _num(previous.get("last_rtt_ms"))
    cur_rtt = _num(current.get("p95_rtt_ms"))
    if cur_rtt is None:
        cur_rtt = _num(current.get("last_rtt_ms"))
    if prev_rtt is not None and cur_rtt is not None and cur_rtt - prev_rtt >= rtt_threshold_ms:
        changes.append(f"RTT regression: {prev_rtt:.1f} ms → {cur_rtt:.1f} ms")

    prev_loss = _num(previous.get("loss_pct"))
    cur_loss = _num(current.get("loss_pct"))
    if prev_loss is not None and cur_loss is not None and cur_loss - prev_loss >= loss_threshold_pct:
        changes.append(f"Packet loss increased: {prev_loss:.1f}% → {cur_loss:.1f}%")

    prev_dl = _num(previous.get("download_mbps"))
    cur_dl = _num(current.get("download_mbps"))
    if prev_dl and cur_dl is not None and cur_dl < prev_dl * (1 - throughput_drop_pct / 100.0):
        changes.append(f"Download throughput dropped: {prev_dl:.0f} Mbps → {cur_dl:.0f} Mbps")

    if previous.get("severity") != current.get("severity") and current.get("severity") in {"warning", "critical"}:
        changes.append(
            f"Verdict worsened: {previous.get('severity') or 'unknown'} → "
            f"{current.get('severity')} ({current.get('verdict') or 'unknown'})"
        )

    return changes or ["No regression detected."]
