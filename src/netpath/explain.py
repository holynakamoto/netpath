from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from netpath import monitor


def load_baseline(path: str) -> dict[str, Any] | None:
    """Load the newest JSON object from a snapshot JSON or JSONL history file."""
    text = Path(path).expanduser().read_text()
    stripped = text.strip()
    if not stripped:
        return None

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        latest = None
        for line in stripped.splitlines():
            line = line.strip()
            if line:
                latest = json.loads(line)
        return latest if isinstance(latest, dict) else None

    if isinstance(data, list):
        latest = data[-1] if data else None
        return latest if isinstance(latest, dict) else None
    if isinstance(data, dict):
        return data
    return None


def build_report(
    *,
    destination: str,
    result: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = result.get("verdict") or {}
    path = _path_from_result(result)
    target_asn = result.get("target_asn") or result.get("asn") or _last_known_asn(path)
    as_path = _as_path(path)
    result_for_inference = {**result, "path": path}
    current = monitor.snapshot_from_result(
        result_for_inference,
        asn=target_asn or "AS???",
        target_host=result.get("target_host") or result.get("resolved_ip") or destination,
        monitor_key=result.get("target_input") or destination,
    )
    baseline_changes = (
        monitor.compare_snapshots(baseline, current)
        if baseline is not None
        else []
    )
    culprit = _infer_culprit(result_for_inference, baseline)
    evidence = _build_evidence(result_for_inference, baseline_changes, as_path)
    recommendation = _recommended_action(culprit, verdict)
    summary = _ticket_summary(destination, result_for_inference, verdict, culprit, evidence, baseline_changes, recommendation)
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
        "evidence_details": _signal_evidence(verdict),
        "path": path,
        "probes": result.get("probes"),
        "baseline_changes": baseline_changes,
        "recommendation": recommendation,
        "recommended_action": recommendation,
        "ticket_summary": summary,
    }


