import re

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from netpath.asn import cymru_bulk_lookup_rich, normalize_asn
from netpath import ixp as ixp_mod

_IP_PAT = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')

LATENCY_GREEN_MS = 20
LATENCY_YELLOW_MS = 80

console = Console()


# ── name helpers ─────────────────────────────────────────────────────────────

def clean_asn_name(name: str) -> str:
    """Strip Cymru short-name prefix: 'PARTNER-AS - Partner Comms' → 'Partner Comms'"""
    if ' - ' not in name:
        return name
    prefix, _, rest = name.partition(' - ')
    prefix = prefix.strip()
    rest = rest.strip()
    # Exact duplicate: "Dimension Data - Dimension Data" → "Dimension Data"
    if prefix == rest:
        return rest.replace('_', ' ').strip()
    # Short code: no spaces, ≤25 chars (handles PARTNER-AS, NV-ASN, Internet_Binat, Tehila-AS…)
    if ' ' not in prefix and 1 <= len(prefix) <= 25:
        return rest.replace('_', ' ').strip()
    return name


# ── formatting helpers ────────────────────────────────────────────────────────

def fmt_country_latency(ms: float) -> Text:
    s = f"{ms:.1f} ms"
    if ms < 120:
        return Text(s, style="bold green")
    if ms < 200:
        return Text(s, style="yellow")
    return Text(s, style="bold red")


def fmt_latency(ms: float) -> Text:
    s = f"{ms:.1f} ms"
    if ms <= 0:
        return Text("—", style="dim")
    if ms < LATENCY_GREEN_MS:
        return Text(s, style="bold green")
    if ms < LATENCY_YELLOW_MS:
        return Text(s, style="yellow")
    return Text(s, style="bold red")


def fmt_loss(pct: float) -> Text:
    s = f"{pct:.1f}%"
    if pct == 0:
        return Text(s, style="green")
    if pct < 5:
        return Text(s, style="yellow")
    return Text(s, style="bold red")


def fmt_bps(bps: float) -> str:
    if bps >= 1e9:
        return f"{bps / 1e9:.2f} Gbps"
    if bps >= 1e6:
        return f"{bps / 1e6:.0f} Mbps"
    return f"{bps / 1e3:.0f} Kbps"


# ── sections ─────────────────────────────────────────────────────────────────

def header(version: str = "0.1.0"):
    console.print()
    console.print(
        Panel(
            "[bold cyan]netpath[/bold cyan]  "
            "[dim]network path analyzer — throughput · latency · packet loss · AS hops[/dim]",
            border_style="cyan",
            expand=False,
            padding=(0, 2),
        )
    )
    console.print()


def server_heading(server: dict):
    host = server.get("HOST", "?")
    site = server.get("SITE", "")
    country = server.get("COUNTRY", "")
    asn = server.get("asn", "")
    port = server.get("port", 5201)
    meta = "  ".join(filter(None, [asn, site, country, f":{port}"]))
    console.print(
        Panel(
            f"[bold]{host}[/bold]  [dim]{meta}[/dim]",
            border_style="blue",
            expand=False,
            padding=(0, 1),
        )
    )
    console.print()


def isp_section(rank: int, asn: str, name: str, addresses: int = 0, prefix_count: int = 0):
    """Full-width section rule for each ISP in country mode."""
    name_clean = clean_asn_name(name)
    addrs = f"  [dim]{addresses:,} IPs[/dim]" if addresses else ""
    console.print()
    console.rule(
        f" [bold cyan]#{rank}[/bold cyan]  [bold]{asn}[/bold]  {name_clean}{addrs} ",
        style="cyan",
        align="left",
    )
    console.print()


def _all_stars(hubs: list[dict]) -> bool:
    return bool(hubs) and all(h.get("host") in ("???", None) for h in hubs)


def _trim_trailing(hubs: list[dict]) -> tuple[list[dict], int]:
    """Remove trailing unreachable hops. Returns (trimmed_hubs, count_removed)."""
    last_real = max(
        (i for i, h in enumerate(hubs) if h.get("host") not in ("???", None, "")),
        default=-1,
    )
    if last_real >= 0 and last_real < len(hubs) - 1:
        return hubs[:last_real + 1], len(hubs) - last_real - 1
    return hubs, 0


