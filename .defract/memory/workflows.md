# Proven Workflows

## Workflows

- [01KWCKQ23XMDXGM25652E3BDFP] **- **netpath CI workflow: Python 3** -- - **netpath CI workflow: Python 3.9–3.13 matrix on ubuntu-latest** — `.github/workflows/ci.yml` runs on every push and PR to `main`. Matrix: `python-version: ["3.9", "3.10", "3.11", "3.12", "3.13"]` on `ubuntu-latest` only (macOS runners are slower; pure-function tests have no platform-specific behavior). Each job: `actions/checkout@v4` → `actions/setup-python@v5` → `pip install -e ".[dev]"` → `pytest`. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.65]. [source: task-ways-to-improve-netpath-01kwc564vewr, importance: 0.6]

