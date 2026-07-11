# netpath

A diagnosis-first network incident investigator for the terminal.

`netpath` answers the operational question behind a traceroute: **is the issue
local, on the route, or at the destination — and who owns the next action?** It
combines traceroute/MTR, application-edge timing, optional iperf3 tests,
Globalping remote corroboration, Cloudflare Radar RUM data, DNS checks, and
saved snapshots into one evidence-backed incident workbench.

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

Enter a hostname or IP and select **Diagnose**. The workbench leads with a
verdict, likely owner, confidence, strongest evidence, and recommended next
action. Path and raw measurements remain available in dedicated tabs.

The workbench is organized around user goals:

- **Investigate:** diagnose an endpoint, compare against a saved snapshot, or
  check DNS propagation
- **Explore:** sample city-to-city and ASN-to-ASN paths, test an ASN, or scan a
  country
- **Tools:** save snapshots, plan a privacy-bounded capture, discover targets,
  inspect probe coverage, or set up iperf3

Every structured investigation keeps the evidence behind its conclusion.
`F6` saves a redacted Markdown + JSON incident bundle under
`~/.netpath/reports` for tickets and handoffs. City and ASN path views are
explicitly labeled as sampled routes to representative discovered targets;
they are not presented as every possible route between the named endpoints.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Ctrl+R` | Run the current analysis |
| `F6` | Export a redacted incident bundle |
| `Ctrl+Q` | Quit |

Sampled city and ASN path results also expose a contextual **Globe** button.

Check the installed version with `netpath --version`.

### Local traffic capture

Select **Capture local traffic** and describe the diagnostic in plain language,
such as “watch DNS traffic for 60 seconds” or “capture my Zoom call for 5
minutes.” Netpath shows the interface, filter, duration, privacy boundary, and
size cap before asking for confirmation. Captures are limited to traffic visible
to the local machine and store only the first 128 bytes of each matching
packet. Those prefixes can contain tens of bytes of application payload; the
confirmation screen states that boundary explicitly. The raw pcap is deleted
after local analysis, and payload content is not included in the report.

Known requests use local rules. For requests such as “capture my Slack
traffic,” choose **Use Codex account** or **Use Claude account** beside the
prompt. Netpath invokes the selected, already-authenticated CLI in
non-interactive schema-only mode; credentials are never copied into netpath.
The prompt is sent to that provider, but packet data is not.

Packet capture may require elevated permission on macOS. When needed, netpath
temporarily suspends the TUI and shows the normal system `sudo` prompt, then
resumes after authentication. It never opens a hidden password prompt.

## Snapshots and incident analysis

Select **Save snapshot** to record a measurement. Snapshots are stored under
`~/.netpath/monitor` and capture route stability, RTT, loss, throughput, and
diagnostic verdicts. A single saved run is intentionally called a snapshot;
repeat monitoring builds the history needed for a meaningful baseline.

Select **Compare snapshot** to compare a new endpoint trace with an existing
measurement. Available JSON and JSONL history files appear automatically in
the interface.

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
