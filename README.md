# netpath

An interactive network path analyzer for investigating routes, latency, packet
loss, throughput, DNS propagation, and regional probe coverage.

`netpath` brings traceroute/MTR, optional iperf3 throughput tests, Globalping
remote probes, Cloudflare Radar RUM data, and incident baselines into one
terminal interface.

## Install

```bash
pip install netpath
```

You can also run it without installing:

```bash
uvx netpath
```

For the best results, install the optional system tools:

```bash
# macOS
brew install mtr iperf3

# Debian / Ubuntu
sudo apt install mtr-tiny iperf3

# Fedora / RHEL
sudo dnf install mtr iperf3
```

`mtr` is the preferred path prober; `traceroute` is used as a fallback when
available. `iperf3` enables cross-ASN throughput tests. Without it, netpath uses
a Cloudflare HTTP speed-test baseline where relevant.

## Get started

Launch netpath:

```bash
netpath
```

Choose an analysis mode, enter the requested endpoints, and select **Run**.

The TUI includes:

- city-to-city and ASN-to-ASN path ranking
- hostname and IP traces
- ASN and country analysis
- DNS propagation checks
- natural-language, headers-only local traffic capture
- reusable monitoring baselines and incident explanations
- ASN target discovery
- Globalping probe coverage
- iperf3 server setup

Path results include geolocated hops, RTT, network ownership, an approximate
terminal route map, and an optional browser-based globe.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Ctrl+R` | Run the current analysis |
| `m` | Cycle through analysis modes |
| `g` | Open the latest path on the globe |
| `q` | Quit |

Check the installed version with `netpath --version`.

### Local traffic capture

Select **Capture local traffic** and describe the diagnostic in plain language,
such as “watch DNS traffic for 60 seconds” or “capture my Zoom call for 5
minutes.” Netpath shows the interface, filter, duration, privacy boundary, and
size cap before asking for confirmation. Captures are limited to traffic visible
to the local machine and the raw pcap is deleted after analysis.

Known requests use local rules. For requests such as “capture my Slack
traffic,” choose **Use Codex account** or **Use Claude account** beside the
prompt. Netpath invokes the selected, already-authenticated CLI in
non-interactive schema-only mode; credentials are never copied into netpath.
The prompt is sent to that provider, but packet data is not.

Packet capture may require elevated permission on macOS. Run `sudo -v` in
another terminal before confirming; netpath never opens a hidden password
prompt.

## Baselines and incident analysis

Select **Create baseline** to save a measurement. Baselines are stored under
`~/.netpath/monitor` and capture route stability, RTT, loss, throughput, and
diagnostic verdicts.

Select **Explain incident** to compare a new endpoint trace with an existing
baseline. Available JSON and JSONL baseline files appear automatically in the
interface.

## Remote measurements

[Globalping](https://globalping.io/) provides remote, inside-out measurements
without requiring an account. A token is optional and increases the available
rate limit:

```bash
export NETPATH_GLOBALPING_TOKEN=your_token_here
netpath
```

Cloudflare Radar RUM overlays require a token with `radar:read` permission:

```bash
export NETPATH_CF_TOKEN=your_token_here
netpath
```

## Target discovery and throughput

When netpath needs a target inside an ASN, it checks registered and public
iperf3 servers, connected RIPE Atlas probes, PeeringDB IXP interfaces, and a
small verified sample of RIPEstat announced prefixes.

Real cross-ASN throughput measurements require an iperf3 server inside the
target network. Network operators can select **Set up iperf3 server** in the TUI
to configure one. Open TCP and UDP port 5201 if the server should be reachable
from outside the network.

Container, systemd, cloud-init, and community registry deployment assets are
also included with the package. See the
[operator guide](src/netpath/deploy/README.md) for details.

## Development

```bash
make validate  # sync dev extras, then run tests and lint
make test      # run the test suite
make lint      # run Ruff
```

## Maintainer release flow

Releases are tag-driven. Cut them from `main` with the local helper:

```bash
release-tag v0.27.0 "Describe the change"
```

The helper verifies `main`, runs the tests, and pushes the commit and tag. A
`v*.*.*` tag triggers PyPI publishing and GitHub Release creation through
GitHub Actions.

## License

MIT