def _build_hub_table(hubs: list[dict], target_asn: str, show_p95: bool = True) -> Table:
    """Build and return a Rich Table for a pre-trimmed hub list. Adds a Type column."""
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Host", min_width=18)
    table.add_column("ASN", min_width=20)
    table.add_column("Type", width=8)
    table.add_column("Loss", justify="right", width=7)
    table.add_column("Avg", justify="right", width=9)
    table.add_column("Best", justify="right", width=9)
    table.add_column("Worst", justify="right", width=9)
    if show_p95:
        table.add_column("p95", justify="right", width=9)

    target_norm = normalize_asn(target_asn) if target_asn else None

    prev_asn = None
    for hub in hubs:
        hop = str(hub.get("count", "?"))
        host = hub.get("host", "???")
        asn = hub.get("ASN", "AS???")
        loss = hub.get("Loss%", 0.0)
        avg = hub.get("Avg", 0.0)
        best = hub.get("Best", 0.0)
        worst = hub.get("Wrst", 0.0)

        if host in ("???", "", None):
            row = [hop, Text("* * *", style="dim"), Text("—", style="dim"),
                   Text("—", style="dim"), Text("—", style="dim"),
                   Text("—", style="dim"), Text("—", style="dim"), Text("—", style="dim")]
            if show_p95:
                row.append(Text("—", style="dim"))
            table.add_row(*row)
            prev_asn = asn
            continue

        # AS boundary: highlight the hop where we enter a new AS
        asn_name_val = hub.get("asn_name", "")
        if asn == "AS???":
            asn_display = "—"
        elif asn_name_val:
            asn_display = f"{asn} ({asn_name_val[:20]})"
        else:
            asn_display = asn
        asn_text = Text(asn_display)
        hub_asn_norm = normalize_asn(asn) if asn and asn != "AS???" else None
        is_dest = target_norm and hub_asn_norm == target_norm
        if asn != "AS???" and asn != prev_asn and prev_asn is not None:
            asn_text.stylize("bold yellow")
            if is_dest:
                asn_text.stylize("bold green")
        elif is_dest:
            asn_text.stylize("green")

        # Hop type classification
        if is_dest:
            type_text = Text("dest", style="bold green")
        else:
            hop_type = ixp_mod.classify_hop(host)
            if hop_type == "ixp":
                type_text = Text("IXP", style="bold blue")
            else:
                type_text = Text("transit", style="dim")

        row = [
            hop, host, asn_text, type_text,
            fmt_loss(loss), fmt_latency(avg), fmt_latency(best), fmt_latency(worst),
        ]
        if show_p95:
            p95 = hub.get("p95")
            row.append(fmt_latency(p95) if p95 is not None else Text("—", style="dim"))
        table.add_row(*row)
        prev_asn = asn

    return table


def path_table(hubs: list[dict], target_asn: str):
    if _all_stars(hubs):
        console.print(
            f"  [yellow]⚠[/yellow] [dim]Path filtered — all {len(hubs)} hops dropped ICMP probes "
            f"(destination may still be reachable)[/dim]\n"
        )
        return

    trimmed, trailing = _trim_trailing(hubs)
    show_p95 = console.width >= 90
    table = _build_hub_table(trimmed, target_asn, show_p95=show_p95)
    console.print(table)
    if trailing:
        console.print(
            f"  [dim]  + {trailing} hop{'s' if trailing != 1 else ''} beyond "
            f"— ICMP TTL-exceeded filtered[/dim]"
        )


def dual_stack_columns(hubs_v4: list[dict], hubs_v6: list[dict] | None, target_asn: str):
    """Display IPv4 and IPv6 path tables side-by-side using Rich Columns."""
    trimmed_v4, _ = _trim_trailing(hubs_v4) if hubs_v4 else ([], 0)
    v4_table = _build_hub_table(trimmed_v4, target_asn, show_p95=False)
    v4_panel = Panel(v4_table, title="[bold]IPv4 Path[/bold]", border_style="blue", expand=False)

    if hubs_v6:
        trimmed_v6, _ = _trim_trailing(hubs_v6)
        v6_table = _build_hub_table(trimmed_v6, target_asn, show_p95=False)
        v6_panel = Panel(v6_table, title="[bold]IPv6 Path[/bold]", border_style="cyan", expand=False)
    else:
        v6_panel = Panel(
            "  [dim]unavailable[/dim]",
            title="[bold]IPv6 Path[/bold]",
            border_style="dim",
            expand=False,
        )

    console.print(Columns([v4_panel, v6_panel], equal=False, expand=False))
    console.print()


