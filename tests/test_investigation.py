import json

from netpath.cli_json import _apply_path_json_contract
from netpath.dns import summarize_public_resolver_rows
from netpath.investigation import from_payload, render_markdown, save_bundle


def test_from_payload_normalizes_flattened_explain_report():
    payload = {
        "verdict": "Near-target Packet Loss",
        "severity": "warning",
        "confidence": "high",
        "culprit_asn": "AS64502",
        "culprit_scope": "route-change",
        "evidence": ["Remote loss was 2.0% across 30 packets."],
        "evidence_details": [
            {
                "condition": "remote_packet_loss",
                "detail": "The loss was reproduced from inside the target network.",
            }
        ],
        "path": [
            {"hop": 1, "host": "198.51.100.1", "asn": "AS64502", "avg_ms": 10.0},
            {
                "hop": 2,
                "host": "203.0.113.10",
                "asn": "AS64500",
                "avg_ms": 70.0,
                "loss_pct": 2.0,
            },
        ],
        "baseline_changes": ["AS path changed at AS64502."],
        "recommendation": "Escalate with the remote packet-loss evidence.",
    }

    result = from_payload("explain", "zoom.example", payload)

    assert result.verdict == "Near-target Packet Loss"
    assert result.severity == "warning"
    assert result.confidence == "high"
    assert result.culprit == "AS64502 (route-change)"
    assert result.evidence == (
        "Remote loss was 2.0% across 30 packets.",
        "The loss was reproduced from inside the target network.",
    )
    assert result.baseline_changes == ("AS path changed at AS64502.",)
    assert result.path[1]["loss_pct"] == 2.0
    assert ("Maximum loss", "2%") in result.metrics


def test_from_payload_infers_dns_disagreement_and_resolver_evidence():
    payload = {
        "domain": "example.com",
        "record_type": "A",
        "summary": {
            "agree": 1,
            "responding": 2,
            "percentage": 50,
            "errors": 0,
            "groups": 2,
            "none": 0,
            "servfail": 0,
            "majority_values": ["203.0.113.10"],
            "majority_rows": [True, False],
        },
        "resolvers": [
            {
                "name": "Google Public DNS",
                "ip": "8.8.8.8",
                "location": "Anycast",
                "elapsed_ms": 24,
                "status": "ok",
                "values": ["203.0.113.10"],
            },
            {
                "name": "Cloudflare",
                "ip": "1.1.1.1",
                "location": "Anycast",
                "elapsed_ms": 31,
                "status": "ok",
                "values": ["198.51.100.20"],
            },
        ],
    }

    result = from_payload("dns", "example.com", payload)

    assert result.verdict == "Propagation differs"
    assert result.severity == "warning"
    assert result.culprit == "DNS propagation"
    assert ("Agreement", "50%") in result.metrics
    assert len(result.path) == 2
    assert any("Cloudflare returned 198.51.100.20" in item for item in result.evidence)
    assert "TTL" in result.recommendation


def test_from_payload_marks_consistent_dns_answers_healthy():
    payload = {
        "summary": {
            "agree": 3,
            "responding": 3,
            "percentage": 100,
            "errors": 0,
            "groups": 1,
            "majority_values": ["203.0.113.10"],
            "majority_rows": [True, True, True],
        },
        "resolvers": [
            {"name": name, "status": "ok", "values": ["203.0.113.10"]}
            for name in ("Google", "Cloudflare", "Quad9")
        ],
    }

    result = from_payload("dns", "example.com", payload)

    assert result.verdict == "DNS consistent"
    assert result.severity == "ok"
    assert result.confidence == "high"
    assert result.culprit == "none"
    assert "No conflicting answer was found across 3 usable responses" in result.evidence[-1]


def test_dns_empty_response_is_an_exception_not_a_conflicting_answer_group():
    rows = [
        {
            "name": "Google",
            "status": "ok",
            "values": ["216.198.79.1"],
            "elapsed_ms": 24,
        },
        {
            "name": "Cloudflare",
            "status": "ok",
            "values": ["216.198.79.1"],
            "elapsed_ms": 30,
        },
        {
            "name": "Bezeq Intl",
            "status": "none",
            "values": [],
            "elapsed_ms": 1842,
        },
    ]
    summary = summarize_public_resolver_rows(rows)

    assert summary["responding"] == 3
    assert summary["usable"] == 2
    assert summary["agree"] == 2
    assert summary["groups"] == 1
    assert summary["none"] == 1

    result = from_payload(
        "dns",
        "dave.io",
        {"record_type": "A", "summary": summary, "resolvers": rows},
    )

    assert result.verdict == "Mostly consistent"
    assert result.severity == "ok"
    assert result.confidence == "medium"
    assert "No conflicting record was confirmed" in result.detail
    assert "Bezeq Intl: no answer" in result.evidence[1]
    assert ("Exceptions", "1") in result.metrics
    assert "one TTL" not in result.recommendation


