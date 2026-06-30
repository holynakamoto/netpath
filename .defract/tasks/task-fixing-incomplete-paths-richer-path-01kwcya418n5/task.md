---
defract:
  id: task-fixing-incomplete-paths-richer-path-01kwcya418n5
  type: bug
  status: active
  stage: implementation
  phase: 0
  total_phases: 3
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

## Story Brief

# Fixing incomplete paths + richer path metrics

# Fixing incomplete paths + richer path metrics

# Fixing incomplete paths + richer path metrics

## What We're Building

Transform netpath from a focused path/throughput prober into a comprehensive network diagnostics tool that covers every signal a network engineer needs in a single run. The work breaks into three areas: (1) fix two accuracy bugs — a false-positive packet loss warning on ICMP rate-limited transit hops, and an uninformative "incomplete" label that discards useful trace data; (2) improve path completion so more traces reach their destination by selecting smarter target IPs and preferring TCP-based probing; and (3) add the full set of CCIE-grade path metrics that are currently missing — ECMP-aware tracing, per-path jitter, PMTU black-hole detection, TCP and TLS application latency, IPv6 dual-stack comparison, statistically calibrated loss confidence, route stability detection across probe cycles, and IXP-vs-transit hop classification.

## Expected Outcome

- Paths crossing ICMP rate-limited transit hops no longer produce false packet loss warnings or non-zero exit codes
- Incomplete path reports show the stall location (transit ASN and hop number) and last measured RTT instead of a flat "incomplete" label
- More `country` mode paths complete end-to-end due to smarter destination IP selection and TCP-443 as the primary probe
- ECMP-heavy core paths are traced accurately without phantom loss at transit hops
- Per-path jitter and IPDV appear alongside latency and loss in the verdict
- PMTU black-hole conditions — where ping succeeds but throughput stalls — are detected and reported
- TCP connect and TLS handshake latency give application-felt latency alongside ICMP RTT
- IPv4 and IPv6 paths can be compared side-by-side for the same target
- Loss verdicts are calibrated to sample size so a single drop in ten probes does not trigger the same alarm as ten drops in a hundred
- Route instability and flapping across probe cycles is detected and flagged
- Each AS hop is labeled as IXP, transit, or destination to speed up triage

## Phase Outcomes

- **Phase 1: Fix the two accuracy bugs** — Engineers running country sweeps stop getting false alarms from transit hops that rate-limit ICMP, and incomplete paths now show enough context (stall ASN, hop number, last RTT) to understand where the trace broke down.
- **Phase 2: Smarter probing and calibrated metrics** — Country mode reaches more destinations by preferring TCP-443 traceroute and better test IP selection; jitter and loss confidence calibration appear in verdicts so alarms are proportional to the evidence.
- **Phase 3: Advanced path analysis** — PMTU black-hole conditions, TCP/TLS application latency, ECMP path divergence, route flapping, IXP hop classification, and IPv6 dual-stack comparison are all available in a single run for deep-dive diagnostics.

## Out of Scope

- GUI, web dashboard, or browser-based visualization (CLI only; the existing `--globe` flag is unchanged)
- Packet capture or deep packet inspection
- Active security scanning or attack simulation
- Push integration with third-party observability platforms (Datadog, New Relic, Splunk, etc.)
- Automated remediation or configuration changes based on diagnosis results

## Scope Summary

**Size:** 16 requirements, 14 acceptance criteria, 3 implementation phases
**Key decisions:**
- Architecture stage will define per-file breakdown for all three phases
- IXP classification via PeeringDB prefix fetch with in-process caching; graceful degradation when unavailable
- Loss confidence calibration uses total probe samples (cycles × mtr probe count) as the denominator
**Biggest risk:** Phase 3 introduces two new modules and relies on PeeringDB's public API — rate-limit or schema changes could block IXP classification; dual-stack adds execution paths hard to test without a live IPv6 network.

## Context

