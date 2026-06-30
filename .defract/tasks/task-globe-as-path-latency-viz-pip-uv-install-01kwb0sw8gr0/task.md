---
defract:
  id: task-globe-as-path-latency-viz-pip-uv-install-01kwb0sw8gr0
  type: improvement
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

## Story Brief

# Globe AS-path latency viz + pip/uv install

## What We're Building

Two improvements to netpath: an interactive 3D globe visualization that maps the traced network path onto a rotating earth — geolocating each hop, drawing color-coded arcs between them by latency jump, and opening the result in the browser — and PyPI packaging work that makes netpath installable with `pip install netpath`, `uvx netpath`, or `uv tool install netpath`.

## Expected Outcome

- Running `netpath asn` or `netpath country` with a `--globe` flag produces an interactive 3D globe in the browser, showing the traced AS path as great-circle arcs
- Arc colors encode the latency jump between each pair of consecutive hops: green for fast legs, yellow for moderate, red for high latency using the same thresholds already in the tool
- The globe output is a single self-contained HTML file that works in any browser with no additional installation
- Anyone can install netpath from PyPI with `pip install netpath`, `uvx netpath`, or `uv tool install netpath`
- The repository has a LICENSE file and complete package metadata (authors, project URLs, classifiers) to meet PyPI quality standards

## Out of Scope

- In-terminal ASCII or text-based map rendering — the builder asked for a graphical, browser-based experience
- Precise router-level geolocation; the globe is directional (transcontinental legs are visible) but individual hop dots are not survey-grade locations
- Changes to the path-probing or throughput-measurement logic — this task only adds visualization on top of existing data
- Automated PyPI publish via CI/CD — the packaging work produces a publishable package; the actual publish step can be done manually or added later
