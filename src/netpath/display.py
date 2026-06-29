import re

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()


# ── name helpers ─────────────────────────────────────────────────────────────

def clean_asn_name(name: str) -> str:
    """Strip Cymru short-name prefix: 'PARTNER-AS - Partner Communications Ltd.' → 'Partner Communications Ltd.'"""
    if ' - ' not in name:
        return name
    prefix, _, rest = name.partition(' - ')
    if re.match(r'^[A-Z0-9][A-Z0-9_\-]*$', prefix.strip()):
        return rest.strip().replace('_', ' ').strip()
    return name


# ── formatting helpers ────────────────────────────────────────────────────────

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
            table.add_row(hop, Text("* * *", style="dim"), Text("—", style="dim"),
                          Text("—", style="dim"), Text("—", style="dim"),
                          Text("—", style="dim"), Text("—", style="dim"))
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

        table.add_row(
            hop,
            host,
            asn_text,
            fmt_loss(loss),
            fmt_latency(avg),
            fmt_latency(best),
            fmt_latency(worst),
        )
        prev_asn = asn

    console.print(table)


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
    """Show RUM panel standalone when iperf3 was skipped."""
    dr = rum.get("date_range", "7d")
    lines = [
        f"  [bold cyan]↓ Download:[/bold cyan]  {_fmt_opt(rum.get('dl_mbps'), 'Mbps')}",
        f"  [bold green]↑ Upload:[/bold green]    {_fmt_opt(rum.get('ul_mbps'), 'Mbps')}",
        f"  [dim]Latency idle:    {_fmt_opt(rum.get('latency_idle'), 'ms')}[/dim]",
        f"  [dim]Latency loaded:  {_fmt_opt(rum.get('latency_loaded'), 'ms')}[/dim]",
        f"  [dim]Jitter:          {_fmt_opt(rum.get('jitter'), 'ms')}[/dim]",
    ]
    if rum.get("packet_loss") is not None:
        lines.append(f"  [dim]Packet loss:     {rum['packet_loss']:.2f}%[/dim]")

    console.print(
        Panel("\n".join(lines),
              title=f"[bold]RUM · Cloudflare Radar · {asn} ({dr})[/bold]",
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


def error(msg: str):
    console.print(f"  [red]✗[/red] {msg}\n")


def warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}\n")