netpath currently runs mtr or traceroute against iperf3 servers or RIPE-allocated IPs, enriches with Cymru ASN data, and classifies results through `diagnosis.py`. The two bugs being fixed in Phase 1 live in `diagnosis.py:33–54` (ICMP rate-limit false positive, where `Loss% > 1.0` at a transit hop triggers a verdict without checking whether downstream hops are clean) and `display.py:400–409` (flat "incomplete" label with no stall context). Path completion is limited because `country.get_test_ip_for_asn()` picks the second host from whichever prefix happens to be first in the RIPE response, and UDP-ICMP probing is blocked by many transit networks. Phase 3's nine new metrics require new logic across `mtr.py`, `diagnosis.py`, `display.py`, `cli.py`, and two new modules (`src/netpath/pmtu.py`, `src/netpath/ixp.py`).

## Requirements

### Bug Fixes

- R1: When an intermediate hop reports `Loss% > 1.0` but all subsequent responsive hops report `Loss% ≤ 1.0`, the diagnosis must suppress the "Mid-path Packet Loss" verdict and emit a `rate_limited_hops` informational signal in a "Healthy" verdict instead. (Logic in `diagnosis.py:33–54`.)
- R2: `_classify_path()` in `cli.py:50–95` must additionally return the stall hop number (`count` field of the last responsive hub before the path stops). `display.country_summary()` in `display.py:326–415` must render incomplete path rows with stall ASN, stall hop number, and last measured RTT — e.g., "⚠ stalled at AS1299, hop 8, 45.2 ms" — instead of the current flat "⚠ incomplete".

### Smarter Probing

- R3: `country.get_test_ip_for_asn()` in `country.py:109–134` must prefer the most-specific announced prefix (highest `prefixlen`) when selecting a test IP rather than the first prefix returned.
- R4: When no iperf3 server exists for a country-mode ASN, the traceroute path in `cli.py:526–547` must prefer TCP-443 probing (via the existing `mtr._run_traceroute_cmd(tcp=True)`), falling back to UDP if TCP returns all-stars or raises.

### Jitter

- R5: `_measure()` in `cli.py:157–244` must compute a path-weighted jitter value from per-hop `StDev` fields in the mtr hub list and include it as `jitter_ms` (float or None) in the returned result dict.
- R6: `diagnosis.py` must accept `jitter_ms` from the result dict and emit a "High Jitter" warning signal when `jitter_ms` exceeds a named threshold constant (`JITTER_WARNING_MS = 10.0`).
- R7: `jitter_ms` must appear in `--json` output (`cli.py:383–412`) and in the signals list of the terminal verdict panel when elevated.

### Loss Confidence Calibration

- R8: `diagnosis.py` must accept a `probe_count` integer (total probe samples) from the result dict and adjust the mid-path loss alarm threshold: `< 20` probes → threshold `> 5.0%`; `20–99` probes → default `> 1.0%`; `≥ 100` probes → threshold `> 0.5%`. All thresholds must be named constants.

### PMTU Black-hole Detection

- R9: A new `src/netpath/pmtu.py` module must export `probe(host: str) -> dict` that sends ICMP echo at 1472-byte and 64-byte payload sizes, compares success rates, and returns `{"blackhole": bool, "mtu_floor_bytes": int | None}`. The function must return `{"blackhole": False, "mtu_floor_bytes": None}` gracefully when ICMP is unavailable or the host blocks all probes.
- R10: `_measure()` must call `pmtu.probe()` and include the result as `pmtu` in the returned dict. `diagnosis.py` must emit a "PMTU Black-hole" critical signal when `pmtu.get("blackhole")` is True.

### TCP and TLS Application Latency

- R11: A helper (in `cli.py` or a new `src/netpath/latency.py`) must measure TCP connect latency (SYN→SYN-ACK) and TLS handshake duration using Python's standard `socket` and `ssl` modules only — no new runtime dependencies. Both measurements must time out within 5 seconds and handle `ConnectionRefusedError`, `ssl.SSLError`, and `OSError` gracefully, returning `None` on failure.
- R12: `tcp_connect_ms` and `tls_handshake_ms` must appear in the `_measure()` result dict, in `--json` output, and as verdict signals when they exceed 200 ms and 500 ms respectively.

### ECMP and Route Stability

