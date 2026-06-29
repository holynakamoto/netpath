# Design System

## Overview

netpath is a Python CLI tool with no web frontend. Its visual layer is entirely terminal-based, implemented with the [Rich](https://github.com/Textualize/rich) library (`rich>=13.0`) and [Typer](https://typer.tiangolo.com/) (`typer>=0.9`). All styling is expressed as Rich markup strings (e.g. `[bold cyan]`, `[dim]`) and component configuration in `src/netpath/display.py`.

## Colors

Rich's built-in ANSI color names are used directly — no hex values. Colors carry semantic meaning tied to data quality thresholds.

### Semantic Roles

| Role | Rich Style | Usage |
|------|-----------|-------|
| Brand / primary accent | `cyan` | App header panel border, table header text, section rule color, ISP rank numbers |
| Server / structural | `blue` | Server heading panel border, throughput panel border |
| Real-user metrics | `magenta` | RUM panel border |
| Good / success | `green` | 0% packet loss, success checkmark (✓), target ASN final hop |
| Very good | `bold green` | Latency < 20 ms, upload label (↑), found-servers message, final AS path hop |
| Warning | `yellow` | Latency 20–79 ms, packet loss 1–4.9%, AS boundary hops, warning icon (⚠) |
| Prominent label | `bold yellow` | ISP/ASN identifiers in the country ranking list |
| Bad | `bold red` | Latency ≥ 80 ms, packet loss ≥ 5% |
| Error | `red` | Error symbol (✗) |
| Muted / secondary | `dim` | Metadata, unreachable hops (`* * *`), non-critical labels, path arrows |
| Emphasized text | `bold` | Host names, panel titles, important values |

## Status Thresholds

### Latency (`fmt_latency` in `display.py:28`)

| Range | Style | Display |
|-------|-------|---------|
| ≤ 0 ms | `dim` | — |
| < 20 ms | `bold green` | `N.N ms` |
| 20–79 ms | `yellow` | `N.N ms` |
| ≥ 80 ms | `bold red` | `N.N ms` |

### Packet Loss (`fmt_loss` in `display.py:39`)

| Range | Style | Display |
|-------|-------|---------|
| 0% | `green` | `0.0%` |
| 1–4.9% | `yellow` | `N.N%` |
| ≥ 5% | `bold red` | `N.N%` |

## Typography

Rich uses the terminal's default monospace font. No custom font configuration is applied.

### Text Hierarchy

| Level | Rich Style | Used For |
|-------|-----------|----------|
| Title / brand | `bold cyan` | App name in header, table column headers |
| Heading | `bold` | Panel titles, host names, server labels |
| Body | *(unstyled)* | Default terminal text |
| Secondary / metadata | `dim` | ASN info, probe counts, fallback messages |

## Icons

Consistent icon set used throughout the CLI:

| Icon | Color | Meaning |
|------|-------|---------|
| `✓` | `green` | Success (servers found, operation complete) |
| `✗` | `red` | Error |
| `⚠` | `yellow` | Warning |
| `→` | `dim` | Direction / path indicator |
| `↑` | `bold green` | Upload |
| `↓` | `bold cyan` | Download |

## Components

All components are implemented in `src/netpath/display.py` using Rich primitives.

### Panel Types

| Component | Border Style | Purpose |
|-----------|-------------|---------|
| App header | `cyan` | Shown once per run; displays app name and description |
| Server heading | `blue` | Per-server panel showing host, ASN, site, country, port |
| Throughput (iperf3) | `blue` | Upload/download speeds + optional TTFB and retransmits |
| RUM metrics | `magenta` | Cloudflare Radar real-user metrics (download, upload, latency, jitter, loss) |
| Baseline speedtest | `blue` | User's own Cloudflare connection baseline |
| Side-by-side panels | `Columns` | Throughput + RUM rendered next to each other when both available |

### Path Table

Rich `Table` with `box.SIMPLE_HEAD`, columns: `#`, `Host`, `ASN`, `Loss`, `Avg`, `Best`, `Worst`.

- Header style: `bold cyan`
- Hop number column: `dim`, right-justified, width 3
- Host column: min-width 18
- Metric columns: right-justified, fixed widths 7–9
- Unreachable hops (`* * *`): all cells rendered `dim`
- AS boundary hops: ASN cell styled `bold yellow`; target ASN entry styled `bold green`

### Section Rules

`Rule` with `style="cyan"`, `align="left"`. Used as full-width dividers between ISPs in country mode. Content: ISP rank, ASN, name, and allocated IP count.

### Progress Indicators

`Progress` with `SpinnerColumn` + `TextColumn`, `transient=True`. Shown during DNS resolution, MTR tracing, and iperf3 tests — erased from the terminal when the task completes.

## Conventions

### Styling Approach

- **Framework**: Rich (terminal markup)
- **Style location**: All styles are centralized in `src/netpath/display.py`; `cli.py` delegates all display work to that module
- **Style syntax**: Rich markup strings — `[bold cyan]text[/bold cyan]`, `Text("str", style="bold green")`
- **No inline styles in CLI layer**: `cli.py` calls display functions; it does not apply Rich styles directly

### Throughput Formatting (`fmt_bps` in `display.py:48`)

| Range | Format |
|-------|--------|
| ≥ 1 Gbps | `N.NN Gbps` |
| ≥ 1 Mbps | `N Mbps` |
| < 1 Mbps | `N Kbps` |