def test_from_payload_normalizes_country_asn_coverage_inventory():
    payload = {
        "country": "US",
        "country_name": "United States",
        "asn_count": 2,
        "probe_count": 3,
        "asns": [
            {
                "asn": "AS64500",
                "probe_count": 2,
                "network": "ExampleNet",
                "networks": ["ExampleNet"],
            },
            {
                "asn": "AS64501",
                "probe_count": 1,
                "network": "OtherNet",
                "networks": ["OtherNet"],
            },
        ],
    }

    result = from_payload("coverage", "US", payload)

    assert result.verdict == "ASN coverage"
    assert result.target == "US"
    assert result.detail == (
        "2 ASNs have 3 connected Globalping probes in United States."
    )
    assert result.path[0]["asn"] == "AS64500"
    assert result.metrics == (
        ("Country", "United States (US)"),
        ("Covered ASNs", "2"),
        ("Connected probes", "3"),
    )


def test_from_payload_normalizes_country_network_comparison():
    payload = {
        "country": "US",
        "requested_asns": 3,
        "measured_asns": 3,
        "warning_asns": 1,
        "operator_answer": {
            "verdict": "Near-target Packet Loss",
            "severity": "warning",
            "confidence": "high",
            "likely_culprit": "AS7018",
            "evidence": ["Affected networks: AS7018 Near-target Packet Loss"],
            "recommendation": "Investigate AS7018 directly.",
        },
        "results": [
            {
                "asn": "AS7018",
                "name": "AT&T",
                "verdict": {
                    "verdict": "Near-target Packet Loss",
                    "severity": "warning",
                },
            },
            {
                "asn": "AS7922",
                "name": "Comcast",
                "verdict": {"verdict": "Healthy", "severity": "ok"},
            },
        ],
    }

    result = from_payload("country", "US", payload)

    assert result.verdict == "Isolated network anomaly"
    assert result.evidence[0] == "Strongest finding: Near-target Packet Loss"
    assert result.culprit == "AS7018"
    assert result.detail == (
        "Compared 3 of 3 representative networks in US; "
        "1 produced a warning or critical finding."
    )
    assert result.path[0]["asn"] == "AS7018"
    assert result.metrics == (
        ("Requested networks", "3"),
        ("Measured networks", "3"),
        ("Warnings", "1"),
    )


def test_from_payload_normalizes_aspath_hop_points_and_metrics():
    payload = {
        "source_asn": "AS64500",
        "dest_asn": "AS64510",
        "target_ip": "203.0.113.10",
        "ping_rtt": {"avg": 42.5},
        "verdict": {
            "severity": "ok",
            "verdict": "Target Network Observed",
            "signals": [],
        },
        "confidence": "medium",
        "recommendation": "Diagnose the exact endpoint if the symptom persists.",
        "optimal_path": {
            "rtt_ms": 44.0,
            "reaches_target": True,
            "path": ["AS64500", "AS64510"],
            "hop_points": [
                {"hop": 1, "ip": "198.51.100.1", "label": "AS64500", "rtt_ms": 8.0},
                {"hop": 2, "ip": "203.0.113.10", "label": "AS64510", "rtt_ms": 44.0},
            ],
        },
        "candidates": [
            {"reaches_target": True, "rtt_ms": 44.0},
            {"reaches_target": False, "rtt_ms": 50.0},
        ],
    }

    result = from_payload("aspath", "AS64500 → AS64510", payload)

    assert result.verdict == "Target Network Observed"
    assert result.culprit == "none"
    assert result.path[1]["ip"] == "203.0.113.10"
    assert ("Aggregate RTT", "42.5 ms") in result.metrics
    assert ("Destination-ASN paths", "1") in result.metrics
    assert "Measured 2 candidate path(s)" in result.evidence[0]


def test_path_json_contract_does_not_claim_exact_endpoint_reachability():
    payload = {
        "optimal_path": {
            "reaches_target": True,
            "path": ["AS64500", "AS64510"],
        },
        "candidates": [{"reaches_target": True}],
    }

    result = _apply_path_json_contract(payload)

    assert result["verdict"]["verdict"] == "Target Network Observed"
    assert result["confidence"] == "medium"
    assert "does not prove" in result["verdict"]["detail"]
    assert result["evidence"][0]["evidence"]["exact_target_reachability"] == (
        "not_established"
    )


def test_from_payload_does_not_call_an_all_partial_path_reachable():
    payload = {
        "path_status": "incomplete",
        "optimal_path": None,
        "candidates": [
            {
                "reaches_target": False,
                "rtt_ms": 51.0,
                "path": ["AS64500"],
            }
        ],
    }

    result = from_payload("aspath", "AS64500 → AS64510", payload)

    assert result.severity == "warning"
    assert result.verdict == "Incomplete Path"
    assert result.culprit == "undetermined"
    assert "0 entered the destination ASN" in result.evidence[0]


