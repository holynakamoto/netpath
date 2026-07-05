from __future__ import annotations

from typing import Optional

from netpath import servers
from netpath.cli_measurement import _run_test

_SEVERITY_CODE = {"ok": 0, "warning": 1, "critical": 2}


def _worst_exit_code(verdicts: list[dict]) -> int:
    return max((_SEVERITY_CODE.get(v.get("severity", "ok"), 0) for v in verdicts), default=0)


def _asn_json_payload(asn_norm: str, server: dict, result: dict) -> dict:
    upload_mbps = result.get("upload_mbps")
    download_mbps = result.get("download_mbps")
    verdict = result.get("verdict", {})
    target = {
        "type": "asn",
        "asn": asn_norm,
        "host": server["HOST"],
        "port": server.get("port"),
    }
    if server.get("SITE"):
        target["name"] = server["SITE"]
    if server.get("COUNTRY"):
        target["country"] = server["COUNTRY"]
    return {
        "asn": asn_norm,
        "target_host": server["HOST"],
        "target": target,
        "probes": _json_probes(result),
        "path": [_json_path_hop(hub) for hub in result.get("hubs", [])],
        "trace_fusion":      result.get("trace_fusion"),
        "throughput": (
            {"upload_mbps": upload_mbps, "download_mbps": download_mbps}
            if upload_mbps is not None or download_mbps is not None
            else None
        ),
        "jitter_ms":        result.get("jitter_ms"),
        "dns":              result.get("dns"),
        "http_edge":        result.get("http_edge"),
        "geo_path":         result.get("geo_path"),
        "tcp_connect_ms":   result.get("tcp_connect_ms"),
        "tls_handshake_ms": result.get("tls_handshake_ms"),
        "pmtu":             result.get("pmtu"),
        "ecmp_paths":       result.get("ecmp_paths"),
        "path_changes":     result.get("path_changes"),
        "bufferbloat_ms":   result.get("bufferbloat_ms"),
        "rum":              result.get("rum"),
        "verdict":          verdict,
        "confidence":       _json_confidence(verdict),
        "evidence":         _json_evidence(verdict),
        "recommendation":   _json_recommendation(verdict),
    }


def _json_path_hop(hub: dict) -> dict:
    item = {
        "hop":      hub.get("count"),
        "host":     hub.get("host"),
        "asn":      hub.get("ASN"),
        "loss_pct": hub.get("Loss%"),
        "avg_ms":   hub.get("Avg"),
        "best_ms":  hub.get("Best"),
        "worst_ms": hub.get("Wrst"),
        "p50_ms":   hub.get("p50"),
        "p95_ms":   hub.get("p95"),
        "p99_ms":   hub.get("p99"),
    }
    for source_key in ("sources", "variants", "filtered"):
        if source_key in hub:
            item[source_key] = hub.get(source_key)
    return item


def _endpoint_json_payload(endpoint: dict, result: dict) -> dict:
    payload = _asn_json_payload(endpoint.get("asn") or "AS???", {"HOST": endpoint["ip"]}, result)
    payload.update({
        "target_input": endpoint["input"],
        "target_host": endpoint["ip"],
        "resolved_ip": endpoint["ip"],
        "target_asn": endpoint.get("asn"),
        "target_name": endpoint.get("name"),
        "target_prefix": endpoint.get("prefix"),
    })
    payload["target"] = {
        "type": "host",
        "input": endpoint["input"],
        "host": endpoint.get("hostname") or endpoint["ip"],
        "resolved_ip": endpoint["ip"],
        "asn": endpoint.get("asn"),
        "name": endpoint.get("name"),
        "prefix": endpoint.get("prefix"),
    }
    return payload


def _json_probes(result: dict) -> dict:
    probes = {
        "local": {
            "sample_size": result.get("probe_count"),
            "trace_method": result.get("_trace_method"),
        }
    }
    if result.get("ecmp_paths") is not None or result.get("path_changes") is not None:
        probes["ecmp"] = {
            "paths": result.get("ecmp_paths"),
            "path_changes": result.get("path_changes"),
            "passes": result.get("ecmp_passes"),
        }
    if result.get("globalping"):
        gp = result["globalping"]
        probes["globalping"] = {
            "measurement_ids": gp.get("measurement_ids"),
            "ping_packets": gp.get("ping_packets"),
        }
    return probes


def _json_confidence(verdict: dict) -> str:
    signals = verdict.get("signals") or []
    non_ok = [sig for sig in signals if sig.get("severity") != "ok"]
    if non_ok:
        return max(non_ok, key=lambda sig: _SEVERITY_CODE.get(sig.get("severity", "ok"), 0)).get(
            "confidence"
        ) or "medium"
    if signals:
        return signals[0].get("confidence") or "high"
    return "high"


def _json_evidence(verdict: dict) -> list[dict]:
    evidence = []
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
        evidence.append(item)
    return evidence


