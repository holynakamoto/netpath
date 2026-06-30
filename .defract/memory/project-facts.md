# Project Facts

## Tech Stack

- [01KWCKPM3RVN3KJDWKDTSGAHR1] **- **netpath dev toolchain: `pip install -e "** -- - **netpath dev toolchain: `pip install -e ".[dev]"`** — Dev dependencies (pytest>=8, ruff>=0.4) live in `[project.optional-dependencies]` under a `dev` key in `pyproject.toml`. Contributors install everything with a single `pip install -e ".[dev]"` from a clean checkout. uv also works: `uv pip install -e ".[dev]"`. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.6]. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.6]

## Conventions

- [01KWCKPP28DBHPG92PJ2YN9QR1] **- **Use `typer** -- - **Use `typer.Exit(code)` for exit codes, never `sys.exit()`** — Calling `sys.exit()` directly bypasses Typer's cleanup. The correct mechanism in any Typer command is `raise typer.Exit(code=N)`. Exit code convention for netpath: 0=ok, 1=warning, 2=critical (worst severity across all probes in a run). [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.7]. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.7]

## Patterns

- [01KWCKPTN09VEWAVZ9R4GZGR63] **- **netpath test strategy: target only pure functions** — Tests cover `diag...** -- - **netpath test strategy: target only pure functions** — Tests cover `diagnosis.diagnose()` and `mtr._parse_traceroute_output` / `_all_stars()` — the only logic units with no subprocess, network, or filesystem dependencies. Testing `_run_test`, `servers.find_servers_in_asn`, or `iperf.run` would require heavy subprocess/HTTP mocking for minimal reliability gain. Module-private functions are importable via direct import: `from netpath.mtr import _parse_traceroute_output`. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.65]. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.6]
- [01KWCKPY8W6FRW7X59FNG4823T] **- **`_measure()` returns `_`-prefixed internal keys for display state** — `...** -- - **`_measure()` returns `_`-prefixed internal keys for display state** — `_measure()` in `cli.py` returns the enriched result dict with both public keys (used for JSON output) and internal `_`-prefixed keys (e.g. `_iperf_upload`, `_iperf_loaded_rtt`, `_trace_error`, `_speedtest_download`) that carry intermediate state for `_run_test()` to use in display without re-running measurements. This keeps `_measure()` side-effect-free while avoiding a second measurement pass. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.6]. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.6]

