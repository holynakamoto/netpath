from __future__ import annotations

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


def _truncation_note():
    console.print(
        "  [yellow]⚠[/yellow] [dim]Path truncated — the trace timed out before completing; "
        "showing the hops collected so far[/dim]"
    )


def path_table(hubs: list[dict], target_asn: str, truncated: bool = False):
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
    if truncated:
        _truncation_note()


def dual_stack_columns(hubs_v4: list[dict], hubs_v6: list[dict] | None, target_asn: str,
                       truncated: bool = False):
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
    if truncated:
        _truncation_note()
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


def edge_metrics(result: dict):
    """Show compact optional DNS, HTTPS edge, PMTU, and geo sanity metrics."""
    lines: list[str] = []
    dns = result.get("dns") or {}
    if dns and not dns.get("error") and dns.get("lookup_ms") is not None:
        answers = dns.get("answers") or []
        families = "/".join(dict.fromkeys(a.get("type", "?") for a in answers))
        ttl_values = [a.get("ttl") for a in answers if a.get("ttl") is not None]
        ttl = f", ttl {min(ttl_values)}s" if ttl_values else ""
        resolver = ", ".join((dns.get("resolver_ips") or [])[:2])
        resolver = f", resolver {resolver}" if resolver else ""
        lines.append(f"DNS {dns.get('lookup_ms'):.1f} ms ({families or 'no answers'}{ttl}{resolver})")

    edge = result.get("http_edge") or {}
    if edge and not edge.get("error"):
        parts = []
        if edge.get("status_code") is not None:
            parts.append(f"HTTP {edge['status_code']}")
        if edge.get("ttfb_ms") is not None:
            parts.append(f"TTFB {edge['ttfb_ms']:.0f} ms")
        if edge.get("redirect_count"):
            parts.append(f"{edge['redirect_count']} redirect{'s' if edge['redirect_count'] != 1 else ''}")
        cert = edge.get("certificate") or {}
        if cert.get("days_until_expiry") is not None:
            parts.append(f"cert {cert['days_until_expiry']}d")
        if parts:
            lines.append("Edge " + ", ".join(parts))

    pmtu = result.get("pmtu") or {}
    if pmtu.get("effective_mtu_bytes") is not None:
        label = "PMTU black-hole" if pmtu.get("blackhole") else "PMTU"
        lines.append(f"{label} effective MTU {pmtu['effective_mtu_bytes']} bytes")

    geo = result.get("geo_path") or {}
    countries = geo.get("country_hops") or []
    if countries:
        geo_line = "Geo " + " → ".join(countries[:6])
        if geo.get("total_geodesic_km") is not None:
            geo_line += f" ({geo['total_geodesic_km']:.0f} km)"
        if geo.get("warnings"):
            geo_line += " [yellow]⚠[/yellow]"
        lines.append(geo_line)

    if not lines:
        return
    console.print(Panel("\n".join(f"  [dim]{line}[/dim]" for line in lines),
                        title="[bold]Additional path metrics[/bold]",
                        border_style="cyan", expand=False))
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


def baseline_panel(upload: dict | None, download: dict | None,
                   errors: dict | None = None):
    """Your own connection baseline — shown once before per-ISP RUM comparisons.

    Either direction may be None when it failed; the panel then shows the
    reading that succeeded and marks the failed direction.
    """
    errors = errors or {}
    lines = []
    if upload is not None:
        lines.append(f"  [bold green]↑ Upload:[/bold green]   {fmt_bps(upload.get('bps', 0))}")
    elif "upload" in errors:
        lines.append("  [bold green]↑ Upload:[/bold green]   [yellow]failed[/yellow]")
    if download is not None:
        dn = fmt_bps(download.get("recv_bps", download.get("bps", 0)))
        lines.append(f"  [bold cyan]↓ Download:[/bold cyan] {dn}")
    elif "download" in errors:
        lines.append("  [bold cyan]↓ Download:[/bold cyan] [yellow]failed[/yellow]")
    if download is not None and download.get("ttfb_ms") is not None:
        lines.append(f"  [dim]TTFB to Cloudflare: {download['ttfb_ms']:.0f} ms[/dim]")
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
    loss = gp.get("ping_loss_pct")
    jitter = gp.get("ping_jitter_ms")
    path = gp.get("outbound_as_path", [])
    parts = []
    if rtt:
        parts.append(f"RTT {rtt['avg']:.1f} ms avg ({rtt['min']:.1f}–{rtt['max']:.1f})")
    if loss is not None:
        parts.append(f"loss {loss:.1f}%")
    if jitter is not None:
        parts.append(f"jitter {jitter:.1f} ms")
    if path:
        parts.append("outbound: " + " → ".join(path[:6]))
    if (loss is not None or jitter is not None) and (r.get("verdict") or {}).get("verdict"):
        parts.append(f"verdict {r['verdict']['verdict']} (near-target)")
    if not parts:
        return
    cont = "   " if is_last_in_group else "  │"
    console.print(f"  {cont}         [dim][Globalping] {', '.join(parts)}[/dim]")


