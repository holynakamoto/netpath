---
defract:
  version: 1
  generated_at: "2026-07-01T00:00:00Z"
  updated_at: "2026-07-02T00:00:00Z"
  source: extracted
---

# Project Profile

## Overview

`netpath` is a Python CLI tool that probes network paths to Autonomous Systems (ASNs), measuring throughput, latency, packet loss, PMTU, and path properties across AS boundaries. It supports per-ASN probing, country-wide sweeps of top ISPs, optional Cloudflare Radar RUM overlay, and an interactive 3D globe visualization.

## Stack

- **Runtime**: Python 3.9–3.13
- **CLI framework**: Typer ≥ 0.9
- **Terminal display**: Rich ≥ 13.0
- **HTTP client**: requests ≥ 2.28
- **Build backend**: hatchling + hatch-vcs (version derived from git tags)
- **Package manager**: uv (uv.lock present; pip also supported)
- **Testing**: pytest ≥ 8
- **Linting**: ruff ≥ 0.4
- **CI/CD**: GitHub Actions — matrix test on Python 3.9–3.13; publish to PyPI on `v*.*.*` tags via OIDC trusted publishing

## Conventions

- `raise typer.Exit(code)` for exit codes, never `sys.exit()` — Typer's cleanup requires it; exit code = worst verdict severity across all probes (0=ok, 1=warning, 2=critical)
- Single-purpose measurement modules: `iperf.py`, `speedtest.py`, `rum.py`, `pmtu.py`, `latency.py`, `ixp.py` each own one concern; no measurement logic in `cli.py`
- `_measure()` is display-free; `_run_test()` wraps it with display and `json_mode` branching — keeps `--json` and future country-mode JSON straightforward to add
- `probe_errors: dict[str, str]` accumulates all probe failures in `_measure()`; the old `_trace_error` / `_iperf_error` top-level keys are gone
- `concurrent.futures.ThreadPoolExecutor(max_workers=8)` for all concurrency inside `_measure()` — asyncio rejected because all I/O is blocking subprocess/socket calls
- `TypedDict(total=False)` for `Hub` and `MeasurementResult` in `types.py` — preserves `.get()` dict-access patterns and JSON serialisability while adding static type coverage
- `diagnose()` runs all nine signal checks unconditionally; worst severity sets the top-level verdict; rate-limited hop signals use severity `"ok"` to appear without elevating the verdict
- In-process module-level cache for external API reference data (PeeringDB IXP prefixes in `ixp.py`) — CLI exits after each run so disk caching is unnecessary
- `_with_retry()` helper in `utils.py` for HTTP reliability (3 attempts, exponential backoff) — tenacity rejected as a runtime dependency
- Test targets: pure functions and subprocess-mockable modules only (`diagnosis.diagnose`, `mtr._parse_traceroute_output`, `mtr._compare_as_paths`, `country.get_test_ip_for_asn`, `pmtu.probe`)

## File Structure

```
src/netpath/
├── cli.py          — Typer app; `asn` and `country` subcommands; _measure() / _run_test()
├── types.py        — Hub and MeasurementResult TypedDicts
├── asn.py          — ASN normalisation + Team Cymru bulk lookup
├── mtr.py          — mtr runner (with traceroute fallback); ECMP multi-pass; AS path parsing
├── servers.py      — iperf3 public server list fetch, DNS resolve, ASN filter
├── country.py      — RIPE allocation data → top N ASNs for a country
├── diagnosis.py    — verdict engine; nine signal checks; accumulates probe_errors
├── display.py      — Rich terminal tables, panels, and dual-stack columns
├── iperf.py        — bidirectional iperf3 throughput measurement
├── speedtest.py    — Cloudflare HTTP speedtest fallback
├── rum.py          — Cloudflare Radar RUM fetch (radar:read token)
├── globe.py        — interactive 3D globe visualisation via plotly
├── pmtu.py         — ICMP PMTU black-hole detection
├── latency.py      — TCP connect + TLS handshake latency
├── ixp.py          — hop classification (IXP vs transit; PeeringDB prefix cache)
└── utils.py        — _with_retry HTTP helper

tests/
├── test_diagnosis.py
├── test_mtr.py
├── test_country.py
└── test_utils.py

listed_iperf3_servers.json  — bundled public iperf3 server list (tracked in git)
```

## Key Dependencies

### Runtime
- `rich` ≥ 13.0 — terminal tables, panels, progress spinners
- `typer` ≥ 0.9 — CLI commands, options, exit codes
- `requests` ≥ 2.28 — RIPE API, Cloudflare Radar, PeeringDB, server list fetch

### Dev
- `pytest` ≥ 8 — test runner
- `ruff` ≥ 0.4 — linter

### System prerequisites (not Python packages)
- `mtr` — primary path prober (falls back to `traceroute`)
- `iperf3` — bidirectional throughput (falls back to Cloudflare HTTP speedtest)

## Build Commands

| Command | Description |
|---------|-------------|
| `pip install -e ".[dev]"` | Editable install with dev deps (pytest, ruff) |
| `uv pip install -e ".[dev]"` | Same via uv |
| `pytest` | Run test suite |
| `ruff check src tests` | Lint |
| `python -m build` | Build sdist + wheel for release |
| `netpath asn AS15169` | Probe a specific ASN |
| `netpath country ZA --top 10` | Probe top 10 ASNs for a country |

## Project-Specific Notes

- Version is dynamic, derived from git tags via `hatch-vcs`; `src/netpath/_version.py` is gitignored and auto-generated on install
- `NETPATH_CF_TOKEN` env var (or `--cf-token` flag) enables Cloudflare Radar RUM overlay; requires `radar:read` permission
- `NETPATH_ATLAS_KEY` env var (or `--atlas-key` flag) enables RIPE Atlas in-network measurements in country mode; credits budget is checked before scheduling measurements
- Country mode always runs `ecmp_passes=2` and `compare_v6=True` — same path-property depth as `asn` mode; only throughput (iperf3/speedtest) is skipped per ISP
- `mtr.run()` returns `list[dict]` for `passes=1` and `list[list[dict]]` for `passes>1` — callers gate on the passes value
- Exit code from CLI reflects worst verdict across all probes: 0=ok, 1=warning, 2=critical; monitoring scripts can rely on this without parsing JSON
