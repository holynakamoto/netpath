---
defract:
  id: task-globe-as-path-latency-viz-pip-uv-install-01kwb0sw8gr0
  type: improvement
  status: active
  stage: implementation
  phase: 0
  total_phases: 2
  priority: normal
  source: manual
  branch_strategy: worktree
  mode: human-in-the-loop
  created_by: holynakamoto
  assignee: holynakamoto
---


## Story Brief

# Globe AS-path latency viz + pip/uv install

# Globe AS-path latency viz + pip/uv install

## What We're Building

Two improvements to netpath: an interactive 3D globe visualization that maps the traced network path onto a rotating earth — geolocating each hop, drawing color-coded arcs between them by latency jump, and opening the result in the browser — and PyPI packaging work that makes netpath installable with `pip install netpath`, `uvx netpath`, or `uv tool install netpath`.

## Expected Outcome

- Running `netpath asn` or `netpath country` with a `--globe` flag produces an interactive 3D globe in the browser, showing the traced AS path as great-circle arcs
- Arc colors encode the latency jump between each pair of consecutive hops: green for fast legs, yellow for moderate, red for high latency using the same thresholds already in the tool
- The globe output is a single self-contained HTML file that works in any browser with no additional installation
- Anyone can install netpath from PyPI with `pip install netpath`, `uvx netpath`, or `uv tool install netpath`
- The repository has a LICENSE file and complete package metadata (authors, project URLs, classifiers) to meet PyPI quality standards

## Phase Outcomes

- **Phase 1: PyPI-ready package** — netpath gains the README, LICENSE file, and complete package metadata required by PyPI, so anyone on the team can publish the package and users can discover and install it from the index.
- **Phase 2: Globe visualization** — users who pass `--globe` after any path probe get an interactive browser tab showing the AS path as color-coded arcs on a rotating 3D globe, making transcontinental hops and high-latency legs immediately visible.

## Out of Scope

- In-terminal ASCII or text-based map rendering — the builder asked for a graphical, browser-based experience
- Precise router-level geolocation; the globe is directional (transcontinental legs are visible) but individual hop dots are not survey-grade locations
- Changes to the path-probing or throughput-measurement logic — this task only adds visualization on top of existing data
- Automated PyPI publish via CI/CD — the packaging work produces a publishable package; the actual publish step can be done manually or added later

## Scope Summary

**Size:** 12 requirements, 10 acceptance criteria, 2 implementation phases
**Key decisions:**
- Use ip-api.com batch API for IP geolocation (free, no API key required, sufficient for ≤100 hops per batch)
- Use Globe.gl via CDN for 3D rendering (no bundler needed, single self-contained HTML file output)
- Arc color uses per-hop latency delta (hop N `Avg` minus hop N-1 `Avg`) against the existing per-hop thresholds in `display.py`
- PyPI packaging adds only metadata and docs files — the existing hatchling build setup is kept as-is
**Biggest risk:** ip-api.com rate limit (45 req/min free tier) may throttle geolocation when the `country` command probes many ASNs with long AS paths in quick succession; the batch endpoint (100 IPs per call) mitigates this, but a graceful fallback message is required.

## Context

netpath currently outputs all results as Rich terminal tables and panels. The globe feature adds a parallel output path: after `_run_test()` returns in both `asn` and `country` subcommands (`cli.py`), the `--globe` flag triggers a new `globe.py` module that geolocates each hop IP via ip-api.com's batch JSON API and generates a self-contained HTML file using Globe.gl (loaded from CDN). The file is written to a temp directory and opened with Python's `webbrowser` module.

For packaging, `pyproject.toml` already declares the MIT license inline (`license = { text = "MIT" }`), but has no `readme` pointer, no `authors` field, no `classifiers`, and no `urls` table — the fields PyPI quality checks require. No `LICENSE` file and no `README.md` exist at the repo root. Both must be created before the package can be published cleanly.

The per-hop latency thresholds in `display.py` (green <20 ms, yellow 20–79 ms, red ≥80 ms) are currently inline in the `fmt_latency()` function. The implementation must extract them as module-level constants so `globe.py` can import them without duplication.

## Requirements

### Globe Visualization

