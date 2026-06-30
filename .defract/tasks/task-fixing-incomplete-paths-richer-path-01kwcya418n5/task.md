---
defract:
  id: task-fixing-incomplete-paths-richer-path-01kwcya418n5
  type: bug
  status: active
  stage: architecture
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

### Open Decisions

**1. How should PMTU black-hole probing be sent?**

The approach determines whether the feature works without administrator rights on all supported platforms. Raw socket calls are more precise but require root/elevated privileges on Linux, which most users will not have.

- System ping command (recommended)
- Raw Python socket

**2. Should multi-pass path tracing (for ECMP and route flapping detection) be user-controlled or always on?**

Multi-pass tracing multiplies total run time by the number of passes. Making it always-on means every `asn` probe takes 3x longer by default, which changes the feel of routine checks.

- User opt-in via a flag (recommended)
- Always run three passes

**3. How should the system know how many packets were sent when calibrating loss alarms?**

The loss calibration logic adjusts alarm thresholds based on total probe count. mtr does not expose raw send counts in its output — there is a design choice about where this number comes from.

- Thread mtr cycle count through the measurement pipeline (recommended)
- Assume a fixed default of 10 probes

**4. Should TCP and TLS latency measurement live in its own module or inline in the main command file?**

The spec explicitly leaves this open. A separate module follows the project's pattern of single-purpose files (as with the new PMTU and IXP modules in Phase 3), but the measurement itself is roughly 30 lines and could reasonably live inline.

- New dedicated latency module (recommended)
- Inline helpers in the main command file