def _rum_summary_str(rum: dict) -> str:
    """Compact one-line Radar figures for a country-summary subrow."""
    parts = [
        f"↓ {_fmt_opt(rum.get('dl_mbps'), 'Mbps')}",
        f"↑ {_fmt_opt(rum.get('ul_mbps'), 'Mbps')}",
        f"idle {_fmt_opt(rum.get('latency_idle'), 'ms')}",
    ]
    if rum.get("packet_loss") is not None:
        parts.append(f"loss {rum['packet_loss']:.2f}%")
    return "Radar: " + "  ".join(parts)


def _render_rum_subrow(r: dict, is_last_in_group: bool) -> None:
    """Print an optional Radar figures line beneath an ISP summary row."""
    rum = r.get("rum")
    if not rum:
        return
    cont = "   " if is_last_in_group else "  │"
    console.print(f"  {cont}         [magenta]{_rum_summary_str(rum)}[/magenta]")


def country_summary(code: str, results: list[dict]):
    """Tree summary grouped by transit entry point with color-coded latency."""
    if not results:
        return

    no_coverage = [r for r in results if r.get("skip_reason")]
    remote_only = [r for r in results if r.get("remote_only")]
    measured = [r for r in results if not r.get("skip_reason") and not r.get("remote_only")]

    complete = [r for r in measured if r.get("path_complete") and r.get("verified_rtt_ms") is not None]
    incomplete = [r for r in measured if not r.get("path_complete") or r.get("verified_rtt_ms") is None]

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

    if remote_only:
        console.print("[dim]remote-only — measured from inside the ISP via Globalping; no local trace ran[/dim]")
        for ri, r in enumerate(remote_only):
            connector = "└─" if ri == len(remote_only) - 1 else "├─"
            line = Text()
            line.append(f"  {connector}   {r['asn']:<10}  {_trim(r['name']):<26}  ", style="dim")
            line.append("remote-only", style="cyan")
            console.print(line)
            _render_rum_subrow(r, ri == len(remote_only) - 1)
            _render_globalping_subrow(r, ri == len(remote_only) - 1)
        console.print()

    if no_coverage:
        console.print("[dim]no coverage — skipped, no live target[/dim]")
        for ri, r in enumerate(no_coverage):
            connector = "└─" if ri == len(no_coverage) - 1 else "├─"
            line = Text()
            line.append(f"  {connector}   {r['asn']:<10}  {_trim(r['name']):<26}  ", style="dim")
            line.append(r.get("skip_reason", "no live target"), style="dim")
            console.print(line)
            _render_rum_subrow(r, ri == len(no_coverage) - 1)
        console.print()

    if sorted_keys:
        best_key = sorted_keys[0]
        best_rtt = groups[best_key][0]["verified_rtt_ms"]
        console.print(f"  [dim]Fastest entry transit: [bold]{_transit_label(best_key)}[/bold] — {best_rtt:.1f} ms[/dim]")
        console.print()


