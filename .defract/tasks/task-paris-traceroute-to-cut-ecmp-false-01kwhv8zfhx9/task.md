---
defract:
  id: task-paris-traceroute-to-cut-ecmp-false-01kwhv8zfhx9
  type: bug
  status: active
  stage: scope
  phase: 0
  total_phases: 1
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---

# Paris traceroute to cut ECMP false positives

## Story Brief

## Story Brief

From chat: Paris traceroute to cut ECMP false positives (2026-07-02T16:31:35.278Z)

### Findings

- **jitter_ms is StDev of the last responsive hop — only 2 samples in the traceroute fallback** — cli.py:268-271 sets result["jitter_ms"] to the StDev of the last responsive hub (the destination). In the traceroute fallback path (macOS, "mtr unavailable"), that StDev is computed from just 2 RTT samples because _run_traceroute_cmd hardcodes -q 2 (mtr.py:204). On a transcontinental US→India path crossing ECMP-balanced backbone, two probes to the destination can traverse different physical paths, so the StDev captures path diversity, not real jitter. This is the primary driver of the "High Jitter" false positives (20.5–58.6 ms) in the country IN run.
  - Files: src/netpath/cli.py, src/netpath/mtr.py
- **"50% loss" at single hops is a -q 2 quantization artifact, mostly already suppressed** — The traceroute fallback runs -q 2 (mtr.py:204), so per-hop Loss% can only be 0/50/100 — a single unanswered probe reads as 50%. That is why isolated hops (e.g. #1 hop 10, #3 hop 10, #6 hop 16) show 50.0%. diagnosis.py:130-145 already forward-scans: if all downstream responsive hops are clean, it emits the "ok" rate_limited_hop signal instead of mid_path_packet_loss, so most of these correctly resolve to Healthy. The loss false positives are largely handled; the jitter verdict is the one still leaking through.
  - Files: src/netpath/mtr.py, src/netpath/diagnosis.py
- **Paris traceroute fixes the ECMP path-divergence class specifically, not the vantage-point or sample-size problems** — Paris traceroute pins the flow identifier (dest port / ICMP id-seq) constant across probes so every probe to a given TTL follows the same ECMP path. It directly eliminates phantom loss, phantom hops/loops, and RTT variance that is really per-flow load-balancer path diversity — which is a real contributor to the High Jitter and stalled-path signals here. What it does NOT fix: (1) the 2-sample sample-size noise from -q 2, and (2) the fact that measuring India ISPs from a US host inherently sees ~280-430 ms RTT with high variance across transoceanic segments. Paris is the right instrument for the load-balancer artifacts but only part of the picture.
- **Globalping mtr runs near the destination and is the authoritative loss/jitter source vs the local transcontinental trace** — Country mode already schedules Globalping ping + mtr measurements (visible in the IN run: AS9829 Globalping RTT 44.5 ms avg vs the local trace's 403.6 ms). Globalping probes sit near the target ASN, so their loss/jitter reflects the ISP's actual path quality, whereas the local US-origin trace mostly measures the transoceanic backbone. A strong alternative (or complement) to adding a Paris binary locally is to source the loss/jitter verdict inputs from Globalping mtr when available and demote the local traceroute to topology/AS-path only.

### Proposed actions

- **Options to cut the High Jitter false positives: raise -q, adopt a Paris tool, or trust Globalping** — Three levers, cheapest first. (1) Raise the fallback probe count above -q 2 and compute jitter from a real sample; nearly free, no new dependency, removes the 2-sample quantization. (2) Adopt a Paris-capable prober — scamper (CAIDA, -P udp-paris/icmp-paris), dublin-traceroute (Paris + Python bindings), or paris-traceroute — to eliminate ECMP path-divergence variance; note macOS system /usr/sbin/traceroute is not Paris-capable, so this adds a system prerequisite alongside mtr/iperf3. (3) Gate the High Jitter / loss verdicts on Globalping mtr data when a probe exists near the target, treating the local trace as topology only. (2) and (3) are complementary; (1) helps regardless.
  - Files: src/netpath/mtr.py, src/netpath/cli.py, src/netpath/diagnosis.py

### Bugs

- **High Jitter verdict misfires on healthy long-haul paths because jitter comes from 2-sample ECMP-contaminated StDev** — Every India ISP with a completed path in the country IN run got a "High Jitter — unstable latency" verdict (AS9829 20.5 ms, AS4755 58.6 ms, AS9498 19.1 ms, AS17488 23.8 ms) despite Cloudflare Radar showing sub-0.2% loss and normal RTTs for those ASNs. The verdict is derived from the destination hub StDev over just 2 probes across an ECMP-balanced transoceanic path (cli.py:268-271, mtr.py:204), so it reports path diversity + sampling noise as instability. The 10 ms JITTER_WARNING_MS threshold (diagnosis.py:1) was likely calibrated for local mtr runs, not long-haul 2-sample traceroute.
  - Files: src/netpath/cli.py, src/netpath/mtr.py, src/netpath/diagnosis.py

Originating chat: Paris traceroute to cut ECMP false positives (68eb9592-3446-4544-94e8-9750fb30fcbc)

## What We're Building

Netpath currently warns about "High Jitter" on network paths that are actually healthy. The false alarm happens because the fallback prober sends only two test packets, and on long-distance routes those two packets can travel different physical paths through load-balanced internet backbones — so normal route diversity gets reported as instability. This task makes the jitter verdict trustworthy: measure with enough samples, keep each measurement on a consistent route where the tooling allows it, and prefer measurements taken near the target network over the long-haul local view when judging that network's quality.

## Expected Outcome

- Healthy ISPs on the far side of the world no longer receive "High Jitter" warnings that independent data sources contradict
- Jitter is computed from a meaningful number of samples instead of two, eliminating the coin-flip artifacts in loss and jitter figures
- When a Paris-style prober that holds each probe on a consistent route is available on the machine, netpath uses it, so load-balancer route diversity stops masquerading as instability
- When a nearby vantage-point measurement of the target network exists, its loss and jitter figures drive the verdict, and the long-distance local trace is used for path topology only
- Country sweeps produce verdicts a network operator can act on without cross-checking external dashboards

## Out of Scope

- Throughput measurement (bandwidth testing) is unchanged — this task is about path-quality verdicts only
- Judging the quality of intermediate networks along the route — verdicts continue to describe the target network only
- Running netpath itself from multiple vantage points or making the probe origin configurable — nearby measurements come from the existing remote-probe integration