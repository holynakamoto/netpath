---
defract:
  version: 1
  generated_at: "2026-06-30T00:00:00Z"
  updated_at: "2026-06-30T00:00:00Z"
  source: extracted
---

# Project Profile

## Overview

`netpath` is a Python CLI tool that probes throughput, latency, and packet loss across Autonomous System (AS) paths. It runs mtr/traceroute to a target ASN, performs bidirectional iperf3 throughput tests against servers inside that ASN, and optionally overlays Cloudflare Radar RUM quality data for comparison.

## Stack

- **Runtime**: Python 3.9+
- **CLI framework**: Typer 0.9+
- **Terminal output**: Rich 13+
- **HTTP client**: requests 2.28+
- **Build backend**: Hatchling
- **Package manager**: pip / uv (`.venv` present; `uvx netpath` supported)
- **CI/CD**: None configured

## Conventions

- `src/` layout — package root is `src/netpath/`; evidence: `[tool.hatch.build.targets.wheel] packages = ["src/netpath"]`
- Entry point via `netpath.cli:run`; evidence: `[project.scripts] netpath = "netpath.cli:run"`
- Typer app with subcommands (`asn`, `country`) defined via `@app.command()` decorators in `cli.py`
- All terminal output routes through a Rich `Console` singleton in `display.py`
- `diagnosis.py` is a pure function with no I/O — kept separate from display logic
- Optional Cloudflare RUM overlay via `NETPATH_CF_TOKEN` env var or `--cf-token` flag
- Graceful fallback chain for probing: mtr → traceroute; for throughput: iperf3 → Cloudflare HTTP speedtest
- `globe.py` renders an interactive 3D in-browser visualization via ip-api.com geolocation + a self-contained HTML tempfile
- ASN lookups use Team Cymru public whois over raw TCP port 43 — no API key required

## File Structure

```
src/netpath/
  __init__.py      # version constant
  __main__.py      # allows `python -m netpath`
  cli.py           # Typer app, `asn` and `country` subcommands
  display.py       # Rich console, all rendering helpers
  diagnosis.py     # pure verdict/classification logic (no I/O)
  mtr.py           # mtr / traceroute runner + Cymru ASN lookup
  servers.py       # iperf3 public server list fetcher + resolver
  asn.py           # ASN normalization utilities
  country.py       # RIPE allocation data fetcher, top-ASN ranking
  rum.py           # Cloudflare Radar RUM API client
  iperf.py         # iperf3 subprocess wrapper
  speedtest.py     # Cloudflare HTTP speedtest fallback
  globe.py         # interactive 3D globe visualization
```

## Key Dependencies

### Runtime
- `rich>=13.0` — terminal tables, panels, spinners, progress bars
- `typer>=0.9` — CLI subcommand framework
- `requests>=2.28` — HTTP calls to ip-api.com, RIPE, Cloudflare Radar

### System (not Python packages)
- `mtr` — primary path prober (falls back to `traceroute` if absent)
- `iperf3` — bidirectional throughput measurement (falls back to Cloudflare HTTP speedtest if absent)

## Build Commands

| Command | Description |
|---------|-------------|
| `pip install -e .` | Install in editable mode |
| `uvx netpath` | Run directly via uv without installing |
| `uv tool install netpath` | Install as a uv tool |
| `netpath asn AS15169` | Probe a specific ASN |
| `netpath country US --top 5` | Probe top 5 ASNs for a country |
| `netpath --help` | List all commands and options |

## Project-Specific Notes

- No CI/CD workflows exist; published to PyPI directly.
- No local env/config files are required — the only optional secret is `NETPATH_CF_TOKEN` (Cloudflare API token with `radar:read` permission, free to create).
- `mtr` requires elevated privileges on some systems; the CLI falls back to `traceroute` + Cymru ASN lookup transparently.
- The `country` subcommand fetches RIPE allocation data to rank ASNs by IPv4 address space, then tests one server per top-N ASN.
