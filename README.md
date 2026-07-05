# netpath

Network path analyzer: probe throughput, latency, and packet loss across Autonomous System (AS) paths. Runs mtr/traceroute to a target ASN, measures bidirectional iperf3 throughput to servers inside that ASN, and optionally overlays Cloudflare Radar RUM data for comparison.

## Installation

```bash
pip install netpath
```

```bash
uvx netpath
```

```bash
uv tool install netpath
```

## System Prerequisites

netpath relies on two external tools for path probing and throughput measurement. Install them before running:

- **mtr** — primary path prober (falls back to traceroute if unavailable)
- **iperf3** — bidirectional throughput measurement (falls back to Cloudflare HTTP speedtest if unavailable)

```bash
# macOS
brew install mtr iperf3

# Debian / Ubuntu
sudo apt install mtr-tiny iperf3

# Fedora / RHEL
sudo dnf install mtr iperf3
```

## Usage

### Probe a specific ASN

```bash
netpath asn AS15169
```

Options:

```
-n, --count INTEGER       Max servers to test (default: 3)
-d, --duration INTEGER    iperf3 seconds per direction (default: 5)
-c, --cycles INTEGER      mtr probe cycles (default: 10)
--no-throughput           Skip throughput test, trace path only
--cf-token TEXT           Cloudflare API token (or set NETPATH_CF_TOKEN)
--json                    Output results as JSON
```

### Probe top ASNs for a country

```bash
netpath country US
```

Options:

```
-t, --top INTEGER         Number of top ASNs to test (default: 10)
-n, --count INTEGER       Max servers per ASN (default: 3)
-d, --duration INTEGER    iperf3 seconds per direction (default: 5)
-c, --cycles INTEGER      mtr probe cycles (default: 10)
--no-throughput           Skip throughput test
--no-remote               Skip Globalping in-network measurements
--compare-v6              Show IPv4/IPv6 traces side by side
--ecmp-passes INTEGER     Run multiple mtr passes to detect path changes
--show-ids                Show Globalping measurement IDs while scheduling
--cf-token TEXT           Cloudflare API token (or set NETPATH_CF_TOKEN)
--gp-token TEXT           Globalping token for a higher rate limit (optional; or set NETPATH_GLOBALPING_TOKEN)
--globe                   Open interactive 3D globe after probes complete
```

### Probe an exact hostname or IP

```bash
netpath host zoom.us
netpath host 170.114.52.2 --json
```

`host` bypasses representative ASN/city target selection and traces the exact resolved endpoint, which is the better fit for application troubleshooting when DNS, Anycast, CDN policy, or service routing may send users to a specific edge.

Options:

```
-d, --duration INTEGER    iperf3 seconds per direction when --throughput is set (default: 5)
-c, --cycles INTEGER      mtr probe cycles (default: 10)
--throughput              Try iperf3 throughput to the destination on port 5201
--compare-v6              Show IPv4/IPv6 traces side by side
--ecmp-passes INTEGER     Run multiple mtr passes to detect path changes
--cf-token TEXT           Cloudflare API token (or set NETPATH_CF_TOKEN)
--json                    Output results as JSON
--globe                   Open interactive 3D globe after probe
```

### Monitor an ASN for regressions

```bash
netpath monitor AS15169
netpath monitor AS15169 --every 10m --runs 6
netpath monitor AS15169 --every 5m --forever --webhook https://example.com/netpath-alert
netpath monitor AS15169 --target zoom.us --every 10m
```

`monitor` stores JSONL history under `~/.netpath/monitor` by default: one file per ASN in standard mode, or endpoint-specific files when `--target` is used (keyed by ASN plus resolved endpoint). It compares each new snapshot with the previous one and reports AS-path changes, RTT regressions, packet-loss increases, throughput drops, and verdict worsening. Use `--store` to choose a different history directory and `--fail-on-regression` for cron or CI jobs.

Options:

```
-n, --count INTEGER              Max servers to test (default: 3)
-d, --duration INTEGER           iperf3 seconds per direction (default: 5)
-c, --cycles INTEGER             mtr probe cycles (default: 10)
--no-throughput                  Skip throughput test
--every TEXT                     Repeat interval, e.g. 30s, 10m, 2h
--runs INTEGER                   Number of snapshots to collect (default: 1)
--forever                        Run until interrupted; requires --every
--store TEXT                     History directory (default: ~/.netpath/monitor)
--target TEXT                    Monitor this exact hostname/IP instead of an auto-selected ASN endpoint
--webhook TEXT                   POST regressions to this webhook URL
--fail-on-regression             Exit 2 when a regression is detected
--rtt-threshold-ms FLOAT         Minimum RTT increase to report (default: 25)
--loss-threshold-pct FLOAT       Minimum loss increase to report (default: 1)
--throughput-drop-pct FLOAT      Minimum download drop to report (default: 30)
--cf-token TEXT                  Cloudflare API token (or set NETPATH_CF_TOKEN)
```

### Compare AS paths between two ASNs

```bash
netpath aspath AS7922 AS7018
```

This schedules Globalping ping + MTR measurements from probes inside the source ASN toward a live target in the destination ASN, then ranks distinct AS paths by measured RTT and AS-hop count. It reports the best measured path plus any alternate paths visible from the selected probes.

Options:

```
--gp-token TEXT           Globalping token for a higher rate limit (optional; or set NETPATH_GLOBALPING_TOKEN)
--target IP               Use this destination IP instead of automatic target discovery
--globe                   Open an interactive globe of the measured AS path
--json                    Output results as JSON
```

`aspath` enriches AS hops with network names when available and includes approximate city-level geolocation for public hop IPs:

```bash
netpath aspath AS14593 AS12400 --globe
```

