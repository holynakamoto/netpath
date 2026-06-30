---
defract:
  version: 1
  generated_at: "2026-06-30T00:00:00Z"
  updated_at: "2026-06-30T00:00:00Z"
  source: extracted
---

# Project Profile

## Overview

`netpath` is a Python CLI network path analyzer that probes throughput, latency, and packet loss across Autonomous System (AS) paths using mtr/traceroute and iperf3. It supports per-ASN probing, country-wide ISP sweeps, Cloudflare Radar RUM overlay, bufferbloat detection, and optional 3D globe visualization.

## Stack

- **Runtime**: Python ≥3.9 (CI matrix: 3.9–3.13)
- **CLI framework**: Typer ≥0.9
- **Terminal output**: Rich ≥13.0
- **HTTP**: requests ≥2.28
- **Build backend**: Hatchling + hatch-vcs (version from git tags via VCS)
- **Package manager**: uv (uv.lock present); pip also supported
- **Testing**: pytest ≥8
- **Linting**: ruff ≥0.4
- **CI/CD**: GitHub Actions — CI on push/PR to main (matrix py3.9–3.13); publish to PyPI on `v*.*.*` tags via OIDC trusted publishing

## Conventions

- **src layout** — package lives at `src/netpath/`; evidence: `pyproject.toml` `[tool.hatch.build.targets.wheel] packages = ["src/netpath"]`
- **Entry point** — `netpath = "netpath.cli:run"` in `[project.scripts]`; `__main__.py` also present for `python -m netpath`
- **Typer subcommands** — `app = typer.Typer(...)` with two subcommands: `asn` and `country` — evidence: `cli.py:16,331,439`
- **Measurement/display separation** — `_measure()` is pure data collection (no display calls); display is gated on `json_mode` — evidence: `cli.py:157–244`
- **Graceful fallback chain** — mtr → traceroute on PermissionError; iperf3 → Cloudflare HTTP speedtest — evidence: `cli.py:138–142`, `cli.py:232–241`
- **Exit codes encode severity** — `ok=0`, `warning=1`, `critical=2`; CLI exits non-zero on unhealthy verdicts — evidence: `cli.py:32–36`
- **diagnosis.py is a pure function** — no netpath imports, no I/O, wrapped in try/except; always returns a verdict dict — evidence: `diagnosis.py:1`
- **Optional Cloudflare RUM** — gated behind `NETPATH_CF_TOKEN` env var or `--cf-token` flag; silently skipped if absent

## File Structure

```
netpath/
├── pyproject.toml          # project metadata, deps, hatchling build config
├── uv.lock                 # lockfile
├── README.md
├── src/
│   └── netpath/
│       ├── __init__.py     # exposes __version__
│       ├── __main__.py     # python -m netpath entry
│       ├── cli.py          # Typer app; asn + country subcommands
│       ├── diagnosis.py    # pure verdict classifier (no I/O)
│       ├── display.py      # Rich terminal rendering
│       ├── mtr.py          # mtr/traceroute runner + Cymru ASN enrichment
│       ├── asn.py          # ASN normalization utilities
│       ├── servers.py      # public iperf3 server list fetcher/resolver
│       ├── iperf.py        # iperf3 subprocess wrapper
│       ├── speedtest.py    # Cloudflare HTTP speedtest fallback
│       ├── rum.py          # Cloudflare Radar RUM API client
│       ├── country.py      # RIPE allocation data + top-ASN ranking
│       └── globe.py        # 3D globe visualization (--globe flag)
└── tests/
    ├── test_diagnosis.py   # verdict classifier unit tests
    └── test_mtr.py         # mtr parsing tests
```

## Key Dependencies

### Runtime
- `rich>=13.0` — terminal tables, panels, progress spinners
- `typer>=0.9` — CLI argument parsing and subcommands
- `requests>=2.28` — HTTP calls (Cloudflare RUM API, iperf3 server list, speedtest)

### Dev
- `pytest>=8` — test runner
- `ruff>=0.4` — linter

### Build
- `hatchling` + `hatch-vcs` — PEP 517 build backend with git-tag versioning

### System prerequisites (not PyPI)
- `mtr` — primary path prober (`brew install mtr`)
- `iperf3` — bidirectional throughput (`brew install iperf3`)

## Build Commands

| Command | Description |
|---------|-------------|
| `pip install -e ".[dev]"` | Editable install with dev extras |
| `uv sync` | Install all deps from lockfile |
| `pytest` | Run test suite |
| `ruff check .` | Lint |
| `python -m build` | Build sdist + wheel for release |
| `netpath asn AS15169` | Probe a specific ASN |
| `netpath country US` | Probe top ASNs for a country |

## Project-Specific Notes

- `src/netpath/_version.py` is generated at build time by `hatch-vcs` and is gitignored — do not create manually
- `mtr` requires root or `NET_RAW` capability on Linux; falls back to `traceroute` on `PermissionError` transparently
- `iperf3` is optional; without it the tool falls back to a Cloudflare HTTP speedtest (measures user→Cloudflare, not user→target ASN — surfaced in UI)
- `--globe` opens a self-contained HTML tempfile with an interactive 3D path visualization
- `netpath asn --json` outputs structured JSON to stdout and suppresses all terminal display — suitable for scripting/CI
- Published to PyPI as `netpath`; installable via `pip install netpath` or `uvx netpath`
- No local env/config files exist in this project — `.gitignore` covers only build artifacts (`.venv/`, `dist/`, `__pycache__/`, `_version.py`)
