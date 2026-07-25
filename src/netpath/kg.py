"""Knowledge graph over network topology, derived from netpath's own diagnosis history.

Nodes are ASNs; edges record how often two ASNs appeared adjacent in an
observed AS path, and what severities came with those observations. The graph
is a materialized view over monitor.py's append-only snapshot history — it is
never a second source of truth, so it is rebuilt from that history rather
than maintained as hand-updated graph state.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import networkx as nx

from netpath import monitor

_DEGRADED_SEVERITIES = {"warning", "critical"}


def _iter_snapshots(store_path: str | None = None) -> Iterator[dict[str, Any]]:
    store = monitor.store_dir(store_path)
    if not store.exists():
        return
    for file in sorted(store.glob("*.jsonl")):
        for line in file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                snapshot = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(snapshot, dict):
                yield snapshot


def build_graph(store_path: str | None = None) -> nx.DiGraph:
    """Rebuild the AS-adjacency graph from every saved diagnosis snapshot."""
    graph = nx.DiGraph()
    for snapshot in _iter_snapshots(store_path):
        as_path = snapshot.get("as_path") or []
        severity = snapshot.get("severity") or "unknown"
        timestamp = snapshot.get("timestamp")
        for hop_asn in as_path:
            graph.add_node(hop_asn)
        for upstream, downstream in zip(as_path, as_path[1:]):
            if graph.has_edge(upstream, downstream):
                edge = graph[upstream][downstream]
                edge["observations"] += 1
                edge["severity_counts"][severity] = edge["severity_counts"].get(severity, 0) + 1
                if timestamp and (edge["last_seen"] is None or timestamp > edge["last_seen"]):
                    edge["last_seen"] = timestamp
            else:
                graph.add_edge(
                    upstream,
                    downstream,
                    observations=1,
                    severity_counts={severity: 1},
                    last_seen=timestamp,
                )
    return graph


def segment_history(graph: nx.DiGraph, upstream: str, downstream: str) -> dict[str, Any] | None:
    """Everything the graph has observed about one AS-to-AS hop, or None if never seen."""
    if not graph.has_edge(upstream, downstream):
        return None
    return dict(graph[upstream][downstream])


def flag_known_bad_segments(
    graph: nx.DiGraph,
    as_path: list[str],
    *,
    min_observations: int = 2,
    degraded_rate_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Given a currently observed AS path, surface hops with a history of trouble.

    A segment is flagged once it has been seen at least `min_observations`
    times and at least `degraded_rate_threshold` of those observations were
    warning/critical severity.
    """
    flagged = []
    for upstream, downstream in zip(as_path, as_path[1:]):
        history = segment_history(graph, upstream, downstream)
        if not history or history["observations"] < min_observations:
            continue
        degraded = sum(
            count for sev, count in history["severity_counts"].items() if sev in _DEGRADED_SEVERITIES
        )
        rate = degraded / history["observations"]
        if rate >= degraded_rate_threshold:
            flagged.append(
                {
                    "upstream": upstream,
                    "downstream": downstream,
                    "degraded_rate": round(rate, 2),
                    **history,
                }
            )
    return flagged
