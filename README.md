# netpath

Network path diagnostics for AS paths, exact service endpoints, and regional probe coverage. `netpath` combines traceroute/MTR, optional iperf3 throughput, latency/loss/jitter checks, Globalping remote probes, and Cloudflare Radar RUM overlays.

## Install

```bash
pip install netpath
# or
uvx netpath
# or
uv tool install netpath
```

System tools:

```bash
# macOS
brew install mtr iperf3

# Debian / Ubuntu
sudo apt install mtr-tiny iperf3

# Fedora / RHEL
sudo dnf install mtr iperf3
```

`mtr` is the preferred path prober; `traceroute` is used as a fallback when available. `iperf3` enables cross-ASN throughput tests; without it, netpath falls back to a Cloudflare HTTP speedtest baseline where relevant.

## Quickstart

```bash
# Diagnose a specific service endpoint
netpath host zoom.us

# Generate an escalation-ready root-cause report
netpath explain zoom.us --baseline ~/.netpath/monitor/AS15169.jsonl

# Probe one ASN
netpath asn AS15169

# Sweep top ASNs in a country
netpath country US --top 5

# Monitor path regressions over time
netpath monitor AS15169 --target zoom.us --every 10m

# Compare measured paths between ASNs or cities
netpath aspath AS7922 AS7018
netpath citypath "Los Angeles" "Tokyo"
```

Use `--json` on commands that support scripting output.

## Command guide

| Command | Use when you need to… | Example |
| --- | --- | --- |
| `host` | Trace the exact hostname/IP an app uses; best for SaaS/CDN/Anycast troubleshooting. | `netpath host zoom.us --json` |
| `explain` | Turn an endpoint trace into a likely-cause report with evidence and an escalation summary. | `netpath explain zoom.us --baseline ~/.netpath/monitor/AS15169.jsonl` |
| `asn` | Probe representative public iperf3 servers inside a target ASN. | `netpath asn AS15169 --no-throughput` |
| `country` | Compare top ASNs in a country, with optional Globalping inside-out measurements. | `netpath country GB --top 5` |
| `monitor` | Persist snapshots and report AS-path, RTT, loss, throughput, or verdict regressions. | `netpath monitor AS15169 --target zoom.us --every 10m` |
| `aspath` | Measure paths from probes inside one ASN toward a destination ASN or IP. | `netpath aspath AS7922 AS7018 --target 12.122.1.1` |
| `citypath` | Compare measured paths between two cities using Globalping and RIPE Atlas targets. | `netpath citypath "Los Angeles" "Tokyo"` |
| `target` | Discover or validate a usable probe target inside an ASN. | `netpath target AS7018 --json` |
| `coverage` | Show Globalping probe coverage by country. | `netpath coverage --top 20 --globe` |

### Common options

| Option | Applies to | Meaning |
| --- | --- | --- |
| `-c, --cycles` | `host`, `asn`, `country`, `monitor` | Probe cycles for MTR/traceroute. |
| `-d, --duration` | Throughput-capable commands | iperf3/speedtest duration. |
| `--no-throughput` | `asn`, `country`, `monitor` | Trace only; skip throughput. |
| `--compare-v6` | `host`, `asn`, `country` | Show IPv4/IPv6 traces side by side. |
| `--ecmp-passes` | `host`, `asn`, `country` | Run multiple passes to expose route changes. |
| `--gp-token` | Globalping commands | Optional token for higher Globalping rate limits (`NETPATH_GLOBALPING_TOKEN`). |
| `--cf-token` | RUM-capable commands | Cloudflare Radar token (`NETPATH_CF_TOKEN`). |
| `--baseline` | `explain` | Compare against a monitor JSON/JSONL history file. |
| `--globe` | Visual commands | Open an interactive 3D globe after probing. |

Run `netpath <command> --help` for the full option list.

## Endpoint vs ASN mode

Use `host` when troubleshooting an application path. It bypasses representative ASN/city target selection and traces the resolved endpoint directly, which matters for DNS steering, CDNs, Anycast, and SaaS edges.

Use `asn`, `country`, `aspath`, and `citypath` when characterizing networks or comparing providers. Those modes intentionally select usable targets or remote probes to answer broader path questions.

## Monitoring

`monitor` stores JSONL history under `~/.netpath/monitor` by default:

```bash
netpath monitor AS15169
netpath monitor AS15169 --every 10m --runs 6
netpath monitor AS15169 --target zoom.us --every 10m
netpath monitor AS15169 --forever --every 5m --webhook https://example.com/netpath-alert
```

Standard mode keeps one history file per ASN. `--target` mode keys history by ASN plus resolved endpoint, so application-specific baselines do not mix with representative ASN baselines. Add `--fail-on-regression` for cron or CI jobs.

## Globalping and RUM

Globalping is used for remote, inside-out measurements without requiring an account. A token is optional and only raises rate limits:

```bash
export NETPATH_GLOBALPING_TOKEN=your_token_here
netpath country ZA --top 10
```

Cloudflare Radar RUM overlays need a free token with `radar:read` permission:

```bash
export NETPATH_CF_TOKEN=your_token_here
netpath asn AS15169
```

## Target discovery

When netpath needs a target inside an ASN, it tries public iperf3 servers, connected RIPE Atlas probe addresses, PeeringDB IXP interface addresses, then a small verified sample from RIPEstat announced prefixes. User-provided targets are preserved and annotated with Cymru ASN/prefix attribution.

## Maintainer release flow

Releases are tag-driven. Cut them from `main` with the local helper:

```bash
release-tag v0.27.0 "Describe the change"
```

The helper verifies `main`, runs tests, pushes the commit/tag, and the `v*.*.*` tag triggers PyPI publishing plus GitHub Release creation via GitHub Actions.

## License

MIT