def as_path_summary(hubs: list[dict]):
    path: list[tuple[str, str]] = []  # (bare_asn, display_label)
    for hub in hubs:
        asn = hub.get("ASN", "")
        if not asn or asn == "AS???":
            continue
        name = hub.get("asn_name", "")
        label = f"{asn} ({name})" if name else asn
        if not path or path[-1][0] != asn:
            path.append((asn, label))

    if not path:
        return

    parts = []
    for i, (_, label) in enumerate(path):
        if i == 0:
            parts.append(f"[dim]{label}[/dim]")
        elif i == len(path) - 1:
            parts.append(f"[bold green]{label}[/bold green]")
        else:
            parts.append(f"[yellow]{label}[/yellow]")

    console.print("  [dim]AS path:[/dim] " + " [dim]→[/dim] ".join(parts))
    console.print()


def _fmt_opt(val: float | None, unit: str) -> str:
    return f"{val:.0f} {unit}" if val is not None else "—"


def throughput_and_rum(upload: dict, download: dict, rum: dict | None = None,
                       server: str = "speed.cloudflare.com"):
    up   = fmt_bps(upload.get("bps", 0))
    dn   = fmt_bps(download.get("recv_bps", download.get("bps", 0)))
    retx = upload.get("retransmits") or 0
    ttfb = download.get("ttfb_ms")

    synth_lines = [
        f"  [bold green]↑ Upload:[/bold green]   {up}",
        f"  [bold cyan]↓ Download:[/bold cyan] {dn}",
    ]
    if ttfb is not None:
        synth_lines.append(f"  [dim]TTFB: {ttfb:.0f} ms[/dim]")
    if retx:
        synth_lines.append(f"  [dim]retransmits: {retx}[/dim]")

    synth_panel = Panel(
        "\n".join(synth_lines),
        title=f"[bold]Throughput · {server}[/bold]",
        border_style="blue",
        expand=False,
    )

    if rum:
        dr = rum.get("date_range", "7d")
        rum_lines = [
            f"  [bold cyan]↓[/bold cyan]  {_fmt_opt(rum.get('dl_mbps'), 'Mbps')}",
            f"  [bold green]↑[/bold green]  {_fmt_opt(rum.get('ul_mbps'), 'Mbps')}",
            f"  [dim]Latency idle:   {_fmt_opt(rum.get('latency_idle'), 'ms')}[/dim]",
            f"  [dim]Latency loaded: {_fmt_opt(rum.get('latency_loaded'), 'ms')}[/dim]",
            f"  [dim]Jitter:         {_fmt_opt(rum.get('jitter'), 'ms')}[/dim]",
        ]
        if rum.get("packet_loss") is not None:
            rum_lines.append(f"  [dim]Packet loss:    {rum['packet_loss']:.2f}%[/dim]")

        rum_panel = Panel(
            "\n".join(rum_lines),
            title=f"[bold]RUM · Cloudflare Radar ({dr})[/bold]",
            border_style="magenta",
            expand=False,
        )
        console.print(Columns([synth_panel, rum_panel], equal=False, expand=False))
    else:
        console.print(synth_panel)

    console.print()


def rum_only_panel(rum: dict, asn: str):
    """Show compact RUM panel (3 lines) when throughput test was skipped."""
    dr = rum.get("date_range", "7d")
    dl = _fmt_opt(rum.get("dl_mbps"), "Mbps")
    ul = _fmt_opt(rum.get("ul_mbps"), "Mbps")
    idle = _fmt_opt(rum.get("latency_idle"), "ms")
    loaded = _fmt_opt(rum.get("latency_loaded"), "ms")

    lines = [
        f"  [bold cyan]↓[/bold cyan] {dl}   [bold green]↑[/bold green] {ul}",
        f"  [dim]idle {idle}   loaded {loaded}[/dim]",
    ]
    if rum.get("packet_loss") is not None:
        lines.append(f"  [dim]loss {rum['packet_loss']:.2f}%[/dim]")

    console.print(
        Panel("\n".join(lines),
              title=f"[bold]Cloudflare Radar · {asn} ({dr})[/bold]",
              border_style="magenta", expand=False)
    )
    console.print()


