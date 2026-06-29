---
defract:
  version: 1
  generated_at: "2026-06-29T00:00:00Z"
  updated_at: "2026-06-29T00:00:00Z"
  source: extracted
---

# Project Profile

## Overview

`netpath` is a CLI tool that probes throughput, latency, and packet loss across Autonomous System (AS) paths. It runs mtr/traceroute to a target, performs bidirectional iperf3 throughput tests to servers inside that ASN, and optionally overlays Cloudflare Radar RUM data for comparison.

## Stack

- **Runtime**: Python 3.9+
- **CLI framework**: Typer 0.9+
- **Terminal output**: Rich 13+
- **HTTP client**: requests 2.28+
- **Build backend**: Hatchling
- **Package manager**: pip / venv (`.venv` present)
- **CI/CD**: None configured

## Conventions

- `src/` layout — `src/netpath/` is the package root; evidence: `[tool.hatch.build.targets.wheel] packages = ["src/netpath"]` in `pyproject.toml`
- Entry point via `netpath.cli:run` — evidence: `[project.scripts] netpath = "netpath.cli:run"`
- Typer app with subcommands — `asn` and `country` subcommands defined via `@app.command()` decorators in `cli.py`
- Rich `Console` singleton in `display.py` — all terminal output routes through `display.console`
- External network calls isolated per module — `asn.py` (Cymru whois), `servers.py` (iperf3 server list), `rum.py` (Cloudflare Radar API), `speedtest.py` (Cloudflare speed), `iperf.py` (iperf3 subprocess), `mtr.py` (mtr/traceroute subprocess)
- Module-level process cache for the iperf3 server list — `servers._resolved_cache` avoids redundant fetches within a single invocation
- Graceful fallback chain for path probing: mtr → traceroute (UDP) → traceroute (TCP SYN)
- Graceful fallback chain for throughput: iperf3 → Cloudflare HTTP speedtest (baseline only)
- Type hints used throughout; no strict mypy config observed

## File Structure

```
src/netpath/
├── __init__.py      — package version
├── __main__.py      — python -m netpath entry point
├── cli.py           — Typer app; asn and country subcommands
├── display.py       — all Rich terminal output (tables, panels, formatting)
├── asn.py           — Cymru bulk whois lookups; parallel hostname resolution
├── servers.py       — fetches public iperf3 server list; filters by ASN
├── mtr.py           — mtr (JSON mode) and traceroute fallback; path parsing
├── iperf.py         — iperf3 subprocess wrapper; bidirectional throughput
├── speedtest.py     — Cloudflare HTTP speedtest fallback
├── rum.py           — Cloudflare Radar API; per-ASN RUM quality metrics
└── country.py       — RIPE allocation data; ranks top ASNs by IPv4 space
```

## Key Dependencies

### Runtime
- `rich>=13.0` — terminal tables, panels, progress spinners, color output
- `typer>=0.9` — CLI argument parsing and subcommand routing
- `requests>=2.28` — HTTP calls to iperf3 server list, Cloudflare Radar, speedtest

### External tools (not Python dependencies)
- `mtr` — primary path probing (optional; falls back to traceroute)
- `iperf3` — bidirectional throughput measurement (optional; falls back to HTTP speedtest)

## Build Commands

| Command | Description |
|---------|-------------|
| `pip install -e .` | Install in editable mode |
| `netpath asn <ASN>` | Probe a specific ASN (e.g. `netpath asn AS15169`) |
| `netpath country <CC>` | Probe top ASNs for a country (e.g. `netpath country US`) |
| `netpath --help` | List all commands and options |

## Project-Specific Notes

- Requires `mtr` and/or `iperf3` to be installed on the host system; the tool degrades gracefully if either is missing.
- The `NETPATH_CF_TOKEN` environment variable (or `--cf-token` flag) enables Cloudflare Radar RUM overlay panels; the token needs `radar:read` permission and is free to obtain from a Cloudflare account.
- ASN lookups use Team Cymru's public whois service over a raw TCP socket to port 43; no API key required.
- The `country` subcommand fetches RIPE allocation data to rank ASNs by IPv4 address space, then runs one iperf3/traceroute test per top-N ASN.