def aspath_report(source_asn: str, dest_asn: str, target_ip: str, result: dict) -> None:
    """Render ranked Globalping AS-path candidates for source_asn -> dest_asn."""
    candidates = result.get("candidates") or []
    ping = result.get("ping_rtt") or {}
    loss = result.get("ping_loss_pct")
    jitter = result.get("ping_jitter_ms")

    console.print()
    console.rule(f" AS path {source_asn} → {dest_asn} ", style="bold cyan")
    target_geo = (result.get("target") or {}).get("geo") or {}
    target_city = ", ".join(
        p for p in (target_geo.get("city"), target_geo.get("country_code")) if p
    )
    target_suffix = f"  [dim]({target_city})[/dim]" if target_city else ""
    console.print(f"  [dim]Target:[/dim] {target_ip}{target_suffix}")
    metrics = []
    if ping:
        metrics.append(f"RTT {ping['avg']:.1f} ms avg ({ping['min']:.1f}-{ping['max']:.1f})")
    if loss is not None:
        metrics.append(f"loss {loss:.1f}%")
    if jitter is not None:
        metrics.append(f"jitter {jitter:.1f} ms")
    if metrics:
        console.print(f"  [dim]Probe aggregate:[/dim] {', '.join(metrics)}")
    console.print()

    if not candidates:
        warn("No AS path could be derived from the Globalping MTR results.")
        return

    best = result.get("optimal_path")
    if best:
        console.print(
            "  [bold green]Optimal measured path:[/bold green] "
            + " [dim]→[/dim] ".join(best["path"])
        )
        console.print(
            "  [dim]Ranking uses complete paths first, then MTR RTT when available, "
            "then AS-hop count. BGP policy control is outside netpath.[/dim]\n"
        )
    else:
        console.print("  [bold yellow]Incomplete measurement[/bold yellow]")
        if result.get("path_note"):
            console.print(f"  [dim]{result['path_note']}[/dim]")
        console.print()

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("RTT", justify="right", width=10)
    table.add_column("Status", justify="center", width=10)
    table.add_column("AS hops", justify="right", width=8)
    table.add_column("Probe", min_width=18)
    table.add_column("Path", min_width=32)
    table.add_column("Approx. cities", min_width=20)

    def _city_sequence(candidate: dict) -> str:
        cities: list[str] = []
        source_label = (candidate.get("path") or [""])[0]
        for idx, point in enumerate(candidate.get("geo_points", [])):
            # Starlink and some other networks geolocate their internal public
            # hops to registration/HQ locations. Keep the probe's real city,
            # but avoid implying same-AS internal hops are physical detours.
            if idx > 0 and point.get("label") == source_label:
                continue
            city = point.get("city")
            cc = point.get("country_code")
            label = ", ".join(p for p in (city, cc) if p)
            if label and (not cities or cities[-1] != label):
                cities.append(label)
        if target_city and (not cities or cities[-1] != target_city):
            cities.append(target_city)
        if not cities:
            return "—"
        if len(cities) > 5:
            cities = cities[:4] + [cities[-1]]
        return " → ".join(cities)

    for idx, candidate in enumerate(candidates, 1):
        rtt = candidate.get("rtt_ms")
        if rtt is not None:
            rtt_text = fmt_latency(rtt)
        elif candidate.get("last_responsive_rtt_ms") is not None:
            rtt_text = Text(f"last {candidate['last_responsive_rtt_ms']:.1f}", style="dim")
        else:
            rtt_text = Text("—", style="dim")
        table.add_row(
            str(idx),
            rtt_text,
            Text("complete", style="green") if candidate.get("reaches_target") else Text("partial", style="yellow"),
            str(candidate.get("as_hops", len(candidate.get("path", [])))),
            candidate.get("probe", "Globalping probe"),
            " → ".join(candidate.get("path", [])),
            _city_sequence(candidate),
        )
    console.print(table)
    console.print()