def baseline_panel(upload: dict, download: dict):
    """Your own connection baseline — shown once before per-ISP RUM comparisons."""
    up  = fmt_bps(upload.get("bps", 0))
    dn  = fmt_bps(download.get("recv_bps", download.get("bps", 0)))
    ttfb = download.get("ttfb_ms")
    lines = [
        f"  [bold green]↑ Upload:[/bold green]   {up}",
        f"  [bold cyan]↓ Download:[/bold cyan] {dn}",
    ]
    if ttfb is not None:
        lines.append(f"  [dim]TTFB to Cloudflare: {ttfb:.0f} ms[/dim]")
    console.print(
        Panel("\n".join(lines),
              title="[bold]Your baseline · speed.cloudflare.com[/bold]",
              border_style="blue", expand=False)
    )
    console.print()


def _render_globalping_subrow(r: dict, is_last_in_group: bool) -> None:
    """Print optional Globalping RTT + outbound AS-path line beneath an ISP summary row."""
    gp = r.get("globalping", {})
    if not gp:
        return
    rtt = gp.get("ping_rtt")
    path = gp.get("outbound_as_path", [])
    parts = []
    if rtt:
        parts.append(f"RTT {rtt['avg']:.1f} ms avg ({rtt['min']:.1f}–{rtt['max']:.1f})")
    if path:
        parts.append("outbound: " + "→".join(path[:6]))
    if not parts:
        return
    cont = "   " if is_last_in_group else "  │"
    console.print(f"  {cont}         [dim][Globalping] {', '.join(parts)}[/dim]")


def country_summary(code: str, results: list[dict]):
    """Tree summary grouped by transit entry point with color-coded latency."""
    if not results:
        return

    complete = [r for r in results if r.get("path_complete") and r.get("verified_rtt_ms") is not None]
    incomplete = [r for r in results if not r.get("path_complete") or r.get("verified_rtt_ms") is None]

    star_asn: str | None = None
    if complete:
        star_asn = min(complete, key=lambda r: r["verified_rtt_ms"])["asn"]

    # Group complete rows by entry_transit_asn; sort each group by RTT
    groups: dict[str | None, list[dict]] = {}
    for r in complete:
        groups.setdefault(r.get("entry_transit_asn"), []).append(r)
    sorted_keys = sorted(groups, key=lambda k: min(r["verified_rtt_ms"] for r in groups[k]))
    for key in sorted_keys:
        groups[key].sort(key=lambda r: r["verified_rtt_ms"])

    # Collect one IP per transit ASN from hub lists for Cymru name lookup
    transit_ips: dict[str, str] = {}
    for key in sorted_keys:
        if key is None:
            continue
        for r in groups[key]:
            for hub in r.get("hubs", []):
                raw_asn = hub.get("ASN", "")
                if raw_asn and normalize_asn(raw_asn) == key:
                    host = hub.get("host", "")
                    if host and host not in ("???", None, "") and _IP_PAT.match(host):
                        transit_ips[key] = host
                        break
            if key in transit_ips:
                break

    # Batch Cymru lookup for transit org names (one TCP connection)
    transit_names: dict[str, str] = {}
    if transit_ips:
        try:
            lookup = cymru_bulk_lookup_rich(list(transit_ips.values()))
            for asn_key, ip in transit_ips.items():
                if ip in lookup:
                    n = lookup[ip].get("name", "")
                    if n:
                        transit_names[asn_key] = clean_asn_name(n)
        except Exception:
            pass

    def _transit_label(key: str | None) -> str:
        if key is None:
            return "direct"
        name = transit_names.get(key)
        return f"{key} · {name}" if name else key

    def _trim(name: str, width: int = 26) -> str:
        return name[:width - 1] + "…" if len(name) > width else name

    console.print()
    console.rule(f" {code} summary ", style="bold cyan")
    console.print()

    for key in sorted_keys:
        rows = groups[key]
        console.print(f"[bold]{_transit_label(key)}[/bold]")
        for ri, r in enumerate(rows):
            connector = "└─" if ri == len(rows) - 1 else "├─"
            star = "★ " if r["asn"] == star_asn else "  "
            line = Text()
            line.append(f"  {connector} {star}{r['asn']:<10}  {_trim(r['name']):<26}  ")
            line.append_text(fmt_country_latency(r["verified_rtt_ms"]))
            console.print(line)
            _render_globalping_subrow(r, ri == len(rows) - 1)
        console.print()

    if incomplete:
        console.print("[dim]incomplete paths[/dim]")
        for ri, r in enumerate(incomplete):
            connector = "└─" if ri == len(incomplete) - 1 else "├─"
            line = Text()
            line.append(f"  {connector}   {r['asn']:<10}  {_trim(r['name']):<26}  ", style="dim")
            line.append("⚠ ", style="yellow")
            stall_asn = r.get("entry_transit_asn")
            stall_hop = r.get("stall_hop")
            last_rtt = r.get("last_rtt_ms")
            if stall_asn or stall_hop is not None or last_rtt is not None:
                parts = []
                if stall_asn:
                    parts.append(stall_asn)
                if stall_hop is not None:
                    parts.append(f"hop {stall_hop}")
                if last_rtt is not None:
                    parts.append(f"{last_rtt:.1f} ms")
                line.append(f"stalled at {', '.join(parts)}", style="dim")
            else:
                line.append("incomplete", style="dim")
            console.print(line)
            _render_globalping_subrow(r, ri == len(incomplete) - 1)
        console.print()

    if sorted_keys:
        best_key = sorted_keys[0]
        best_rtt = groups[best_key][0]["verified_rtt_ms"]
        console.print(f"  [dim]Fastest entry transit: [bold]{_transit_label(best_key)}[/bold] — {best_rtt:.1f} ms[/dim]")
        console.print()


