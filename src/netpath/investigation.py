"""Normalize netpath outputs into a portable investigation report.

The CLI and TUI expose several result shapes.  This module keeps presentation
code independent of those shapes and provides a deliberately small, stable
view model for incident summaries and saved evidence bundles.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union


@dataclass(frozen=True)
class InvestigationResult:
    """A normalized, presentation-ready network investigation."""

    mode: str
    target: str
    verdict: str
    severity: str
    confidence: str
    culprit: str
    detail: str
    evidence: Tuple[str, ...]
    recommendation: str
    path: Tuple[Dict[str, Any], ...]
    baseline_changes: Tuple[str, ...]
    metrics: Tuple[Tuple[str, str], ...]
    raw: Dict[str, Any]


_SECRET_KEYS = {
    "auth",
    "authorization",
    "proxyauthorization",
    "apikey",
    "accesstoken",
    "refreshtoken",
    "token",
    "password",
    "passwd",
    "secret",
    "clientsecret",
    "secretkey",
    "awssecretaccesskey",
    "cookie",
    "setcookie",
    "webhook",
    "webhookurl",
    "credential",
    "credentials",
    "privatekey",
    "signature",
    "sig",
    "xamzsignature",
    "xgoogsignature",
}
_SECRET_NAME_PATTERN = (
    r"(?:aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key|"
    r"x[_-]?(?:amz|goog)[_-]?signature|(?:[a-z0-9]+[_-])*(?:authorization|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|"
    r"client[_-]?secret|secret|signature|sig))"
)
_QUOTED_ASSIGNED_SECRET_RE = re.compile(
    rf"(?i)([\"']?\b{_SECRET_NAME_PATTERN}\b[\"']?\s*[:=]\s*)"
    r'''(?:"[^"\r\n]*"|'[^'\r\n]*')'''
)
_ASSIGNED_SECRET_RE = re.compile(
    rf"(?i)([\"']?\b{_SECRET_NAME_PATTERN}\b[\"']?)(\s*[:=]\s*)"
    r"(?:bearer\s+)?([^\s,;&#\"']+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|token|password|secret|signature|sig|credential)=)[^&#\s]+"
)
_SENSITIVE_HEADER_RE = re.compile(
    r"(?im)\b((?:proxy-)?authorization|(?:set-)?cookie)(\s*:\s*)[^\r\n]+"
)
_URL_USERINFO_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@/\s]+)@"
)
_KNOWN_TOKEN_RE = re.compile(
    r"(?:\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{20,}\b|"
    r"\bgithub_pat_[0-9A-Za-z_]{20,}\b|\bgh[pousr]_[0-9A-Za-z]{20,}\b|"
    r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b|\bsk-(?:ant-)?[0-9A-Za-z_-]{16,}\b|"
    r"\beyJ[0-9A-Za-z_-]{8,}\.[0-9A-Za-z_-]{8,}\.[0-9A-Za-z_-]{8,}\b)"
)


def from_payload(
    mode: str,
    target: str,
    payload: Mapping[str, Any],
) -> InvestigationResult:
    """Normalize a CLI/TUI payload into :class:`InvestigationResult`.

    Supported payload families are flattened host/explain reports, DNS JSON
    snapshots, and city/ASN path results.  Unknown modes use the host/report
    normalizer, which is intentionally tolerant of missing optional fields.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    normalized_mode = str(mode).strip().lower() or "unknown"
    normalized_target = str(target).strip()
    raw = deepcopy(dict(payload))

    if normalized_mode == "dns" or (
        isinstance(payload.get("summary"), Mapping)
        and isinstance(payload.get("resolvers"), (list, tuple))
    ):
        return _from_dns(normalized_mode, normalized_target, payload, raw)
    if normalized_mode in {"city", "citypath", "aspath"} or (
        "candidates" in payload or "optimal_path" in payload
    ):
        return _from_path(normalized_mode, normalized_target, payload, raw)
    return _from_report(normalized_mode, normalized_target, payload, raw)