def target_report(asn: str, info: dict) -> None:
    """Render target discovery metadata."""
    confidence = info.get("confidence", "unknown")
    styles = {
        "high": "bold green",
        "medium": "yellow",
        "low": "bold red",
        "user": "cyan",
    }
    style = styles.get(confidence, "dim")
    lines = [
        f"  [bold]{info.get('ip', '—')}[/bold]",
        f"  [dim]Source:[/dim] {info.get('origin', 'unknown')}",
        f"  [dim]Confidence:[/dim] [{style}]{confidence}[/{style}]",
    ]
    if info.get("prefix"):
        lines.append(f"  [dim]Prefix:[/dim] {info['prefix']}")
    geo = info.get("geo") or {}
    city = ", ".join(p for p in (geo.get("city"), geo.get("region"), geo.get("country")) if p)
    if city:
        lines.append(f"  [dim]Location:[/dim] {city}")
    if geo.get("as") or geo.get("org"):
        lines.append(f"  [dim]Geo ASN:[/dim] {geo.get('as') or geo.get('org')}")
    if info.get("port"):
        port_line = f"  [dim]Validation:[/dim] TCP/{info['port']}"
        if info.get("tcp_status"):
            port_line += f" {info['tcp_status']}"
        lines.append(port_line)
    if info.get("reason"):
        lines.extend(["", f"  {info['reason']}"])

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold]Target · {asn}[/bold]",
            border_style="blue",
            expand=False,
        )
    )
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


def operator_answer(answer: dict) -> bool:
    severity = answer.get("severity", "ok")
    if severity not in {"warning", "critical"}:
        return False

    severity_styles = {"warning": "bold yellow", "critical": "bold red"}
    border_colors = {"warning": "yellow", "critical": "red"}
    style = severity_styles.get(severity, "bold yellow")
    border = border_colors.get(severity, "yellow")
    culprit = answer.get("likely_culprit") or answer.get("culprit_asn") or answer.get("culprit_scope") or "unknown"
    scope = answer.get("culprit_scope")
    culprit_note = f" ({scope})" if scope and scope not in {culprit, "none"} else ""

    lines = [
        f"  [{style}]{answer.get('verdict', 'Warning')}[/{style}]",
        f"  [dim]Likely culprit:[/dim] {culprit}{culprit_note}",
        f"  [dim]Confidence:[/dim] {answer.get('confidence', 'unknown')}",
    ]
    evidence = [item for item in answer.get("evidence", []) if item]
    if evidence:
        lines.append("  [dim]Key evidence:[/dim]")
        for item in evidence[:3]:
            lines.append(f"    • {item}")
    recommendation = answer.get("recommendation")
    if recommendation:
        lines.append(f"  [dim]Next action:[/dim] {recommendation}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold]Operator answer[/bold]",
            border_style=border,
            expand=False,
        )
    )
    console.print()
    return True


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

    lines = [f"  [{style}]{label_text}[/{style}]"]
    if detail:
        lines.append(f"  {detail}")
    extra_signals = [sig for sig in signals if sig.get("detail") != detail]
    if extra_signals:
        lines.append("")
        for sig in extra_signals:
            lines.append(f"  • {sig['detail']}")

    console.print(
        Panel("\n".join(lines), title="[bold]Diagnosis[/bold]",
              border_style=border, expand=False)
    )
    console.print()


def explain_report(report: dict) -> None:
    severity = report.get("severity", "ok")
    severity_styles = {"ok": "bold green", "warning": "bold yellow", "critical": "bold red"}
    border_colors = {"ok": "green", "warning": "yellow", "critical": "red"}
    style = severity_styles.get(severity, "bold green")
    border = border_colors.get(severity, "green")
    target = report.get("target") or {}
    culprit = report.get("culprit_asn") or report.get("culprit_scope") or "none"
    lines = [
        f"  [{style}]{report.get('verdict', 'Healthy')}[/{style}]",
        f"  [dim]Target:[/dim] {target.get('input') or report.get('destination')} → {target.get('resolved_ip') or target.get('host') or 'unknown'}",
        f"  [dim]Likely culprit:[/dim] {culprit} ({report.get('culprit_scope')}, confidence {report.get('confidence')})",
        f"  [dim]Action:[/dim] {report.get('recommended_action')}",
    ]
    evidence = report.get("evidence") or []
    if evidence:
        lines.append("")
        lines.append("  [bold]Evidence[/bold]")
        for item in evidence[:6]:
            lines.append(f"  • {item}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold]Explanation[/bold]",
            border_style=border,
            expand=False,
        )
    )
    console.print()
    console.print("[bold]Escalation summary[/bold]")
    console.print(report.get("ticket_summary", ""))
    console.print()


def error(msg: str):
    console.print(f"  [red]✗[/red] {msg}\n")


def warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}\n")