def test_trailing_unanswered_hops_collapse_in_markdown_and_metrics():
    payload = {
        "severity": "ok",
        "path": [
            {"hop": 1, "host": "192.168.1.1", "asn": "AS???", "avg_ms": 24.9, "loss_pct": 0.0},
            {"hop": 2, "host": "???", "asn": "AS???", "avg_ms": 0.0, "loss_pct": 100.0},
            {"hop": 3, "host": "206.224.66.82", "asn": "AS14593", "avg_ms": 32.5, "loss_pct": 0.0},
        ]
        + [
            {"hop": hop, "host": "???", "asn": "AS???", "avg_ms": 0.0, "loss_pct": 100.0}
            for hop in range(4, 31)
        ],
    }

    result = from_payload("host", "dave.io", payload)

    assert ("Observed hops", "2") in result.metrics
    assert ("Unanswered probes", "28") in result.metrics
    assert ("Maximum loss", "100%") not in result.metrics

    markdown = render_markdown(result)
    assert "+ 27 hops with no reply" in markdown
    assert "* * *" in markdown  # the mid-path unanswered hop stays visible
    assert "???" not in markdown


def test_render_and_save_bundle_are_useful_valid_and_redacted(tmp_path):
    secret = "super-secret-token"
    cookie_secret = "session-very-secret"
    aws_secret = "AReallySensitiveAwsSecretAccessKey1234567890"
    signed_secret = "signed-url-value"
    provider_token = "github_pat_0123456789abcdefghijklmnop"
    payload = {
        "verdict": "Mid-path Packet Loss",
        "severity": "warning",
        "confidence": "medium",
        "likely_culprit": "AS64510",
        "detail": f"Probe succeeded with token={secret}",
        "evidence": [
            f"Authorization: Basic {secret}",
            f"Cookie: session={cookie_secret}",
            "TXT answer contained <script>alert(1)</script>",
        ],
        "recommendation": "Share the path evidence with the transit provider.",
        "path": [
            {
                "hop": 2,
                "host": "198.51.100.2",
                "asn": "AS64510",
                "avg_ms": 35.0,
                "loss_pct": 7.0,
            }
        ],
        "api_key": secret,
        "gp_token": secret,
        "nested": {"authorization": f"Bearer {secret}"},
        "aws_secret_access_key": aws_secret,
        "notes": f"secret_key={aws_secret} provider={provider_token}",
        "text_snippet": (
            '{"api_key":"plain-sensitive-value"} '
            'password="plain sensitive value"'
        ),
    }
    target = (
        "https://alice:p4ss@app.example/path"
        f"?X-Amz-Signature={signed_secret}&token={secret}"
    )
    result = from_payload("host", target, payload)

    markdown = render_markdown(result)
    assert "# netpath incident report" in markdown
    assert "Mid-path Packet Loss" in markdown
    assert "| Step | Endpoint |" in markdown
    assert "## Recommendation" in markdown
    assert secret not in markdown
    assert cookie_secret not in markdown
    assert aws_secret not in markdown
    assert signed_secret not in markdown
    assert provider_token not in markdown
    assert "plain-sensitive-value" not in markdown
    assert "plain sensitive value" not in markdown
    assert "alice" not in markdown
    assert "p4ss" not in markdown
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "[REDACTED]" in markdown

    markdown_path, json_path = save_bundle(result, tmp_path / "incident bundles")

    assert markdown_path.exists()
    assert json_path.exists()
    assert markdown_path.stem == json_path.stem
    assert ":" not in markdown_path.name
    assert secret not in markdown_path.name
    assert signed_secret not in markdown_path.name
    saved_markdown = markdown_path.read_text(encoding="utf-8")
    saved_json_text = json_path.read_text(encoding="utf-8")
    saved_json = json.loads(saved_json_text)
    assert saved_json["schema_version"] == 1
    assert saved_json["target"] == (
        "https://[REDACTED]:[REDACTED]@app.example/path"
        "?X-Amz-Signature=[REDACTED]&token=[REDACTED]"
    )
    assert saved_json["path"][0]["asn"] == "AS64510"
    assert saved_json["raw"]["api_key"] == "[REDACTED]"
    assert saved_json["raw"]["gp_token"] == "[REDACTED]"
    assert saved_json["raw"]["nested"]["authorization"] == "[REDACTED]"
    assert saved_json["raw"]["aws_secret_access_key"] == "[REDACTED]"
    assert secret not in saved_markdown
    assert secret not in saved_json_text
    assert cookie_secret not in saved_markdown
    assert cookie_secret not in saved_json_text
    assert aws_secret not in saved_json_text
    assert signed_secret not in saved_json_text
    assert provider_token not in saved_json_text
    assert "plain-sensitive-value" not in saved_json_text
    assert "plain sensitive value" not in saved_json_text
    assert "alice" not in saved_json_text
    assert "p4ss" not in saved_json_text
