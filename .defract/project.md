---
defract:
  version: 1
  generated_at: "2026-06-30T00:00:00Z"
  updated_at: "2026-06-30T00:00:00Z"
  source: extracted
---

# Project Profile

## Overview

`netpath` is a Python CLI tool that probes network path quality — latency, packet loss, and bidirectional throughput — to a target Autonomous System (ASN) or to the top ISPs for a given country. It combines mtr/traceroute path analysis with iperf3 throughput measurement and optional Cloudflare Radar RUM overlay.

## Stack

- **Runtime**: Python 3.9–3.13 (matrix CI)
- **CLI framework**: Typer 0.9+
- **Terminal output**: Rich 13+
- **HTTP**: requests 2.28+
- **Build system**: Hatchling (PEP 517)
- **Package manager**: uv (uv.lock present)
- **Testing**: pytest 8+
- **Linting**: ruff 0.4+
- **CI/CD**: GitHub Actions (`.github/workflows/ci.yml`) — matrix across Python 3.9–3.13 on ubuntu-latest

## Conventions

- **src layout** — package lives at `src/netpath/`; entry point is `netpath.cli:run` — evidence: `pyproject.toml` `[tool.hatch.build.targets.wheel]` and `[project.scripts]`
- **Typer subcommands** — single `app = typer.Typer(...)` in `cli.py` with two subcommands (`asn`, `country`) — evidence: `cli.py:16`
- **Measurement/display separation** — `_measure()` is pure data collection with no display calls; display is gated on `json_mode` — evidence: `cli.py:157–244`
- **Graceful fallback chain** — iperf3 falls back to Cloudflare HTTP speedtest; mtr falls back to traceroute — evidence: `cli.py:138–142`, `cli.py:232–241`
- **Exit codes encode severity** — 0 = ok, 1 = warning, 2 = critical — evidence: `cli.py:32`
- **Optional CF token** — Cloudflare RUM overlay via `NETPATH_CF_TOKEN` env var or `--cf-token` flag; silently skipped if absent
- **Tests live in `tests/`** — `test_mtr.py`, `test_diagnosis.py`

## File Structure

```
netpath/
├── pyproject.toml          # project metadata, deps, build config
├── uv.lock                 # uv lockfile
├── README.md
├── src/
│   └── netpath/
│       ├── __init__.py     # version constant
│       ├── __main__.py     # python -m netpath entry
│       ├── cli.py          # Typer app, subcommands: asn, country
│       ├── asn.py          # ASN normalization utilities
│       ├── country.py      # RIPE/Cymru top-ASN lookup by country code
│       ├── diagnosis.py    # verdict/severity logic (pure, no I/O)
│       ├── display.py      # Rich terminal rendering helpers
│       ├── globe.py        # interactive 3D globe visualization (--globe)
│       ├── iperf.py        # iperf3 subprocess wrapper
│       ├── mtr.py          # mtr/traceroute subprocess wrapper + Cymru lookup
│       ├── rum.py          # Cloudflare Radar RUM API client
│       ├── servers.py      # public iperf3 server list + ASN filtering
│       └── speedtest.py    # Cloudflare HTTP speedtest fallback
└── tests/
    ├── test_mtr.py
    └── test_diagnosis.py
```

## Key Dependencies

### Runtime
- `rich>=13.0` — terminal tables, panels, spinners, progress bars
- `typer>=0.9` — CLI framework with argument/option parsing
- `requests>=2.28` — HTTP calls to RIPE, Cymru, Cloudflare Radar APIs

### Dev
- `pytest>=8` — test runner
- `ruff>=0.4` — linting

### System prerequisites (not PyPI)
- `mtr` — primary path prober (falls back to `traceroute`)
- `iperf3` — bidirectional throughput (falls back to Cloudflare HTTP speedtest)

## Build Commands

| Command | Description |
|---------|-------------|
| `pip install -e ".[dev]"` | Install in editable mode with dev extras |
| `uv run netpath` | Run via uv |
| `uvx netpath` | Run without installing |
| `pytest` | Run tests |
| `ruff check .` | Lint |
| `python -m build` | Build distribution wheel |

## Project-Specific Notes

- `NETPATH_CF_TOKEN` env var enables Cloudflare Radar RUM overlay; without it, RUM data is silently skipped. Token requires `radar:read` permission (free to create at dash.cloudflare.com).
- The `--globe` flag opens a self-contained HTML tempfile with an interactive 3D path visualization.
- `netpath asn --json` outputs structured JSON to stdout and suppresses all terminal display — safe for scripting and CI.
- `mtr` requires elevated privileges on some systems; CLI falls back to `traceroute` + Cymru ASN lookup transparently.
- Published to PyPI as `netpath`; installable via `pip install netpath` or `uvx netpath`.
- No local env/config files exist — the `.gitignore` covers only build artifacts (`.venv/`, `dist/`, `__pycache__/`).