def render_markdown(result: InvestigationResult) -> str:
    """Render a concise, shareable incident report with secrets redacted."""

    lines = [
        "# netpath incident report",
        "",
        f"- **Target:** {_markdown_text(result.target)}",
        f"- **Mode:** {_markdown_text(result.mode)}",
        f"- **Verdict:** {_markdown_text(result.verdict)}",
        f"- **Severity:** {_markdown_text(result.severity)}",
        f"- **Confidence:** {_markdown_text(result.confidence)}",
        f"- **Likely culprit:** {_markdown_text(result.culprit)}",
    ]
    if result.detail:
        lines.extend(["", _markdown_text(result.detail)])

    if result.metrics:
        lines.extend(["", "## Key metrics", "", "| Metric | Value |", "| --- | --- |"])
        for label, value in result.metrics:
            lines.append(f"| {_markdown_cell(label)} | {_markdown_cell(value)} |")

    lines.extend(["", "## Evidence", ""])
    if result.evidence:
        lines.extend(f"- {_markdown_text(item)}" for item in result.evidence)
    else:
        lines.append("- No anomalous evidence was reported.")

    if result.baseline_changes:
        lines.extend(["", "## Baseline comparison", ""])
        lines.extend(
            f"- {_markdown_text(change)}" for change in result.baseline_changes
        )

    if result.path:
        lines.extend(
            [
                "",
                "## Path and observations",
                "",
                "| Step | Endpoint | Network / status | Latency | Observation |",
                "| ---: | --- | --- | ---: | --- |",
            ]
        )
        for index, row in enumerate(result.path, 1):
            step, endpoint, network, latency, observation = _path_row(index, row)
            lines.append(
                f"| {_markdown_cell(step)} | {_markdown_cell(endpoint)} | "
                f"{_markdown_cell(network)} | {_markdown_cell(latency)} | "
                f"{_markdown_cell(observation)} |"
            )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            _markdown_text(result.recommendation),
            "",
        ]
    )
    return "\n".join(lines)