### Compare measured paths between two cities

```bash
netpath citypath "Los Angeles" "Tokyo"
```

Quote multi-word city names. This geocodes the source and destination cities, measures from Globalping probes in the source city, chooses the nearest connected RIPE Atlas IPv4 target near the destination city, and ranks the AS paths it observes.

Options:

```
--gp-token TEXT           Globalping token for a higher rate limit (optional; or set NETPATH_GLOBALPING_TOKEN)
--globe                   Open an interactive globe of the measured city path
--json                    Output results as JSON
```

### Find a usable target in an ASN

```bash
netpath target AS7018
```

Target discovery tries public iperf3 servers, connected RIPE Atlas probe addresses, PeeringDB IXP interface addresses, then a small sample from RIPEstat announced prefixes. Prefix-sampled targets are verified with Cymru; when TCP/443 or TCP/80 responds they are marked medium-confidence, otherwise a routed but unresponsive sample can be returned as low-confidence.

```bash
netpath target AS7018 --json
netpath target AS7018 --target 12.122.1.1
```

### Probe coverage

```bash
netpath coverage --top 10
```

Fetches the connected probe inventory from Globalping — no account or token needed — and displays a ranked table showing which countries have the richest coverage:

```
   Globalping Coverage — Top 10 Countries
 ┌────┬──────┬──────────────────────┬────────┐
 │  # │ Code │ Country              │ Probes │
 ├────┼──────┼──────────────────────┼────────┤
 │  1 │ US   │ United States        │    142 │
 │  2 │ DE   │ Germany              │     87 │
 │  3 │ FR   │ France               │     54 │
 └────┴──────┴──────────────────────┴────────┘
```

Options:

```
-t, --top INTEGER         Rows to show (default: 20)
--gp-token TEXT           Globalping token for a higher rate limit (optional)
--globe                   Open choropleth globe showing coverage density
```

### Examples

```bash
# Probe Google's ASN
netpath asn AS15169

# Probe top 5 UK ISPs
netpath country GB --top 5

# Path-only probe (no throughput test)
netpath asn AS7018 --no-throughput

# JSON output for scripting
netpath asn AS15169 --json | jq .verdict
```

## Globalping

[Globalping](https://globalping.io/) is a free, community-powered network of measurement probes around the world. netpath uses it to measure your network path from *inside* each target ISP — probes inside the ISP ping the per-ASN test address and run an mtr trace back to your public IP, giving you an inside-out view of each AS hop. No account, API key, or credit balance is required: in-network measurements run by default in country mode.

```bash
netpath country ZA --top 10
```

Pass `--no-remote` for a faster, local-only sweep with no in-network measurements:

```bash
netpath country ZA --top 10 --no-remote
```

### What the output looks like

When Globalping probes exist in a target ASN, a `[Globalping]` row appears below the regular measurement showing the inbound RTT and the outbound AS path as seen from inside that ISP:

```
  [Globalping] RTT 12.3 ms avg (9.8–15.1), outbound: AS37611 → AS3356 → AS7018
```

When no probes exist in a target ASN, the tool reports "no Globalping coverage" and continues to the next ASN.

### Higher rate limits (optional)

Unauthenticated use is rate-limited per IP, which is plenty for typical sweeps. For large or frequent sweeps, a free Globalping token raises the hourly limit — see the [Globalping docs](https://globalping.io/docs/api.globalping.io#authentication) for current limits:

```bash
export NETPATH_GLOBALPING_TOKEN=your_token_here
netpath country ZA --top 10
```

Or pass it inline with `--gp-token`. A token is never required.

### Probe coverage

Use `netpath coverage` to discover which countries have the richest probe coverage before planning a sweep:

```bash
netpath coverage --top 10
netpath coverage --top 20 --globe
```

### Upgrading from earlier versions

Earlier releases performed in-network measurements through a RIPE Atlas backend that required an API key and a credit balance. That backend has been fully removed: the old key flag no longer exists, its environment variable is obsolete and silently ignored (you can delete it from your shell profile), and the old coverage command is now `netpath coverage`. Nothing needs to be configured — in-network measurements work out of the box. One narrow Atlas touchpoint survives: country mode performs a public, keyless lookup of the RIPE Atlas probes API solely to discover a live trace-target address inside an ASN — no key, credits, or measurements are involved.

## Maintainer Release Flow

This repository expects releases to be cut from `main` with the local `release-tag` helper:

```bash
release-tag v0.23.0 "Describe the change"
```

The helper runs the full release path without an interactive prompt:

1. Fetches `origin/main` and tags.
2. Fails if the tag already exists locally or on GitHub.
3. Verifies `main` has not diverged from `origin/main`.
4. Runs `git diff --check`.
5. Runs `uv run --extra dev pytest`.
6. Stages and commits any current changes with the message you passed.
7. Pushes `main`.
8. Creates and pushes an annotated tag at the pushed commit.
9. Verifies the remote tag points at the same commit as local `HEAD`.

If you just updated the helper in `~/.zshrc`, reload your shell before releasing:

```bash
source ~/.zshrc
```

## Cloudflare Radar RUM Overlay

netpath can overlay Cloudflare Radar Real User Monitoring (RUM) quality metrics for each ASN, showing real-world HTTP performance data alongside your own measurements.

To enable it, pass a Cloudflare API token with `radar:read` permission:

```bash
export NETPATH_CF_TOKEN=your_token_here
netpath asn AS15169
```

Or pass it inline:

```bash
netpath asn AS15169 --cf-token your_token_here
```

Tokens are free. Create one in the [Cloudflare dashboard](https://dash.cloudflare.com/profile/api-tokens) with the `radar:read` permission scope.

## License

MIT