def _json_recommendation(verdict: dict) -> str:
    conditions = {
        signal.get("condition")
        for signal in verdict.get("signals") or []
        if signal.get("severity") != "ok"
    }
    if not conditions:
        return "No escalation needed; keep monitoring if this is an intermittent incident."
    if "last_mile_congestion" in conditions:
        return "Escalate to the local access ISP with first-hop loss/bufferbloat evidence."
    if "remote_packet_loss" in conditions:
        return "Escalate to the destination network/SaaS provider with near-target packet-loss evidence."
    if "mid_path_packet_loss" in conditions:
        return "Escalate to the transit provider owning the lossy hop with downstream-loss evidence."
    if "pmtu_blackhole" in conditions:
        return "Escalate as an MTU/PMTUD black-hole and include the small-vs-large packet behavior."
    if {"tcp_latency", "tls_latency"} & conditions:
        return "Escalate to the destination application edge owner; TCP/TLS setup is the slow segment."
    if {"dns_latency", "http_ttfb_latency"} & conditions:
        return "Escalate to the DNS/application edge owner with lookup, TTFB, and redirect evidence."
    if "route_flapping" in conditions:
        return "Escalate route instability with the observed ECMP/path-change evidence."
    return "Share the report with the suspected network owner and rerun to confirm whether the condition persists."


def _apply_path_json_contract(result: dict) -> dict:
    if result.get("optimal_path"):
        path = result["optimal_path"].get("path") or []
        verdict = {"severity": "ok", "verdict": "Reachable Path", "signals": []}
        recommendation = "No escalation needed; the destination was reachable from the selected probes."
        confidence = "high"
        evidence = []
    else:
        path = result.get("partial_paths") or result.get("candidates") or []
        verdict = {
            "severity": "warning",
            "verdict": "Incomplete Path",
            "detail": result.get("path_note") or "No complete measured AS path reached the destination.",
            "signals": [],
        }
        recommendation = "Rerun with a different target or probe scope; escalate only if the destination is also unreachable."
        confidence = "low"
        evidence = [{
            "condition": "incomplete_path",
            "severity": "warning",
            "source": "globalping",
            "confidence": "low",
            "detail": verdict["detail"],
            "evidence": {"candidate_count": len(result.get("candidates") or [])},
        }]
    result["path"] = path
    result["probes"] = {
        "globalping": {
            "measurement_ids": result.get("measurement_ids"),
            "statuses": result.get("statuses"),
            "ping_packets": result.get("ping_packets"),
        }
    }
    result["verdict"] = verdict
    result["confidence"] = confidence
    result["evidence"] = evidence
    result["recommendation"] = recommendation
    return result


def _collect_asn_json(
    asn_norm: str,
    *,
    count: int,
    duration: int,
    cycles: int,
    skip_throughput: bool,
    cf_token: Optional[str],
    ecmp_passes: int = 1,
    compare_v6: bool = False,
    trace_fusion: bool = False,
    candidates: list[dict] | None = None,
    _run_test_impl=None,
) -> dict:
    run_test = _run_test_impl or _run_test
    found = candidates if candidates is not None else servers.find_servers_in_asn(asn_norm, max_count=count)
    if not found:
        raise RuntimeError(f"No public iperf3 servers found in {asn_norm}")
    server = found[0]
    result = run_test(
        host=server["HOST"], port=server["port"],
        server_meta=server, target_asn=asn_norm,
        cycles=cycles, duration=duration,
        skip_throughput=skip_throughput, cf_token=cf_token,
        json_mode=True, ecmp_passes=ecmp_passes, compare_v6=compare_v6,
        trace_fusion=trace_fusion,
    )
    return _asn_json_payload(asn_norm, server, result)


def _collect_endpoint_json(
    endpoint: dict,
    *,
    duration: int,
    cycles: int,
    skip_throughput: bool,
    cf_token: Optional[str],
    ecmp_passes: int = 1,
    compare_v6: bool = False,
    trace_fusion: bool = False,
    json_mode: bool = True,
    show_operator_answer: bool = True,
    _run_test_impl=None,
) -> dict:
    run_test = _run_test_impl or _run_test
    target_asn = endpoint.get("asn") or "AS???"
    meta = {
        "HOST": endpoint["ip"],
        "SITE": endpoint.get("input") or "",
        "asn": target_asn,
        "port": 5201,
    }
    result = run_test(
        host=endpoint["ip"], port=5201,
        server_meta=meta, target_asn=target_asn,
        cycles=cycles, duration=duration,
        skip_throughput=skip_throughput, cf_token=cf_token,
        json_mode=json_mode, ecmp_passes=ecmp_passes, compare_v6=compare_v6,
        service_host=endpoint.get("hostname") or endpoint.get("input"),
        trace_fusion=trace_fusion,
        show_operator_answer=show_operator_answer,
    )
    return _endpoint_json_payload(endpoint, result)