def bufferbloat_line(idle_ms: float | None, loaded_ms: float | None) -> None:
    idle_str = f"{idle_ms:.1f} ms" if idle_ms is not None else "—"
    if loaded_ms is None:
        console.print(
            f"  [dim]Bufferbloat:[/dim]  idle {idle_str}  loaded [dim]unavailable[/dim]"
        )
        console.print()
        return
    loaded_str = f"{loaded_ms:.1f} ms"
    delta = loaded_ms - (idle_ms if idle_ms is not None else 0.0)
    delta_str = f"{delta:+.1f} ms"
    if delta < 5:
        delta_markup = f"[dim]{delta_str}[/dim]"
        label_markup = "[dim]None[/dim]"
    elif delta <= 30:
        delta_markup = f"[yellow]{delta_str}[/yellow]"
        label_markup = "[yellow]Moderate[/yellow]"
    else:
        delta_markup = f"[bold red]{delta_str}[/bold red]"
        label_markup = "[bold red]Severe[/bold red]"
    console.print(
        f"  [dim]Bufferbloat:[/dim]  idle {idle_str}  loaded {loaded_str}  {delta_markup}  {label_markup}"
    )
    console.print()


def verdict_panel(verdict: dict) -> None:
    severity = verdict.get("severity", "ok")
    label = verdict.get("verdict", "Healthy")
    detail = verdict.get("detail", "")
    signals = verdict.get("signals", [])
    partial = verdict.get("partial_results", False)
    probe_errors = verdict.get("probe_errors", {})

    severity_styles = {"ok": "bold green", "warning": "bold yellow", "critical": "bold red"}
    border_colors   = {"ok": "green",      "warning": "yellow",       "critical": "red"}
    style  = severity_styles.get(severity, "bold green")
    border = border_colors.get(severity, "green")

    if partial and probe_errors:
        failed = ", ".join(probe_errors.keys())
        label_text = f"{label} (partial results: {failed})"
    elif partial:
        label_text = f"{label} (partial results)"
    else:
        label_text = label

    lines = [f"  [{style}]{label_text}[/{style}]", f"  {detail}"]
    if signals:
        lines.append("")
        for sig in signals:
            lines.append(f"  • {sig['detail']}")

    console.print(
        Panel("\n".join(lines), title="[bold]Diagnosis[/bold]",
              border_style=border, expand=False)
    )
    console.print()


def error(msg: str):
    console.print(f"  [red]✗[/red] {msg}\n")


def warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}\n")
