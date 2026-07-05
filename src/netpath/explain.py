from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from netpath import monitor


def load_baseline(path: str) -> dict[str, Any] | None:
    """Load the newest JSON object from a snapshot JSON or JSONL history file."""
    latest = None
    try:
        with Path(path).expanduser().open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                latest = json.loads(line)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError:
        with Path(path).expanduser().open() as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[-1] if data else None
        if isinstance(data, dict):
            return data
        return None
    return latest


def build_report(
    *,
    destination: str,
    result: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = result.get("verdict") or {}
    path = result.get("path") or []
    target_asn = result.get("target_asn") or _last_known_asn(path)
    as_path = _as_path(path)
    current = monitor.snapshot_from_result(
        result,
        asn=target_asn or "AS???",
        target_host=result.get("target_host") or result.get("resolved_ip") or destination,
        monitor_key=result.get("target_input") or destination,
    )
    baseline_changes = (
        monitor.compare_snapshots(baseline, current)
        if baseline is not None
        else []
    )
    culprit = _infer_culprit(result, baseline)
    evidence = _build_evidence(result, baseline_changes, as_path)
    recommendation = _recommended_action(culprit, verdict)
    summary = _ticket_summary(destination, result, verdict, culprit, evidence, baseline_changes, recommendation)
    return {
        "destination": destination,
        "target": {
            "input": result.get("target_input") or destination,
            "host": result.get("target_host"),
            "resolved_ip": result.get("resolved_ip"),
            "asn": target_asn,
            "name": result.get("target_name"),
        },
        "verdict": verdict.get("verdict", "Healthy"),
        "severity": verdict.get("severity", "ok"),
        "culprit_asn": culprit["asn"],
        "culprit_scope": culprit["scope"],
        "confidence": culprit["confidence"],
        "evidence": evidence,
        "baseline_changes": baseline_changes,
        "recommended_action": recommendation,
        "ticket_summary": summary,
    }


def _as_path(path: list[dict[str, Any]]) -> list[str]:
    asns: list[str] = []
    for hop in path:
        asn = hop.get("asn")
        if asn and asn != "AS???" and (not asns or asns[-1] != asn):
            asns.append(asn)
    return asns


def _last_known_asn(path: list[dict[str, Any]]) -> str | None:
    for hop in reversed(path):
        asn = hop.get("asn")
        if asn and asn != "AS???":
            return asn
    return None


def _last_responsive_hop(path: list[dict[str, Any]]) -> dict[str, Any] | None:
    for hop in reversed(path):
        if hop.get("host") not in ("???", None, ""):
            return hop
    return None


def _first_lossy_hop(path: list[dict[str, Any]]) -> dict[str, Any] | None:
    responsive = [
        hop for hop in path
        if hop.get("host") not in ("???", None, "")
    ]
    if len(responsive) < 2:
        return None
    for hop in responsive[1:-1]:
        loss = hop.get("loss_pct")
        if isinstance(loss, (int, float)) and loss > 1.0:
            return hop
    return None


def _path_divergence_asn(current: list[str], previous: list[str]) -> str | None:
    for idx, asn in enumerate(current):
        if idx >= len(previous) or previous[idx] != asn:
            return asn
    return None


def _infer_culprit(result: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, str | None]:
    verdict = result.get("verdict") or {}
    signals = verdict.get("signals") or []
    conditions = {sig.get("condition") for sig in signals}
    path = result.get("path") or []
    current_as_path = _as_path(path)
    target_asn = result.get("target_asn") or _last_known_asn(path)

    if baseline and baseline.get("as_path") != current_as_path:
        changed_asn = _path_divergence_asn(current_as_path, baseline.get("as_path") or [])
        if changed_asn:
            return {"asn": changed_asn, "scope": "route-change", "confidence": "medium"}

    if "last_mile_congestion" in conditions:
        first = path[0] if path else {}
        return {"asn": first.get("asn"), "scope": "local-access", "confidence": "medium"}

    if "mid_path_packet_loss" in conditions:
        hop = _first_lossy_hop(path) or {}
        return {"asn": hop.get("asn"), "scope": "transit-hop", "confidence": "medium"}

    if "remote_packet_loss" in conditions:
        return {"asn": target_asn, "scope": "near-target", "confidence": "high"}

    if "incomplete_path" in conditions:
        hop = _last_responsive_hop(path) or {}
        return {"asn": hop.get("asn"), "scope": "last-responsive-hop", "confidence": "low"}

    if "pmtu_blackhole" in conditions:
        return {"asn": target_asn, "scope": "path-mtu", "confidence": "medium"}

    if {"tcp_latency", "tls_latency"} & conditions:
        return {"asn": target_asn, "scope": "application-edge", "confidence": "medium"}

    if "route_flapping" in conditions:
        return {"asn": target_asn, "scope": "routing-instability", "confidence": "medium"}

    if verdict.get("severity") in {"warning", "critical"}:
        return {"asn": target_asn, "scope": "measured-path", "confidence": "low"}

    return {"asn": None, "scope": "none", "confidence": "high"}


def _build_evidence(
    result: dict[str, Any],
    baseline_changes: list[str],
    as_path: list[str],
) -> list[str]:
    evidence: list[str] = []
    verdict = result.get("verdict") or {}
    if verdict.get("detail"):
        evidence.append(verdict["detail"])
    evidence.extend(change for change in baseline_changes if change != "No regression detected.")
    if as_path:
        evidence.append("AS path: " + " → ".join(as_path))

    throughput = result.get("throughput") or {}
    metrics = []
    if result.get("jitter_ms") is not None:
        metrics.append(f"jitter {result['jitter_ms']:.1f} ms")
    if throughput.get("download_mbps") is not None:
        metrics.append(f"download {throughput['download_mbps']:.0f} Mbps")
    if result.get("tcp_connect_ms") is not None:
        metrics.append(f"TCP connect {result['tcp_connect_ms']:.0f} ms")
    if result.get("tls_handshake_ms") is not None:
        metrics.append(f"TLS handshake {result['tls_handshake_ms']:.0f} ms")
    if metrics:
        evidence.append("Measured: " + ", ".join(metrics))
    return evidence


def _recommended_action(culprit: dict[str, str | None], verdict: dict[str, Any]) -> str:
    scope = culprit.get("scope")
    asn = culprit.get("asn")
    if scope == "none":
        return "No escalation needed; keep monitoring if this is an intermittent incident."
    if scope == "local-access":
        return "Escalate to the local access ISP with first-hop loss/bufferbloat evidence."
    if scope == "route-change":
        return f"Escalate the route regression to the network owning {asn} and include the old/new AS paths."
    if scope == "near-target":
        return f"Escalate to the destination network/SaaS provider for {asn}; the anomaly is visible near the target."
    if scope == "path-mtu":
        return "Escalate as an MTU/PMTUD black-hole and include the small-vs-large packet behavior."
    if scope == "application-edge":
        return f"Escalate to the destination application edge owner for {asn}; TCP/TLS setup is the slow segment."
    if verdict.get("severity") == "critical":
        return "Escalate immediately with the attached path evidence and rerun after mitigation."
    return "Share the report with the suspected network owner and rerun to confirm whether the condition persists."


def _ticket_summary(
    destination: str,
    result: dict[str, Any],
    verdict: dict[str, Any],
    culprit: dict[str, str | None],
    evidence: list[str],
    baseline_changes: list[str],
    recommendation: str,
) -> str:
    target = result.get("resolved_ip") or result.get("target_host") or destination
    culprit_label = culprit.get("asn") or culprit.get("scope") or "unknown"
    lines = [
        f"netpath diagnosed {destination} ({target}) as {verdict.get('severity', 'ok')} / {verdict.get('verdict', 'Healthy')}.",
        f"Likely culprit: {culprit_label} ({culprit.get('scope')}, confidence {culprit.get('confidence')}).",
    ]
    if evidence:
        lines.append("Evidence: " + " | ".join(evidence[:4]))
    if baseline_changes:
        lines.append("Baseline comparison: " + " | ".join(baseline_changes))
    lines.append("Requested action: " + recommendation)
    return "\n".join(lines)
