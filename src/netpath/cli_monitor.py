from __future__ import annotations

import re

import typer
from rich import box
from rich.table import Table

from netpath import display

def _parse_interval_seconds(value: str) -> int:
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", value.lower())
    if not m:
        raise typer.BadParameter("use an interval like 30s, 10m, 2h, or 1d")
    amount = int(m.group(1))
    unit = m.group(2) or "s"
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    seconds = amount * multiplier
    if seconds <= 0:
        raise typer.BadParameter("interval must be greater than zero")
    return seconds


def _display_monitor_result(snapshot: dict, changes: list[str], history_file: str) -> None:
    title = snapshot.get("monitor_key") or snapshot["asn"]
    table = Table(title=f"Monitor snapshot · {title}", box=box.SIMPLE)
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Target", snapshot.get("target_host") or "—")
    if snapshot.get("target_input") and snapshot.get("target_input") != snapshot.get("target_host"):
        table.add_row("Input", snapshot["target_input"])
    if snapshot.get("target_asn"):
        table.add_row("Target ASN", snapshot["target_asn"])
    table.add_row("AS path", " → ".join(snapshot.get("as_path") or []) or "unknown")
    table.add_row("RTT", f"{snapshot['last_rtt_ms']:.1f} ms" if snapshot.get("last_rtt_ms") is not None else "—")
    table.add_row("Loss", f"{snapshot['loss_pct']:.1f}%" if snapshot.get("loss_pct") is not None else "—")
    table.add_row("Download", f"{snapshot['download_mbps']:.0f} Mbps" if snapshot.get("download_mbps") is not None else "—")
    table.add_row("Verdict", f"{snapshot.get('severity') or 'unknown'} · {snapshot.get('verdict') or 'unknown'}")
    display.console.print(table)
    for change in changes:
        style = "yellow" if change != "No regression detected." and not change.startswith("No previous") else "green"
        display.console.print(f"[{style}]• {change}[/{style}]")
    display.console.print(f"[dim]History: {history_file}[/dim]")

