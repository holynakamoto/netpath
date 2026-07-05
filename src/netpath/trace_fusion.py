from __future__ import annotations

import concurrent.futures
import statistics
from typing import Callable

from netpath import mtr, paris

MAX_FUSION_PROBES = 5


def _is_responsive(hub: dict) -> bool:
    return hub.get("host") not in ("???", None, "")


def _run_method(name: str, fn: Callable[[], list[dict]]) -> dict:
    try:
        return {"name": name, "hubs": fn(), "error": None}
    except mtr.TraceTimeout as exc:
        return {"name": name, "hubs": exc.hubs, "error": "timed out (partial path shown)"}
    except Exception as exc:
        return {"name": name, "hubs": [], "error": str(exc) or exc.__class__.__name__}


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    return mtr._percentile(sorted(values), p)


def _fuse_hop(ttl: int, samples: list[tuple[str, dict]], method_count: int) -> dict:
    responsive = [(method, hub) for method, hub in samples if _is_responsive(hub)]
    if not responsive:
        return {
            "count": ttl,
            "host": "???",
            "ASN": "AS???",
            "Loss%": 100.0,
            "Avg": 0.0,
            "Best": 0.0,
            "Wrst": 0.0,
            "StDev": 0.0,
            "p50": None,
            "p95": None,
            "p99": None,
            "sources": [],
            "variants": [],
            "filtered": True,
            "status": "silent",
            "confidence": "low",
        }

    by_host: dict[str, dict] = {}
    for method, hub in responsive:
        host = hub.get("host") or "???"
        entry = by_host.setdefault(host, {
            "host": host,
            "ASN": hub.get("ASN", "AS???"),
            "asn_name": hub.get("asn_name"),
            "sources": [],
            "rtts": [],
            "loss": [],
        })
        entry["sources"].append(method)
        if hub.get("ASN") and entry.get("ASN") == "AS???":
            entry["ASN"] = hub["ASN"]
        if hub.get("asn_name") and not entry.get("asn_name"):
            entry["asn_name"] = hub["asn_name"]
        for key in ("Avg", "Best", "Wrst", "p50", "p95", "p99"):
            value = hub.get(key)
            if isinstance(value, (int, float)) and value > 0:
                entry["rtts"].append(float(value))
        loss = hub.get("Loss%")
        if isinstance(loss, (int, float)):
            entry["loss"].append(float(loss))

    best = max(by_host.values(), key=lambda item: (len(item["sources"]), -min(item["rtts"] or [0])))
    rtts = best["rtts"]
    losses = best["loss"]
    variants = [
        {
            "host": item["host"],
            "asn": item.get("ASN"),
            "sources": sorted(item["sources"]),
        }
        for item in sorted(by_host.values(), key=lambda item: (-len(item["sources"]), item["host"]))
    ]
    hub = {
        "count": ttl,
        "host": best["host"],
        "ASN": best.get("ASN", "AS???"),
        "Loss%": round(sum(losses) / len(losses), 1) if losses else round((method_count - len(responsive)) / method_count * 100.0, 1),
        "Avg": round(sum(rtts) / len(rtts), 2) if rtts else 0.0,
        "Best": round(min(rtts), 2) if rtts else 0.0,
        "Wrst": round(max(rtts), 2) if rtts else 0.0,
        "StDev": round(statistics.stdev(rtts) if len(rtts) > 1 else 0.0, 2),
        "p50": round(_percentile(rtts, 50), 2) if rtts else None,
        "p95": round(_percentile(rtts, 95), 2) if rtts else None,
        "p99": round(_percentile(rtts, 99), 2) if rtts else None,
        "sources": sorted(best["sources"]),
        "variants": variants,
        "filtered": False,
        "status": "responsive",
        "confidence": "high" if len(best["sources"]) >= 2 else "medium",
    }
    if best.get("asn_name"):
        hub["asn_name"] = best["asn_name"]
    return hub


def _filtered_ranges(hubs: list[dict]) -> list[dict]:
    ranges = []
    start = None
    prev = None
    for hub in hubs:
        if hub.get("filtered"):
            if start is None:
                start = hub["count"]
            prev = hub["count"]
        elif start is not None:
            ranges.append({"start": start, "end": prev})
            start = None
    if start is not None:
        ranges.append({"start": start, "end": prev})
    return ranges