- R13: `mtr.run()` must accept an optional `passes: int = 1` parameter. When `passes > 1`, it runs mtr that many times sequentially and returns `list[list[dict]]`. A helper must compare AS paths across passes (by `hub[i]["ASN"]` at matching `count` positions) and report `ecmp_paths` (distinct path count) in the result dict.
- R14: When `passes > 1`, the number of AS-path changes across consecutive probe cycles must be reported as `path_changes` in the result dict. `diagnosis.py` must emit a "Route Flapping" warning when `path_changes > 0`.

### IXP Hop Classification

- R15: A new `src/netpath/ixp.py` module must export `classify_hop(ip: str) -> str` returning `"ixp" | "transit" | "destination"`. It must fetch the PeeringDB IXP prefix list on first call and cache it in process memory. When the fetch fails, it must return `"transit"` silently. `path_table()` in `display.py` must render a classification prefix or icon for each responsive hop.

### IPv6 Dual-stack Comparison

- R16: The `asn` subcommand must accept `--compare-v6`. When set, `_measure()` runs two parallel traces — IPv4 and IPv6 — and returns both hub lists as `hubs_v4` and `hubs_v6`. The terminal must display them side-by-side using Rich `Columns`, following the existing two-column pattern in `display.py:236–281`. If IPv6 resolution fails, warn and display IPv4 only.

## Acceptance Criteria

- [ ] A trace where hop 6 shows 50% loss but hops 7–10 show 0% loss produces verdict "Healthy" with a `rate_limited_hops` signal, not "Mid-path Packet Loss". Verified by unit test in `tests/test_diagnosis.py`.
- [ ] In country mode, an incomplete path row shows stall ASN, stall hop number, and last RTT instead of just "⚠ incomplete". Verified visually against a known-incomplete ASN via `netpath country US`.
- [ ] `country.get_test_ip_for_asn()` selects a host from the most-specific (highest `prefixlen`) announced prefix. Verified by unit test in `tests/test_country.py`.
- [ ] Country mode uses TCP-443 traceroute for ASNs without an iperf3 server. Verified by unit test confirming `_run_traceroute_cmd(tcp=True)` is called before `tcp=False`.
- [ ] `netpath asn AS15169 --json` output includes a `jitter_ms` numeric field (or null when unavailable).
- [ ] A simulated trace with per-hop StDev of 15 ms triggers a "High Jitter" warning signal. Verified by unit test in `tests/test_diagnosis.py`.
- [ ] Diagnosis with 10 probes and 3% loss produces no "Mid-path Packet Loss" verdict (`probe_count < 20` raises threshold to `> 5%`). Verified by unit test.
- [ ] `pmtu.probe()` returns `{"blackhole": False, "mtu_floor_bytes": None}` without raising when called against a host that blocks all ICMP. Verified by unit test with mocked subprocess.
- [ ] `tcp_connect_ms` and `tls_handshake_ms` appear in `--json` output. Verified by integration test against a reachable host.
- [ ] `mtr.run(passes=3)` with two distinct mocked AS paths returns `ecmp_paths > 1`. Verified by unit test.
- [ ] `path_changes > 0` for two different consecutive AS paths triggers a "Route Flapping" warning. Verified by unit test in `tests/test_diagnosis.py`.
- [ ] Each responsive hop in `path_table()` shows a classification label ("IXP", "transit", or "destination"). Verified visually.
- [ ] `netpath asn AS15169 --compare-v6` shows two path tables in a side-by-side panel. Verified visually.
- [ ] `ruff check .` passes with no new violations after all changes.

## Implementation Phases

### Phase 1: Fix the two accuracy bugs
**Scope:** Fix the ICMP rate-limit false positive in `diagnosis.py` and enrich the incomplete path display in `display.country_summary()` so engineers see stall ASN, hop number, and last RTT. These are contained changes to existing functions with no new modules.
**Files:** `src/netpath/diagnosis.py`, `src/netpath/cli.py` (`_classify_path`), `src/netpath/display.py` (`country_summary`), `tests/test_diagnosis.py`
**Verification:**
- Unit test: 50% loss at hop 6, 0% at hops 7–10 → "Healthy" verdict with `rate_limited_hops` signal
- Visual: `netpath country US` incomplete row shows stall ASN + hop + RTT instead of flat "incomplete"
- `ruff check .` clean
**Estimated effort:** Small