- R1: `netpath asn` and `netpath country` both accept a `--globe / -g` boolean flag that, when set, generates and opens the globe visualization after the probe completes. Flag added to both `@app.command()` decorated functions in `cli.py`.
- R2: When `--globe` is set, the tool geolocates each hop IP using the ip-api.com batch JSON API (`POST http://ip-api.com/batch`). Hops with host `???` or private/RFC1918 IPs (10.x, 172.16–31.x, 192.168.x, 127.x) are silently excluded from the geolocation request and rendered as invisible on the globe.
- R3: Arc color per leg uses the per-hop latency delta (hop N `Avg` minus hop N-1 `Avg`) compared against the thresholds from `display.py`: green if delta <20 ms, yellow if 20–79 ms, red if ≥80 ms. Latency threshold constants must be extracted from `fmt_latency()` in `display.py` into module-level names and imported by `globe.py` rather than re-declared.
- R4: The globe output is a single self-contained HTML file using Globe.gl loaded from CDN (`https://unpkg.com/globe.gl`). Hop data is embedded as inline JSON in a `<script>` block — no server is required to view the file. The file is written to `tempfile.mkdtemp()` and opened with `webbrowser.open()`.
- R5: Each geolocated hop renders as a labeled point on the globe showing the hop number and ASN (e.g., "Hop 3 · AS15169"). Arcs are drawn between consecutive geolocated hops as great-circle paths with a height proportional to geographic distance.
- R6: When the `country` subcommand is used with `--globe`, the per-ASN hub lists collected across the top-N loop are passed together to `globe.render()` after the loop completes. Each ASN's path is layered on the same globe canvas, distinguished by arc opacity or color group. Geolocation requests for all ASNs are batched into as few ip-api.com calls as possible.
- R7: If `--globe` is combined with `--json`, globe generation is skipped and a warning line is printed: `--globe is ignored when --json is set`.
- R8: Geolocation API errors (connection failure, non-200 response, rate-limit response) are caught and reported as a single Rich warning panel. Terminal probe output (tables, panels) is unaffected — probe results are always displayed regardless of globe success or failure.

### PyPI Packaging

- R9: `pyproject.toml` is extended with: `authors` list (name + email), `[project.urls]` table (`Homepage`, `Bug Tracker`), `classifiers` (Python versions 3.9–3.13, OS :: OS Independent, Topic :: System :: Networking :: Monitoring, Development Status), and `readme = "README.md"` pointer.
- R10: `README.md` is created at the repo root with: project description, install instructions (`pip install netpath`, `uvx netpath`, `uv tool install netpath`), system prerequisites (`mtr`, `iperf3`), usage examples for both subcommands, and a note on the `NETPATH_CF_TOKEN` environment variable.
- R11: `LICENSE` is created at the repo root containing the MIT license text with the correct year and author name.
- R12: Running `python -m build` (or `hatch build`) in a clean venv produces a wheel and sdist with no warnings, and `pip install dist/*.whl` followed by `netpath --help` exits successfully showing the correct version.

## Acceptance Criteria

- [ ] `netpath asn AS15169 --globe` opens a browser tab showing a 3D globe with colored hop arcs; verified by running the command and observing the browser open.
- [ ] `netpath country US --globe` opens a browser tab with multiple ASN paths layered on the globe.
- [ ] Arc colors match the per-hop latency delta thresholds; a fast local hop (delta <20 ms) appears green and a slow intercontinental leg (delta ≥80 ms) appears red.
- [ ] Running `netpath asn AS15169 --globe --json` prints a warning containing "ignored" and produces no HTML file.
- [ ] Hops with host `???` and private IPs produce no arc or labeled point on the globe; confirmed by inspecting the embedded JSON in the generated HTML.
- [ ] `python -m build` completes without warnings in a clean venv; `pip install dist/*.whl` succeeds; `netpath --help` shows the correct version string.
- [ ] `pip show netpath` after install includes author name, homepage URL, and license field.
- [ ] README.md renders correctly on GitHub: no broken formatting, all code blocks valid.
- [ ] `LICENSE` file at repo root contains MIT license text with correct year.
- [ ] `uvx netpath --help` succeeds in a fresh environment (simulates end-to-end uv install and run).

## Implementation Phases