def build_operator_answer(
    *,
    destination: str,
    result: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = result.get("verdict") or {}
    path = _path_from_result(result)
    as_path = _as_path(path)
    result_for_inference = {**result, "path": path}
    baseline_changes: list[str] = []
    if baseline is not None:
        target_asn = result.get("target_asn") or result.get("asn") or _last_known_asn(path) or "AS???"
        current = monitor.snapshot_from_result(
            result_for_inference,
            asn=target_asn,
            target_host=result.get("target_host") or result.get("resolved_ip") or destination,
            monitor_key=result.get("target_input") or destination,
        )
        baseline_changes = monitor.compare_snapshots(baseline, current)
    culprit = _infer_culprit(result_for_inference, baseline)
    evidence = _operator_evidence(result_for_inference, baseline_changes, as_path)
    return {
        "destination": destination,
        "verdict": verdict.get("verdict", "Healthy"),
        "severity": verdict.get("severity", "ok"),
        "likely_culprit": culprit.get("asn") or culprit.get("scope") or "none",
        "culprit_asn": culprit.get("asn"),
        "culprit_scope": culprit.get("scope"),
        "confidence": result.get("confidence") or culprit.get("confidence") or "unknown",
        "evidence": evidence,
        "recommendation": result.get("recommendation") or _recommended_action(culprit, verdict),
    }


def build_country_operator_answer(code: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = [
        row for row in rows
        if (row.get("verdict") or {}).get("severity") in {"warning", "critical"}
    ]
    if not ranked:
        return None
    ranked.sort(
        key=lambda row: (
            {"warning": 1, "critical": 2}.get((row.get("verdict") or {}).get("severity"), 0),
            row.get("verified_rtt_ms") or 0,
        ),
        reverse=True,
    )
    top = ranked[0]
    destination = " ".join(p for p in (top.get("asn"), top.get("name")) if p) or code
    answer = build_operator_answer(destination=destination, result=top)
    affected = [
        f"{row.get('asn', 'AS???')} {((row.get('verdict') or {}).get('verdict') or 'warning')}"
        for row in ranked[:3]
    ]
    if len(ranked) > 3:
        affected.append(f"+{len(ranked) - 3} more")
    answer["destination"] = code
    answer["evidence"] = [f"Affected networks: {', '.join(affected)}"] + answer.get("evidence", [])[:2]
    return answer


def _path_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    path = result.get("path") or []
    if path:
        return path
    return [
        {
            "hop": hub.get("count"),
            "host": hub.get("host"),
            "asn": hub.get("ASN"),
            "loss_pct": hub.get("Loss%"),
            "avg_ms": hub.get("Avg"),
            "p95_ms": hub.get("p95"),
        }
        for hub in result.get("hubs") or []
    ]


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
    target_asn = result.get("target_asn") or result.get("asn") or _last_known_asn(path)

    if baseline and baseline.get("as_path") != current_as_path:
        changed_asn = _path_divergence_asn(current_as_path, baseline.get("as_path") or [])
        if changed_asn:
            return {"asn": changed_asn, "scope": "route-change", "confidence": "medium"}

    if "last_mile_congestion" in conditions:
        signal = _signal_for(verdict, "last_mile_congestion") or {}
        first = (signal.get("evidence") or {}).get("first_hop") or {}
        fallback = path[0] if path else {}
        return {
            "asn": first.get("asn") or fallback.get("asn"),
            "scope": "local-access",
            "confidence": signal.get("confidence") or "medium",
        }

    if "mid_path_packet_loss" in conditions:
        signal = _signal_for(verdict, "mid_path_packet_loss") or {}
        hop = (signal.get("evidence") or {}).get("loss_hop") or {}
        fallback = _first_lossy_hop(path) or {}
        return {
            "asn": hop.get("asn") or fallback.get("asn"),
            "scope": "transit-hop",
            "confidence": signal.get("confidence") or "medium",
        }

    if "remote_packet_loss" in conditions:
        return {"asn": target_asn, "scope": "near-target", "confidence": "high"}

    if "incomplete_path" in conditions:
        hop = _last_responsive_hop(path) or {}
        return {"asn": hop.get("asn"), "scope": "last-responsive-hop", "confidence": "low"}

    if "pmtu_blackhole" in conditions:
        signal = _signal_for(verdict, "pmtu_blackhole") or {}
        return {"asn": target_asn, "scope": "path-mtu", "confidence": signal.get("confidence") or "medium"}

    if {"tcp_latency", "tls_latency"} & conditions:
        signal = _signal_for(verdict, "tcp_latency") or _signal_for(verdict, "tls_latency") or {}
        return {"asn": target_asn, "scope": "application-edge", "confidence": signal.get("confidence") or "medium"}

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
    for signal in verdict.get("signals") or []:
        evidence.append(_format_signal_evidence(signal))
    if not evidence and verdict.get("detail"):
        evidence.append(verdict["detail"])
    evidence.extend(change for change in baseline_changes if change != "No regression detected.")
    if as_path:
        evidence.append("AS path: " + " → ".join(as_path))
    return evidence


def _operator_evidence(
    result: dict[str, Any],
    baseline_changes: list[str],
    as_path: list[str],
) -> list[str]:
    contract_evidence = _format_contract_evidence(result.get("evidence") or [])
    if contract_evidence:
        evidence = contract_evidence
        evidence.extend(change for change in baseline_changes if change != "No regression detected.")
        if as_path:
            evidence.append("AS path: " + " → ".join(as_path))
        return evidence
    return _build_evidence(result, baseline_changes, as_path)


def _format_contract_evidence(items: list[Any]) -> list[str]:
    evidence = []
    for item in items:
        if isinstance(item, str):
            evidence.append(item)
        elif isinstance(item, dict):
            evidence.append(_format_signal_evidence(item))
    return evidence


def _signal_for(verdict: dict[str, Any], condition: str) -> dict[str, Any] | None:
    for signal in verdict.get("signals") or []:
        if signal.get("condition") == condition:
            return signal
    return None


def _signal_evidence(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    details = []
    for signal in verdict.get("signals") or []:
        item = {
            "condition": signal.get("condition"),
            "severity": signal.get("severity"),
            "source": signal.get("source"),
            "confidence": signal.get("confidence"),
            "detail": signal.get("detail"),
            "evidence": signal.get("evidence") or {},
        }
        if signal.get("sample_size") is not None:
            item["sample_size"] = signal["sample_size"]
        details.append(item)
    return details


def _format_signal_evidence(signal: dict[str, Any]) -> str:
    parts = [signal.get("detail") or signal.get("condition") or "Signal"]
    source = signal.get("source")
    confidence = signal.get("confidence")
    if source or confidence:
        parts.append(f"({source or 'unknown source'}, confidence {confidence or 'unknown'})")
    evidence = signal.get("evidence") or {}
    if evidence:
        parts.append(json.dumps(evidence, sort_keys=True))
    return " ".join(parts)


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