### Phase 2: Smarter probing and calibrated metrics
**Scope:** Switch country mode traceroute-only paths to prefer TCP-443, improve test IP selection to the most-specific announced prefix, and add jitter and loss confidence calibration to the diagnosis pipeline. Jitter and calibrated thresholds appear in the verdict panel and JSON output.
**Files:** `src/netpath/country.py`, `src/netpath/cli.py`, `src/netpath/diagnosis.py`, `src/netpath/display.py`, `tests/test_diagnosis.py`, `tests/test_country.py`
**Verification:**
- Unit test: `get_test_ip_for_asn()` returns host from highest-prefixlen prefix
- Unit test: `_run_traceroute_cmd(tcp=True)` called first in country mode fallback
- Unit test: 3% loss at 10 probes → no Mid-path Loss verdict
- `netpath asn AS15169 --json` includes `jitter_ms`
- `ruff check .` clean
**Estimated effort:** Medium

### Phase 3: Advanced path analysis
**Scope:** Add PMTU black-hole detection (`pmtu.py`), TCP/TLS application latency, ECMP multi-pass tracing, route stability detection, IXP hop classification (`ixp.py`), and IPv6 dual-stack comparison (`--compare-v6`). This phase introduces two new modules and one new CLI flag.
**Files:** `src/netpath/pmtu.py` (new), `src/netpath/ixp.py` (new), `src/netpath/mtr.py`, `src/netpath/cli.py`, `src/netpath/diagnosis.py`, `src/netpath/display.py`, `tests/test_diagnosis.py`
**Verification:**
- Unit test: `pmtu.probe()` returns non-raising result against ICMP-blocked host
- Unit test: `mtr.run(passes=3)` with two distinct mocked AS paths → `ecmp_paths > 1`
- Unit test: `path_changes > 0` fires "Route Flapping" warning
- Visual: `path_table()` shows IXP/transit/destination labels per hop
- Visual: `netpath asn AS15169 --compare-v6` shows side-by-side IPv4/IPv6 panels
- `ruff check .` clean
**Estimated effort:** Large

## Edge Cases

- ICMP rate-limit detection: loss at hop N with 0% at all downstream responsive hops → rate-limited, not congested; `rate_limited_hops` signal only.
- IXP prefix fetch fails (PeeringDB rate-limited or down): `classify_hop()` returns `"transit"` silently with no user-visible error.
- IPv6 not routable from client (`--compare-v6`): warn in yellow and display IPv4 table only.
- mtr StDev is 0 (single probe or perfectly stable path): `jitter_ms = 0.0`; no "High Jitter" signal raised.
- PMTU probe destination blocks all ICMP: return `{"blackhole": False, "mtu_floor_bytes": None}` — cannot confirm black-hole without both probe sizes succeeding.
- `passes=1`: `path_changes = 0` and `ecmp_paths = 1`; no flapping signal.
- `get_test_ip_for_asn()` finds no prefix with `prefixlen > 8`: fall back to current behavior (second host from first prefix).
- Incomplete path stall is ambiguous (all hops after first responsive hub are `???`): stall hop number is `count` of the last responsive hub.

## Technical Notes

The ICMP rate-limit fix (R1) adds a forward-scan to `diagnosis.py:33–54`: after finding a hop with `Loss% > 1.0`, check whether all subsequent responsive hops have `Loss% ≤ 1.0`. If yes, reclassify to "Healthy" + `rate_limited_hops` signal.

TCP/TLS latency (R11–12) uses standard library only: `socket.create_connection()` for TCP roundtrip timing, wrapped with `ssl.SSLContext().wrap_socket()` for TLS handshake. Both calls need `timeout=5` and must land in the same exception net as existing graceful fallbacks.