### Phase 1: PyPI Packaging
**Scope:** Add the README, LICENSE file, and pyproject.toml metadata fields needed to pass PyPI quality checks and make the package publishable from the current source tree.
**Files:**
- `README.md` (new) — project description, install instructions, usage, prerequisites
- `LICENSE` (new) — MIT license text with year and author
- `pyproject.toml` (modify) — add `authors`, `readme`, `urls`, and `classifiers` fields
**Verification:**
- [ ] `python -m build` produces wheel and sdist with no warnings in a clean venv
- [ ] `pip install dist/*.whl && netpath --help` shows correct version
- [ ] `pip show netpath` includes author name and homepage URL
- [ ] README.md renders without broken formatting on GitHub
**Estimated effort:** Small

### Phase 2: Globe Visualization
**Scope:** Add a `--globe` flag to both CLI subcommands and a new module that geolocates traced hops and generates a self-contained interactive 3D globe HTML file opened automatically in the browser.
**Files:**
- `src/netpath/globe.py` (new) — ip-api.com batch geolocation, Globe.gl HTML generation, `webbrowser.open()` call, edge-case handling
- `src/netpath/display.py` (modify) — extract per-hop latency threshold values into module-level constants
- `src/netpath/cli.py` (modify) — add `--globe / -g` flag to `asn` and `country`; pass hub lists to `globe.render()` after probes complete
**Verification:**
- [ ] `netpath asn AS15169 --globe` opens browser with 3D globe and arcs
- [ ] `netpath country US --globe` shows multiple layered ASN paths on one globe
- [ ] `--globe --json` prints warning and generates no HTML file
- [ ] Hops with `???` or private IPs are absent from the globe's embedded JSON
- [ ] Simulating a geolocation API failure (mock 429 response) logs a Rich warning panel and leaves terminal output intact
- [ ] `webbrowser.open()` returning `False` prints the HTML file path instead of silently failing
**Estimated effort:** Medium

## Edge Cases

- **All hops are `???`**: Globe generation is skipped and a warning is shown instead of writing an empty HTML file.
- **Single geolocated hop**: One dot renders with no arcs; this is valid and must not raise an exception.
- **ip-api.com rate limit (429 or quota message)**: Globe generation aborts with a single warning panel; terminal probe results are displayed normally.
- **No browser available** (headless server): `webbrowser.open()` returns `False`; a message is printed with the full path to the HTML file so the user can retrieve it.
- **`country` command with many ASNs**: All hops from all ASNs are combined into the minimum number of batch requests (each ≤100 IPs) before calling ip-api.com.
- **Private/RFC1918 IPs in path**: Filtered out before sending to ip-api.com; rendered as invisible gaps in the arc chain.
- **First hop has no prior hop for delta**: First geolocated hop renders as a point only; no arc is drawn to it from a phantom predecessor.

## Technical Notes

Globe.gl (`https://unpkg.com/globe.gl`) is the chosen 3D rendering library. It wraps Three.js and provides a declarative API for arcs, labels, and points on a sphere. Three.js is resolved automatically by the CDN. The generated HTML file requires internet access to load these CDN scripts, but once loaded it can be saved and re-opened without re-running the probe.

The ip-api.com batch endpoint: `POST http://ip-api.com/batch` with body `[{"query": "<ip>", "fields": "query,lat,lon,status"}, ...]` (max 100 IPs per request). The free tier counts the entire batch call as one request against the 45 req/min limit. No API key is required.

Latency delta for arc color: `delta = hubs[i]["Avg"] - hubs[i-1]["Avg"]`, where both hops have a valid geolocation. Negative deltas (latency decreasing along path) are treated as green. The threshold constants extracted from `display.py` should be named `LATENCY_GREEN_MS = 20` and `LATENCY_YELLOW_MS = 80` (matching the existing `fmt_latency()` breakpoints).

For the `country` subcommand, `_run_test()` is called inside a loop. The `--globe` logic must collect all per-ASN hub lists into a `dict[str, list[dict]]` keyed by ASN string, and pass the combined dict to `globe.render()` once after the loop — not per-iteration — to avoid making multiple browser tabs.

No new runtime dependencies are introduced: `requests` (already a dependency) handles ip-api.com; `webbrowser` and `tempfile` are Python stdlib. The `globe.py` module does not need to be listed in `pyproject.toml` dependencies.