def save_bundle(
    result: InvestigationResult,
    directory: Union[str, Path],
) -> Tuple[Path, Path]:
    """Save redacted Markdown and JSON files; return ``(markdown, json)`` paths."""

    root = Path(directory).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    basename = "-".join(
        (
            timestamp,
            _safe_slug(result.mode, "investigation"),
            _safe_slug(result.target, "target"),
        )
    )
    markdown_path = root / f"{basename}.md"
    json_path = root / f"{basename}.json"

    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    json_path.write_text(
        json.dumps(_bundle_payload(result), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return markdown_path, json_path


def _from_report(
    mode: str,
    target: str,
    payload: Mapping[str, Any],
    raw: Dict[str, Any],
) -> InvestigationResult:
    nested_verdict = payload.get("verdict")
    verdict_data = nested_verdict if isinstance(nested_verdict, Mapping) else {}
    verdict = _text(
        verdict_data.get("verdict")
        if verdict_data
        else nested_verdict,
        "Healthy" if _text(payload.get("severity"), "ok") == "ok" else "Needs attention",
    )
    severity = _text(payload.get("severity") or verdict_data.get("severity"), "ok").lower()
    evidence = _collect_evidence(
        payload.get("evidence"),
        payload.get("evidence_details"),
        verdict_data.get("signals"),
    )
    detail = _text(payload.get("detail") or verdict_data.get("detail"))
    if not detail and evidence:
        detail = evidence[0]
    confidence = _text(payload.get("confidence"), _signal_confidence(verdict_data) or "unknown")
    culprit = _culprit(payload, severity)
    path = _normalize_path(payload.get("path") or payload.get("hubs"))
    baseline_changes = _string_tuple(payload.get("baseline_changes"))
    recommendation = _text(
        payload.get("recommendation") or payload.get("recommended_action"),
        _default_recommendation(severity),
    )
    return InvestigationResult(
        mode=mode,
        target=target,
        verdict=verdict,
        severity=severity,
        confidence=confidence,
        culprit=culprit,
        detail=detail,
        evidence=evidence,
        recommendation=recommendation,
        path=path,
        baseline_changes=baseline_changes,
        metrics=_report_metrics(payload, path),
        raw=raw,
    )


def _from_dns(
    mode: str,
    target: str,
    payload: Mapping[str, Any],
    raw: Dict[str, Any],
) -> InvestigationResult:
    summary_value = payload.get("summary")
    summary = summary_value if isinstance(summary_value, Mapping) else {}
    resolver_value = payload.get("resolvers")
    resolvers = [
        dict(row)
        for row in resolver_value or []
        if isinstance(row, Mapping)
    ]
    responding = _integer(summary.get("responding"))
    agree = _integer(summary.get("agree"))
    errors = _integer(summary.get("errors"))
    groups = _integer(summary.get("groups"))
    none_count = _integer(summary.get("none"))
    servfail = _integer(summary.get("servfail"))
    percentage_value = summary.get("percentage")
    if percentage_value is None:
        percentage = round((agree / responding) * 100) if responding else 0
    else:
        percentage = _number(percentage_value)
    healthy = (
        responding > 0
        and agree == responding
        and errors == 0
        and groups <= 1
        and none_count == 0
        and servfail == 0
    )
    verdict = "Healthy" if healthy else "Propagation differs"
    severity = "ok" if healthy else ("critical" if responding == 0 else "warning")
    confidence = "low" if responding == 0 else ("high" if responding >= 3 else "medium")
    culprit = "none" if healthy else "DNS propagation"
    detail = (
        f"{agree}/{responding} responding resolvers agree ({_format_number(percentage)}%); "
        f"{errors} unreachable and {groups} answer group(s)."
    )

    majority_values = _values(summary.get("majority_values"))
    evidence: List[str] = []
    if majority_values:
        evidence.append(f"Majority answer: {', '.join(majority_values)}")
    majority_rows = summary.get("majority_rows")
    row_agreement = majority_rows if isinstance(majority_rows, (list, tuple)) else []
    differing: List[str] = []
    unreachable: List[str] = []
    for index, row in enumerate(resolvers):
        name = _text(row.get("name") or row.get("ip"), f"resolver {index + 1}")
        status = _text(row.get("status"), "unknown").lower()
        if status in {"error", "servfail", "none"}:
            unreachable.append(f"{name} ({status})")
            continue
        if index < len(row_agreement):
            agrees = bool(row_agreement[index])
        else:
            agrees = not majority_values or _values(row.get("values")) == majority_values
        if not agrees:
            answer = ", ".join(_values(row.get("values"))) or "no answer"
            differing.append(f"{name} returned {answer}")
    if differing:
        evidence.append("Different answers: " + "; ".join(differing))
    if unreachable:
        evidence.append("Unreachable or empty: " + "; ".join(unreachable))
    if healthy:
        evidence.append(
            f"All {responding} responding resolvers returned the majority answer."
        )
    if not evidence:
        evidence.append("No usable resolver responses were returned.")

    if responding == 0:
        recommendation = (
            "Verify network access and authoritative DNS availability, then retry the "
            "resolver checks."
        )
    elif healthy:
        recommendation = (
            "No DNS propagation issue was detected; continue monitoring if user reports persist."
        )
    else:
        recommendation = (
            "Confirm the authoritative records, allow at least one TTL for caches to expire, "
            "and rerun the propagation check."
        )

    metrics: List[Tuple[str, str]] = [
        ("Propagation", f"{_format_number(percentage)}%"),
        ("Responding", str(responding)),
        ("Answer groups", str(groups)),
        ("Errors", str(errors)),
    ]
    record_type = payload.get("record_type")
    if record_type:
        metrics.insert(0, ("Record type", _text(record_type)))
    return InvestigationResult(
        mode=mode,
        target=target,
        verdict=verdict,
        severity=severity,
        confidence=confidence,
        culprit=culprit,
        detail=detail,
        evidence=tuple(evidence),
        recommendation=recommendation,
        path=tuple(resolvers),
        baseline_changes=(),
        metrics=tuple(metrics),
        raw=raw,
    )


def _from_path(
    mode: str,
    target: str,
    payload: Mapping[str, Any],
    raw: Dict[str, Any],
) -> InvestigationResult:
    verdict_value = payload.get("verdict")
    verdict_data = verdict_value if isinstance(verdict_value, Mapping) else {}
    candidates_value = payload.get("candidates")
    candidates = [
        candidate
        for candidate in candidates_value or []
        if isinstance(candidate, Mapping)
    ]
    complete_count = sum(bool(candidate.get("reaches_target")) for candidate in candidates)
    inferred_incomplete = (
        _text(payload.get("path_status")).lower() == "incomplete"
        or (bool(candidates) and complete_count == 0)
        or ("optimal_path" in payload and not payload.get("optimal_path"))
    )
    default_severity = "warning" if inferred_incomplete else "ok"
    severity = _text(
        payload.get("severity") or verdict_data.get("severity"),
        default_severity,
    ).lower()
    verdict = _text(
        verdict_data.get("verdict") if verdict_data else verdict_value,
        "Target Network Observed" if severity == "ok" else "Incomplete Path",
    )
    selected = payload.get("optimal_path")
    if not isinstance(selected, Mapping):
        candidates = payload.get("candidates")
        selected = next(
            (candidate for candidate in candidates or [] if isinstance(candidate, Mapping)),
            {},
        )
    point_source = selected.get("hop_points") or selected.get("geo_points")
    path = _normalize_path(point_source)
    if not path:
        path = _normalize_path(payload.get("path") or selected.get("path"))

    evidence = _collect_evidence(
        payload.get("evidence"),
        payload.get("evidence_details"),
        verdict_data.get("signals"),
    )
    if not evidence:
        evidence = (
            f"Measured {len(candidates)} candidate path(s); "
            f"{complete_count} entered the destination ASN.",
        )
    detail = _text(payload.get("detail") or verdict_data.get("detail"))
    if not detail and evidence:
        detail = evidence[0]
    confidence = _text(payload.get("confidence"), _signal_confidence(verdict_data) or "unknown")
    culprit = _culprit(payload, severity)
    recommendation = _text(
        payload.get("recommendation") or payload.get("recommended_action"),
        _default_recommendation(severity),
    )
    return InvestigationResult(
        mode=mode,
        target=target,
        verdict=verdict,
        severity=severity,
        confidence=confidence,
        culprit=culprit,
        detail=detail,
        evidence=evidence,
        recommendation=recommendation,
        path=path,
        baseline_changes=_string_tuple(payload.get("baseline_changes")),
        metrics=_path_metrics(payload, selected, candidates, path),
        raw=raw,
    )


def _collect_evidence(*groups: Any) -> Tuple[str, ...]:
    evidence: List[str] = []
    seen = set()
    for group in groups:
        if group is None:
            continue
        items: Iterable[Any]
        if isinstance(group, (list, tuple)):
            items = group
        else:
            items = (group,)
        for item in items:
            text = _evidence_text(item)
            key = " ".join(text.lower().split())
            if text and key not in seen:
                seen.add(key)
                evidence.append(text)
    return tuple(evidence)


def _evidence_text(value: Any) -> str:
    if isinstance(value, Mapping):
        detail = _text(value.get("detail"))
        if detail:
            return detail
        condition = _text(value.get("condition"))
        source = _text(value.get("source"))
        label = condition.replace("_", " ").strip().capitalize()
        if label and source:
            return f"{label} observed by {source.replace('_', ' ')}."
        return label
    return _text(value)


def _normalize_path(value: Any) -> Tuple[Dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        if isinstance(item, Mapping):
            rows.append(deepcopy(dict(item)))
        elif item is not None:
            label = _text(item)
            row: Dict[str, Any] = {"hop": index, "label": label}
            if label.upper().startswith("AS"):
                row["asn"] = label
            rows.append(row)
    return tuple(rows)


def _report_metrics(
    payload: Mapping[str, Any],
    path: Tuple[Dict[str, Any], ...],
) -> Tuple[Tuple[str, str], ...]:
    metrics: List[Tuple[str, str]] = []
    _add_metric(metrics, "Jitter", payload.get("jitter_ms"), "ms")
    _add_metric(metrics, "TCP connect", payload.get("tcp_connect_ms"), "ms")
    _add_metric(metrics, "TLS handshake", payload.get("tls_handshake_ms"), "ms")
    throughput = payload.get("throughput")
    if isinstance(throughput, Mapping):
        _add_metric(metrics, "Download", throughput.get("download_mbps"), "Mbps")
        _add_metric(metrics, "Upload", throughput.get("upload_mbps"), "Mbps")
    if path:
        metrics.append(("Observed hops", str(len(path))))
        last_rtt = next(
            (
                row.get("avg_ms") if row.get("avg_ms") is not None else row.get("rtt_ms")
                for row in reversed(path)
                if row.get("avg_ms") is not None or row.get("rtt_ms") is not None
            ),
            None,
        )
        _add_metric(metrics, "Final RTT", last_rtt, "ms")
        losses = [
            _number(row.get("loss_pct"))
            for row in path
            if row.get("loss_pct") is not None
        ]
        if losses:
            _add_metric(metrics, "Maximum loss", max(losses), "%")
    return tuple(metrics)


def _path_metrics(
    payload: Mapping[str, Any],
    selected: Mapping[str, Any],
    candidates: List[Mapping[str, Any]],
    path: Tuple[Dict[str, Any], ...],
) -> Tuple[Tuple[str, str], ...]:
    metrics: List[Tuple[str, str]] = []
    ping = payload.get("ping_rtt")
    if isinstance(ping, Mapping):
        _add_metric(metrics, "Aggregate RTT", ping.get("avg"), "ms")
    _add_metric(metrics, "Best path RTT", selected.get("rtt_ms"), "ms")
    metrics.append(("Candidate paths", str(len(candidates))))
    metrics.append(
        (
            "Destination-ASN paths",
            str(sum(bool(candidate.get("reaches_target")) for candidate in candidates)),
        )
    )
    if path:
        metrics.append(("Observed hops", str(len(path))))
    target_ip = payload.get("target_ip")
    if target_ip:
        metrics.append(("Measurement target", _text(target_ip)))
    return tuple(metrics)


def _add_metric(
    metrics: List[Tuple[str, str]],
    label: str,
    value: Any,
    unit: str,
) -> None:
    if value is None or value == "":
        return
    rendered = _format_number(value)
    if unit == "%":
        rendered = f"{rendered}%"
    elif unit:
        rendered = f"{rendered} {unit}"
    metrics.append((label, rendered))


def _culprit(payload: Mapping[str, Any], severity: str) -> str:
    explicit = payload.get("culprit") or payload.get("likely_culprit")
    if isinstance(explicit, Mapping):
        explicit = explicit.get("asn") or explicit.get("scope")
    culprit_asn = _text(payload.get("culprit_asn"))
    culprit_scope = _text(payload.get("culprit_scope"))
    if culprit_asn and culprit_scope and culprit_scope != "none":
        return f"{culprit_asn} ({culprit_scope})"
    if culprit_asn:
        return culprit_asn
    if explicit and _text(explicit) != "none":
        return _text(explicit)
    if culprit_scope and culprit_scope != "none":
        return culprit_scope
    return "none" if severity == "ok" else "undetermined"


def _signal_confidence(verdict: Mapping[str, Any]) -> Optional[str]:
    signals = verdict.get("signals")
    if not isinstance(signals, (list, tuple)):
        return None
    for signal in signals:
        if isinstance(signal, Mapping) and signal.get("confidence"):
            return _text(signal.get("confidence"))
    return None


def _default_recommendation(severity: str) -> str:
    if severity == "ok":
        return "No escalation is required; rerun the investigation if symptoms recur."
    return "Rerun to confirm the finding, then share the evidence with the suspected network owner."


def _path_row(index: int, row: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    step = _text(row.get("hop") or row.get("count"), str(index))
    name = _text(row.get("name"))
    address = _text(row.get("host") or row.get("ip"))
    label = _text(row.get("label"))
    if name and address:
        endpoint = f"{name} ({address})"
    else:
        endpoint = name or address or label or "—"

    network = _text(row.get("asn") or row.get("ASN") or row.get("network"))
    location = _text(row.get("location"))
    status = _text(row.get("status"))
    network_parts = [part for part in (network, location, status) if part]
    network_status = " · ".join(network_parts) or (label if label != endpoint else "—")

    latency_value = row.get("avg_ms")
    if latency_value is None:
        latency_value = row.get("rtt_ms")
    if latency_value is None:
        latency_value = row.get("elapsed_ms")
    latency = f"{_format_number(latency_value)} ms" if latency_value is not None else "—"

    loss = row.get("loss_pct")
    if loss is None:
        loss = row.get("Loss%")
    if loss is not None:
        observation = f"{_format_number(loss)}% loss"
    else:
        values = _values(row.get("values"))
        observation = ", ".join(values) if values else _text(row.get("answer"), "—")
    return step, endpoint, network_status, latency, observation


def _bundle_payload(result: InvestigationResult) -> Dict[str, Any]:
    return _redact_value(
        {
            "schema_version": 1,
            "mode": result.mode,
            "target": result.target,
            "verdict": result.verdict,
            "severity": result.severity,
            "confidence": result.confidence,
            "culprit": result.culprit,
            "detail": result.detail,
            "evidence": list(result.evidence),
            "recommendation": result.recommendation,
            "path": list(result.path),
            "baseline_changes": list(result.baseline_changes),
            "metrics": [
                {"label": label, "value": value} for label, value in result.metrics
            ],
            "raw": result.raw,
        }
    )


def _redact_value(value: Any, key: str = "") -> Any:
    if key and _is_secret_key(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _is_secret_key(key: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", key.lower())
    return compact in _SECRET_KEYS or compact.endswith(
        (
            "apikey",
            "token",
            "password",
            "passwd",
            "secret",
            "authorization",
            "cookie",
            "credential",
            "credentials",
            "privatekey",
            "secretkey",
            "signature",
            "sig",
        )
    )


def _redact_text(value: str) -> str:
    text = _SENSITIVE_HEADER_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        value,
    )
    text = _URL_USERINFO_RE.sub(
        lambda match: f"{match.group(1)}[REDACTED]:[REDACTED]@",
        text,
    )
    text = _QUOTED_ASSIGNED_SECRET_RE.sub(
        lambda match: (
            f"{match.group(1)}{match.group(0)[-1]}[REDACTED]{match.group(0)[-1]}"
        ),
        text,
    )
    text = _ASSIGNED_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    text = _BEARER_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    text = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return _KNOWN_TOKEN_RE.sub("[REDACTED]", text)


def _markdown_text(value: Any) -> str:
    text = _redact_text(_text(value, "—")).replace("\r", " ").replace("\n", " ")
    return html.escape(text, quote=False)


def _markdown_cell(value: Any) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _safe_slug(value: Any, fallback: str) -> str:
    redacted = _redact_text(_text(value).strip())
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", redacted).strip("._-")
    return (slug or fallback)[:64]


def _string_tuple(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    items = value if isinstance(value, (list, tuple)) else (value,)
    return tuple(text for text in (_text(item) for item in items) if text)


def _values(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_number(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    number = _number(value)
    if isinstance(value, str) and value.strip() and number == 0 and value.strip() not in {"0", "0.0"}:
        return value.strip()
    return f"{number:g}"


__all__ = ["InvestigationResult", "from_payload", "render_markdown", "save_bundle"]