IXP classification (R15) should cache the PeeringDB prefix response in a module-level dict for the process lifetime — not disk — to avoid repeated fetches during `country` mode sweeps.

mtr multi-pass (R13) calls `mtr.run()` N times sequentially (not concurrently, to avoid path flooding). Each pass returns a hub list; the caller receives `list[list[dict]]` and compares hub-by-hub by matching `count` positions.

The `--compare-v6` flag (R16) resolves IPv6 via `socket.getaddrinfo(host, None, socket.AF_INET6)`. If resolution raises `socket.gaierror`, warn and skip the IPv6 path cleanly.

### Dependencies

Phase 3 introduces `src/netpath/pmtu.py` and `src/netpath/ixp.py`. PeeringDB's public IX prefix list is available without authentication. No new PyPI runtime dependencies are introduced in any phase.

## Architecture

### Architecture Summary

Three phases of work tighten netpath's accuracy and add diagnostic depth. Phase 1 stops false alarms from transit hops that rate-limit ICMP probes, and makes incomplete-path rows in country sweeps show where the trace actually stalled — the transit ASN, hop number, and last measured RTT — instead of a flat warning. Phase 2 makes country sweeps reach more destinations by probing over TCP-443 first (where transit networks often pass traffic that blocks UDP probes), choosing test IPs from the most-specific announced prefix, and calibrating loss alarms to the actual number of packets measured rather than a fixed 1% threshold for every run. Phase 3 adds six advanced diagnostics built as standalone modules: PMTU black-hole detection (finding paths where large packets are silently dropped), TCP and TLS application latency alongside ICMP RTT, ECMP path tracing (running multiple passes to detect load-balanced diverging paths), route flapping detection across probe cycles, IXP hop classification to speed up triage, and IPv6 dual-stack comparison via a new --compare-v6 flag. Two new runtime dependencies are avoided entirely — all new code uses only the Python standard library and the system ping binary already used for bufferbloat.

### Implementation Phases

### Phase 1: Fix the two accuracy bugs

**Verification:**
- [ ] Unit test: hubs with 50% loss at hop 6 and 0% at hops 7-10 produce verdict='Healthy' with a rate_limited_hops signal (tests/test_diagnosis.py)
- [ ] Visual: netpath country US shows an incomplete-path row with stall ASN, hop number, and RTT instead of bare '⚠ incomplete'
- [ ] ruff check . passes with no new violations

**Estimated effort:** Small

### Phase 2: Smarter probing and calibrated metrics

**Verification:**
- [ ] Unit test: get_test_ip_for_asn() with mocked prefixes [/24, /20, /16] returns a host from the /24 (tests/test_country.py)
- [ ] Unit test: mocked traceroute path calls mtr._run_traceroute_cmd(tcp=True) before tcp=False when prefer_tcp=True (tests/test_country.py)
- [ ] Unit test: diagnose({'jitter_ms': 15.0, 'hubs': [...]}) returns a warning with 'High Jitter' signal (tests/test_diagnosis.py)
- [ ] Unit test: diagnose({'probe_count': 10, 'hubs': [{...3% loss...}]}) returns Healthy — 3% does not exceed the 5% threshold for fewer than 20 probes (tests/test_diagnosis.py)
- [ ] netpath asn AS15169 --json output includes a jitter_ms field (numeric or null)
- [ ] ruff check . passes with no new violations

**Estimated effort:** Medium

### Phase 3: Advanced path analysis

**Verification:**
- [ ] Unit test: pmtu.probe() with mocked subprocess returning exit-code 2 for large ping and 0 for small returns {blackhole: True}; with all probes failing returns {blackhole: False, mtu_floor_bytes: None} without raising
- [ ] Unit test: mtr._compare_as_paths([[hubset_A], [hubset_B]]) where hubset_B differs at hop 3 returns ecmp_paths=2 (tests/test_mtr.py)
- [ ] Unit test: diagnose({'path_changes': 1}) triggers Route Flapping warning (tests/test_diagnosis.py)
- [ ] Unit test: diagnose({'tcp_connect_ms': 250}) triggers TCP Latency warning; diagnose({'tls_handshake_ms': 600}) triggers TLS Latency warning (tests/test_diagnosis.py)
- [ ] Visual: netpath asn AS15169 path table shows a Type column with IXP/transit/dest label per responsive hop
- [ ] Visual: netpath asn AS15169 --compare-v6 renders two path tables side-by-side (or IPv4-only with a yellow warning when IPv6 resolution fails)
- [ ] ruff check . passes with no new violations