def _annotate_silence(hubs: list[dict]) -> None:
    responsive_counts = {
        hub.get("count")
        for hub in hubs
        if not hub.get("filtered")
    }
    for hub in hubs:
        if not hub.get("filtered"):
            continue
        ttl = hub.get("count")
        downstream_seen = any(
            isinstance(other, int) and isinstance(ttl, int) and other > ttl
            for other in responsive_counts
        )
        if downstream_seen:
            hub["status"] = "rate_limited_or_filtered"
            hub["confidence"] = "medium"
        else:
            hub["status"] = "filtered_after_last_reply"
            hub["confidence"] = "low"


def _topology_summary(hubs: list[dict]) -> dict:
    branch_points = []
    for hub in hubs:
        variants = hub.get("variants") or []
        if len(variants) <= 1:
            continue
        branch_points.append({
            "hop": hub.get("count"),
            "variants": variants,
        })
    responsive = [hub for hub in hubs if not hub.get("filtered")]
    silent = [hub for hub in hubs if hub.get("filtered")]
    return {
        "mode": "graph" if branch_points else "linear",
        "responsive_hops": len(responsive),
        "silent_hops": len(silent),
        "branch_points": branch_points,
    }


def _method_confidence(successful_count: int, fused: list[dict]) -> str:
    if successful_count <= 1:
        return "low"
    corroborated = any(len(hub.get("sources") or []) >= 2 for hub in fused if not hub.get("filtered"))
    if successful_count >= 3 and corroborated:
        return "high"
    return "medium" if corroborated else "low"


def run(host: str, cycles: int = 10, prefer_tcp: bool = False) -> tuple[list[dict], dict]:
    probes = max(1, min(cycles, MAX_FUSION_PROBES))
    methods: list[tuple[str, Callable[[], list[dict]]]] = []
    if mtr.available():
        methods.append(("mtr", lambda: mtr.run(host, cycles=probes)))
    binary = paris.detect()
    if binary is not None:
        methods.append((binary, lambda binary=binary: paris.run(host, probes=probes, binary=binary)))
    traceroute = mtr.traceroute_path()
    if traceroute is not None:
        ordered = [("traceroute-tcp", True), ("traceroute-udp", False)] if prefer_tcp else [
            ("traceroute-udp", False), ("traceroute-tcp", True)
        ]
        for name, tcp in ordered:
            methods.append((name, lambda tcp=tcp: mtr._run_traceroute_cmd(host, tcp=tcp, probes=probes)))
    if not methods:
        raise RuntimeError("no trace fusion probers available")

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(methods)) as executor:
        futures = [executor.submit(_run_method, name, fn) for name, fn in methods]
        for fut in futures:
            results.append(fut.result())

    successful = [item for item in results if item.get("hubs")]
    if not successful:
        errors = "; ".join(f"{item['name']}: {item['error']}" for item in results)
        raise RuntimeError(errors or "all trace fusion probers failed")

    by_ttl: dict[int, list[tuple[str, dict]]] = {}
    max_ttl = 0
    for item in successful:
        for hub in item["hubs"]:
            ttl = hub.get("count")
            if not isinstance(ttl, int):
                continue
            max_ttl = max(max_ttl, ttl)
            by_ttl.setdefault(ttl, []).append((item["name"], hub))

    fused = [_fuse_hop(ttl, by_ttl.get(ttl, []), len(successful)) for ttl in range(1, max_ttl + 1)]
    _annotate_silence(fused)
    mtr._enrich_names(fused)
    topology = _topology_summary(fused)
    metadata = {
        "enabled": True,
        "probes_per_method": probes,
        "confidence": _method_confidence(len(successful), fused),
        "methods": [
            {
                "name": item["name"],
                "status": "ok" if item.get("hubs") else "error",
                "hop_count": len(item.get("hubs") or []),
                "error": item.get("error"),
            }
            for item in results
        ],
        "filtered_ranges": _filtered_ranges(fused),
        "topology": topology,
    }
    return fused, metadata
