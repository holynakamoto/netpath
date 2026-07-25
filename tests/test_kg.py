from netpath import kg, monitor


def _snapshot(as_path, severity, timestamp="2026-01-01T00:00:00Z"):
    return {
        "as_path": as_path,
        "severity": severity,
        "timestamp": timestamp,
        "monitor_key": as_path[-1] if as_path else "unknown",
        "asn": as_path[-1] if as_path else "AS???",
    }


def test_empty_store_yields_empty_graph(tmp_path):
    graph = kg.build_graph(store_path=str(tmp_path))
    assert graph.number_of_nodes() == 0


def test_missing_store_dir_yields_empty_graph(tmp_path):
    graph = kg.build_graph(store_path=str(tmp_path / "does-not-exist"))
    assert graph.number_of_nodes() == 0


def test_build_graph_counts_adjacent_asn_observations(tmp_path):
    monitor.append_snapshot(_snapshot(["AS1", "AS2", "AS3"], "ok"), path=str(tmp_path))
    monitor.append_snapshot(_snapshot(["AS1", "AS2", "AS3"], "critical"), path=str(tmp_path))

    graph = kg.build_graph(store_path=str(tmp_path))

    assert graph.has_edge("AS1", "AS2")
    history = kg.segment_history(graph, "AS1", "AS2")
    assert history["observations"] == 2
    assert history["severity_counts"] == {"ok": 1, "critical": 1}


def test_segment_history_is_none_for_unseen_hop(tmp_path):
    graph = kg.build_graph(store_path=str(tmp_path))
    assert kg.segment_history(graph, "AS1", "AS2") is None


def test_flag_known_bad_segments_requires_min_observations(tmp_path):
    monitor.append_snapshot(_snapshot(["AS1", "AS2"], "critical"), path=str(tmp_path))

    graph = kg.build_graph(store_path=str(tmp_path))

    assert kg.flag_known_bad_segments(graph, ["AS1", "AS2"]) == []


def test_flag_known_bad_segments_surfaces_high_degraded_rate(tmp_path):
    for severity in ("critical", "critical", "ok"):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], severity), path=str(tmp_path))

    graph = kg.build_graph(store_path=str(tmp_path))
    flagged = kg.flag_known_bad_segments(graph, ["AS1", "AS2"], min_observations=2)

    assert len(flagged) == 1
    assert flagged[0]["upstream"] == "AS1"
    assert flagged[0]["downstream"] == "AS2"
    assert flagged[0]["degraded_rate"] == round(2 / 3, 2)


def test_flag_known_bad_segments_skips_healthy_hops(tmp_path):
    for _ in range(3):
        monitor.append_snapshot(_snapshot(["AS1", "AS2"], "ok"), path=str(tmp_path))

    graph = kg.build_graph(store_path=str(tmp_path))
    assert kg.flag_known_bad_segments(graph, ["AS1", "AS2"], min_observations=2) == []