**Estimated effort:** Large

## Implementation Notes

## Phase 1: Fix the two accuracy bugs

**Status:** Complete

**Files changed:**
- `src/netpath/diagnosis.py` — Added forward-scan in the mid-path loss block: after finding a hop with Loss% > 1.0, checks all subsequent responsive hubs; if all have Loss% ≤ 1.0, returns Healthy verdict with `rate_limited_hops` signal instead of Mid-path Packet Loss.
- `src/netpath/cli.py` — `_classify_path()` now returns `stall_hop` (count of last responsive hub in incomplete paths) and `rtt_ms` from the incomplete scan. `_measure()` stores `stall_hop` in result dict and uses classification's `rtt_ms` for incomplete paths. Skipped-ASN summary row gains `stall_hop: None`.
- `src/netpath/display.py` — `country_summary()` incomplete section now renders "⚠ stalled at {entry_transit_asn}, hop {n}, {rtt} ms" using the new fields instead of flat "⚠ incomplete". Pre-existing unused `Rule` import removed.
- `src/netpath/speedtest.py` — Pre-existing unused `shutil` import removed (ruff clean-up).
- `tests/test_diagnosis.py` — Added `test_rate_limited_hop_produces_healthy_not_mid_path_loss`: 10-hop trace with 50% loss at hop 6 and 0% at hops 7–10 asserts Healthy verdict with `rate_limited_hops` signal. Updated `test_mid_path_packet_loss` to use a downstream-lossy hub (8% at hop 3) so it tests genuine congestion rather than the now-suppressed rate-limit pattern.

**Test results:** 15/15 passed, ruff clean.

## Phase 2: Smarter probing and calibrated metrics

**Status:** Complete

**Files changed:**
- `src/netpath/country.py` — `get_test_ip_for_asn()` now pre-sorts valid IPv4 prefixes by `prefixlen` descending before iterating, so the most-specific announced prefix is selected first.
- `src/netpath/mtr.py` — `run_traceroute()` gains `prefer_tcp: bool = False` parameter. When `True`, tries TCP-443 first; falls back to UDP if TCP returns all-stars or raises. Default (False) preserves existing UDP-first behaviour.
- `src/netpath/cli.py` — `_trace()`, `_measure()`, and `_run_test()` each gain `prefer_tcp: bool = False`; the country-mode no-server path passes `prefer_tcp=True`. `_measure()` initialises `jitter_ms: None` and `probe_count: cycles` in the result dict, then computes `jitter_ms` as the mean `StDev` across responsive hubs. JSON output adds a `jitter_ms` field. Forward-scan comparison in `diagnosis.py` updated to use the calibrated `loss_threshold` so the rate-limit suppression stays consistent with the trigger threshold.
- `src/netpath/diagnosis.py` — Added `JITTER_WARNING_MS = 10.0`, `LOSS_THRESHOLD_FEW = 5.0`, `LOSS_THRESHOLD_DEFAULT = 1.0`, `LOSS_THRESHOLD_MANY = 0.5` constants. `diagnose()` now selects a calibrated loss threshold from `probe_count` and applies it to both the trigger and the forward-scan. Added High Jitter warning (check 5) when `jitter_ms > JITTER_WARNING_MS`.
- `tests/test_diagnosis.py` — Added `test_high_jitter_warning`, `test_jitter_below_threshold_is_healthy`, `test_calibrated_loss_few_probes_no_alarm`, `test_calibrated_loss_many_probes_strict_threshold`.
- `tests/test_country.py` (new) — `test_get_test_ip_prefers_most_specific_prefix`, `test_run_traceroute_prefer_tcp_calls_tcp_first`, `test_run_traceroute_prefer_tcp_falls_back_to_udp_on_allstars`.

