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
--cf-token TEXT           Cloudflare API token (or set NETPATH_CF_TOKEN)
--atlas-key KEY           RIPE Atlas API key for in-network measurements (or set NETPATH_ATLAS_KEY)
--globe                   Open interactive 3D globe after probes complete
```

### Atlas coverage profile

```bash
netpath atlas-profile --top 10
```

Fetches probe and anchor counts from RIPE Atlas and displays a ranked table showing which countries have the richest coverage:

```
   Atlas Coverage — Top 10 Countries
 ┌────┬──────┬──────────────────────┬────────┬─────────┬───────┐
 │  # │ Code │ Country              │ Probes │ Anchors │ Total │
 ├────┼──────┼──────────────────────┼────────┼─────────┼───────┤
 │  1 │ US   │ United States        │   1842 │     104 │  1946 │
 │  2 │ DE   │ Germany              │    898 │      59 │   957 │
 │  3 │ FR   │ France               │    601 │      48 │   649 │
 └────┴──────┴──────────────────────┴────────┴─────────┴───────┘
```

Options:

```
--atlas-key KEY           RIPE Atlas API key (or set NETPATH_ATLAS_KEY)
-t, --top INTEGER         Rows to show (default: 20)
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

## RIPE Atlas

[RIPE Atlas](https://atlas.ripe.net/) is a global network of ~13,000 hardware probes hosted by volunteers. netpath can use Atlas probes to measure your network path from *inside* each target ISP — the probes ping your IP and run a traceroute back to you, giving you an inside-out view of each AS hop.

### Getting an Atlas key

Create a free account at <https://atlas.ripe.net/> and generate an API key with **measurement creation** permission. Each sweep costs approximately 11 Atlas credits per probe per ASN (1 ping + 10 traceroute).

```bash
export NETPATH_ATLAS_KEY=your_key_here
netpath country ZA --top 10
```

Or pass the key inline:

```bash
netpath country ZA --top 10 --atlas-key your_key_here
```

### What the output looks like

When Atlas probes exist in a target ASN, a `[Atlas]` row appears below the regular measurement showing the inbound RTT and AS path as seen from inside that ISP:

```
  [Atlas]  ping avg 12.3 ms  AS37611 → AS3356 → AS7018 → ...
```

When no volunteer probes exist but **anchor nodes** do, the tool falls back automatically and labels the row `[Atlas anchor]`:

```
  [Atlas anchor]  ping avg 28.1 ms  AS37611 → AS3356 → ...
```

When neither probes nor anchors exist for a target ASN, the tool reports "no Atlas coverage" and continues to the next ASN.

### Atlas coverage profile

Use `netpath atlas-profile` to discover which countries have the richest Atlas coverage before planning a sweep:

```bash
netpath atlas-profile --top 10
netpath atlas-profile --top 20 --globe
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
