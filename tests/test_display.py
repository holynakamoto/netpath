from io import StringIO

from rich.console import Console

from netpath import cli, display
from netpath.display import clean_asn_name


def test_clean_asn_name_exact_duplicate():
    """Exact duplicate around ' - ' is collapsed to a single occurrence."""
    assert clean_asn_name("Dimension Data - Dimension Data") == "Dimension Data"


def test_clean_asn_name_multi_word_exact_duplicate():
    """Multi-word exact duplicate is handled correctly."""
    assert clean_asn_name("Acme Corp - Acme Corp") == "Acme Corp"


def test_clean_asn_name_short_code_preserved():
    """Existing short-code stripping behavior is unaffected."""
    assert clean_asn_name("PARTNER-AS - Partner Comms") == "Partner Comms"


def test_operator_answer_renders_concise_warning(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(display, "console", Console(file=output, width=120, force_terminal=False))

    rendered = display.operator_answer({
        "severity": "warning",
        "verdict": "Mid-path Packet Loss",
        "likely_culprit": "AS64510",
        "culprit_scope": "transit-hop",
        "confidence": "medium",
        "evidence": [
            "Packet loss of 7.0% detected at 198.51.100.2.",
            "AS path: AS64500 → AS64510 → AS64520",
            "extra evidence",
            "hidden evidence",
        ],
        "recommendation": "Escalate to the transit provider owning the lossy hop.",
    })

    text = output.getvalue()
    assert rendered is True
    assert "Operator answer" in text
    assert "Likely culprit:" in text
    assert "AS64510 (transit-hop)" in text
    assert "Confidence:" in text
    assert "medium" in text
    assert "Key evidence:" in text
    assert "Next action:" in text
    assert "hidden evidence" not in text


def test_run_test_places_operator_answer_before_path_table(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(display, "console", Console(file=output, width=120, force_terminal=False))
    monkeypatch.setattr(cli.iperf_mod, "available", lambda: False)
    monkeypatch.setattr(cli, "_measure", lambda *args, **kwargs: {
        "hubs": [
            {"count": 1, "host": "192.0.2.1", "ASN": "AS64500", "Loss%": 0.0, "Avg": 3.0, "Best": 2.0, "Wrst": 4.0},
            {"count": 2, "host": "198.51.100.2", "ASN": "AS64510", "Loss%": 7.0, "Avg": 30.0, "Best": 25.0, "Wrst": 35.0},
            {"count": 3, "host": "203.0.113.20", "ASN": "AS64520", "Loss%": 7.0, "Avg": 55.0, "Best": 50.0, "Wrst": 60.0},
        ],
        "verdict": {
            "severity": "warning",
            "verdict": "Mid-path Packet Loss",
            "detail": "Packet loss of 7.0% detected at 198.51.100.2.",
            "signals": [
                {
                    "condition": "mid_path_packet_loss",
                    "severity": "warning",
                    "detail": "Packet loss of 7.0% detected at 198.51.100.2.",
                    "source": "local_trace",
                    "confidence": "medium",
                    "evidence": {
                        "loss_hop": {"hop_index": 2, "host": "198.51.100.2", "asn": "AS64510", "loss_pct": 7.0},
                        "downstream_clean": False,
                    },
                    "sample_size": 5,
                }
            ],
        },
        "probe_errors": {},
    })

    cli._run_test(
        host="203.0.113.20",
        port=5201,
        server_meta={"HOST": "203.0.113.20"},
        target_asn="AS64520",
        cycles=5,
        duration=1,
        skip_throughput=True,
        json_mode=False,
    )

    text = output.getvalue()
    assert text.index("Operator answer") < text.index("Host")
    assert "Likely culprit:" in text
    assert "AS64510 (transit-hop)" in text
    assert "Diagnosis" not in text


def test_trace_fusion_summary_makes_single_prober_limit_explicit(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(display, "console", Console(file=output, width=120, force_terminal=False))

    display.trace_fusion_summary({
        "methods": [
            {"name": "traceroute-udp", "status": "ok"},
            {"name": "traceroute-tcp", "status": "error"},
        ],
        "confidence": "low",
        "topology": {"mode": "linear", "branch_points": []},
        "filtered_ranges": [{"start": 7, "end": 30}],
    })

    text = output.getvalue()
    assert "Only UDP contributed hops" in text
    assert "normal single-prober trace" in text
    assert "Silent hop ranges:" in text
    assert "7–30" in text
    assert "Topology:" in text
    assert "Unavailable/failed:" in text
    assert "TCP" in text


def test_operator_answer_evidence_omits_raw_json(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(display, "console", Console(file=output, width=120, force_terminal=False))

    display.operator_answer({
        "severity": "warning",
        "verdict": "TLS Latency",
        "likely_culprit": "AS2635",
        "culprit_scope": "application-edge",
        "confidence": "high",
        "evidence": [
            "TLS handshake latency of 568 ms exceeds the 500 ms threshold. (tls, confidence high) [TLS 568 ms]",
        ],
        "recommendation": "Escalate to the destination application edge owner.",
    })

    text = output.getvalue()
    assert "[TLS 568 ms]" in text
    assert '"tls_handshake_ms"' not in text


def test_edge_metrics_labels_reachable_large_icmp_as_filtered(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(display, "console", Console(file=output, width=120, force_terminal=False))

    display.edge_metrics({
        "pmtu": {"blackhole": True, "effective_mtu_bytes": 92},
        "http_edge": {"status_code": 403},
    })

    text = output.getvalue()
    assert "Large ICMP filtered" in text
    assert "PMTU black-hole" not in text
