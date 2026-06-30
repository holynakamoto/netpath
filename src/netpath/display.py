import re

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from netpath.asn import cymru_bulk_lookup_rich, normalize_asn

_IP_PAT = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')

console = Console()


# ── name helpers ─────────────────────────────────────────────────────────────

def clean_asn_name(name: str) -> str:
    """Strip Cymru short-name prefix: 'PARTNER-AS - Partner Comms' → 'Partner Comms'"""
    if ' - ' not in name:
        return name
    prefix, _, rest = name.partition(' - ')
    prefix = prefix.strip()
    # Short code: no spaces, ≤25 chars (handles PARTNER-AS, NV-ASN, Internet_Binat, Tehila-AS…)
    if ' ' not in prefix and 1 <= len(prefix) <= 25:
        return rest.strip().replace('_', ' ').strip()
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
    if ms < 20:
        return Text(s, style="bold green")
    if ms < 80:
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


def path_table(hubs: list[dict], target_asn: str):
    if _all_stars(hubs):
        console.print(
            f"  [yellow]⚠[/yellow] [dim]Path filtered — all {len(hubs)} hops dropped ICMP probes "
            f"(destination may still be reachable)[/dim]\n"
        )
        return

    # Trim trailing unreachable hops — after the last responsive hop they're just noise
    last_real = max(
        (i for i, h in enumerate(hubs) if h.get("host") not in ("???", None, "")),
        default=-1,
    )
    trailing = 0
    if last_real >= 0 and last_real < len(hubs) - 1:
        trailing = len(hubs) - last_real - 1
        hubs = hubs[:last_real + 1]

    show_p95 = console.width >= 90

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Host", min_width=18)
    table.add_column("ASN", min_width=9)
    table.add_column("Loss", justify="right", width=7)
    table.add_column("Avg", justify="right", width=9)
    table.add_column("Best", justify="right", width=9)
    table.add_column("Worst", justify="right", width=9)
    if show_p95:
        table.add_column("p95", justify="right", width=9)

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
                   Text("—", style="dim"), Text("—", style="dim")]
            if show_p95:
                row.append(Text("—", style="dim"))
            table.add_row(*row)
            prev_asn = asn
            continue

        # AS boundary: highlight the hop where we enter a new AS
        asn_text = Text(asn if asn != "AS???" else "—")
        if asn != "AS???" and asn != prev_asn and prev_asn is not None:
            asn_text.stylize("bold yellow")
            if asn == target_asn:
                asn_text.stylize("bold green")
        elif asn == target_asn:
            asn_text.stylize("green")

        row = [
            hop, host, asn_text,
            fmt_loss(loss), fmt_latency(avg), fmt_latency(best), fmt_latency(worst),
        ]
        if show_p95:
            p95 = hub.get("p95")
            row.append(fmt_latency(p95) if p95 is not None else Text("—", style="dim"))
        table.add_row(*row)
        prev_asn = asn

    console.print(table)
    if trailing:
        console.print(
            f"  [dim]  + {trailing} hop{'s' if trailing != 1 else ''} beyond "
            f"— ICMP TTL-exceeded filtered[/dim]"
        )


def as_path_summary(hubs: list[dict]):
    asns = []
    for hub in hubs:
        asn = hub.get("ASN", "")
        if asn and asn != "AS???" and (not asns or asns[-1] != asn):
            asns.append(asn)

    if not asns:
        return

    parts = []
    for i, asn in enumerate(asns):
        if i == 0:
            parts.append(f"[dim]{asn}[/dim]")
        elif i == len(asns) - 1:
            parts.append(f"[bold green]{asn}[/bold green]")
        else:
            parts.append(f"[yellow]{asn}[/yellow]")

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
        console.print()

    if incomplete:
        console.print("[dim]incomplete paths[/dim]")
        for ri, r in enumerate(incomplete):
            connector = "└─" if ri == len(incomplete) - 1 else "├─"
            line = Text()
            line.append(f"  {connector}   {r['asn']:<10}  {_trim(r['name']):<26}  ", style="dim")
            line.append("⚠ ", style="yellow")
            line.append("incomplete", style="dim")
            console.print(line)
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

    severity_styles = {"ok": "bold green", "warning": "bold yellow", "critical": "bold red"}
    border_colors   = {"ok": "green",      "warning": "yellow",       "critical": "red"}
    style  = severity_styles.get(severity, "bold green")
    border = border_colors.get(severity, "green")

    lines = [f"  [{style}]{label}[/{style}]", f"  {detail}"]
    if signals:
        lines.append("")
        for sig in signals:
            lines.append(f"  • {sig}")

    console.print(
        Panel("\n".join(lines), title="[bold]Diagnosis[/bold]",
              border_style=border, expand=False)
    )
    console.print()


def error(msg: str):
    console.print(f"  [red]✗[/red] {msg}\n")


def warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}\n")