**Test results:** 22/22 passed, ruff clean.

## Phase 3: Advanced path analysis

**Status:** Complete

**Files created:**
- `src/netpath/pmtu.py` — `probe(host)` runs system ping at 1472-byte and 64-byte ICMP payload sizes. If large fails and small succeeds, returns `{"blackhole": True, "mtu_floor_bytes": 64}`. Returns `{"blackhole": False, "mtu_floor_bytes": None}` gracefully on any subprocess or OS error.
- `src/netpath/latency.py` — `measure_tcp_connect(host, port=443, timeout=5.0)` times SYN→SYN-ACK via `socket.create_connection()`; `measure_tls_handshake(host, port=443, timeout=5.0)` wraps with `ssl.create_default_context().wrap_socket()`. Both return float ms or None; both catch `ConnectionRefusedError`, `ssl.SSLError`, `OSError`.
- `src/netpath/ixp.py` — `classify_hop(ip)` returns `"ixp"` or `"transit"`. `_load_ixp_prefixes()` fetches PeeringDB IXP prefix list on first call and caches in module-level list; returns silently on fetch failure.

**Files modified:**
- `src/netpath/mtr.py` — `run()` gains `passes: int = 1`; when `passes > 1`, runs mtr sequentially and returns `list[list[dict]]`. New `_compare_as_paths(all_passes)` computes `ecmp_paths` (distinct AS sequences) and `path_changes` (consecutive-pass sequence differences).
- `src/netpath/diagnosis.py` — Added `TCP_LATENCY_WARNING_MS = 200.0`, `TLS_LATENCY_WARNING_MS = 500.0` constants. Checks (6)–(9): PMTU Black-hole critical, Route Flapping warning, TCP Latency warning, TLS Latency warning.
- `src/netpath/display.py` — Refactored `path_table()` into `_build_hub_table()` (returns a Table) + `path_table()` (prints it). `_build_hub_table()` adds a "Type" column per hop: "dest" (green) for target-ASN hops, "IXP" (blue) or "transit" (dim) via `ixp.classify_hop()`. New `dual_stack_columns(hubs_v4, hubs_v6, target_asn)` wraps two `_build_hub_table()` results in Panels and displays side-by-side via Rich Columns.
- `src/netpath/cli.py` — Added `import socket` and `from netpath import latency as latency_mod, pmtu as pmtu_mod`. `_measure()` gains `ecmp_passes: int = 1` and `compare_v6: bool = False`. Multi-pass ECMP branch calls `mtr.run(passes=N)` and `mtr._compare_as_paths()`; stores `ecmp_paths` and `path_changes`. Dual-stack branch resolves IPv6 via `socket.getaddrinfo(AF_INET6)`, runs v4/v6 traces in parallel threads, stores `hubs_v4` and `hubs_v6`. `_measure()` always calls `pmtu_mod.probe()` and `latency_mod.measure_tcp_connect/measure_tls_handshake()`. `asn` subcommand gains `--ecmp-passes` and `--compare-v6` flags. JSON output adds `tcp_connect_ms`, `tls_handshake_ms`, `pmtu`, `ecmp_paths`, `path_changes`.
- `tests/test_diagnosis.py` — Added 8 new Phase 3 tests: `test_pmtu_blackhole_triggers_critical`, `test_pmtu_no_blackhole_is_healthy`, `test_route_flapping_warning`, `test_route_flapping_zero_changes_is_healthy`, `test_tcp_latency_warning`, `test_tcp_latency_below_threshold_is_healthy`, `test_tls_latency_warning`, `test_tls_latency_below_threshold_is_healthy`.
- `tests/test_mtr.py` — Added 6 new Phase 3 tests: `test_compare_as_paths_ecmp_two_distinct_paths`, `test_compare_as_paths_identical_passes`, `test_compare_as_paths_empty`, `test_pmtu_blackhole_large_fails_small_succeeds`, `test_pmtu_all_probes_fail_no_blackhole`, `test_pmtu_subprocess_raises_no_exception`.

**Test results:** 36/36 passed, ruff clean.

