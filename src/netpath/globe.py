import ipaddress
import json
import tempfile
import webbrowser
from pathlib import Path

import requests
from rich.panel import Panel

from netpath.display import LATENCY_GREEN_MS, LATENCY_YELLOW_MS, console

_BATCH_URL = "http://ip-api.com/batch"
_BATCH_SIZE = 100


def _is_private(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False  # Hostname — let ip-api.com resolve it


def _geolocate(hosts: list[str]) -> dict[str, dict]:
    """Batch geolocate hosts/IPs. Returns {host: {lat, lon}} for successful lookups."""
    results: dict[str, dict] = {}
    for i in range(0, len(hosts), _BATCH_SIZE):
        batch = hosts[i : i + _BATCH_SIZE]
        payload = [{"query": h, "fields": "query,lat,lon,status"} for h in batch]
        try:
            resp = requests.post(_BATCH_URL, json=payload, timeout=10)
        except requests.RequestException as e:
            raise RuntimeError(f"Geolocation request failed: {e}") from e
        if resp.status_code == 429:
            raise RuntimeError("ip-api.com rate limit reached (HTTP 429)")
        if not resp.ok:
            raise RuntimeError(f"ip-api.com returned HTTP {resp.status_code}")
        for item in resp.json():
            if item.get("status") == "success":
                results[item["query"]] = {"lat": item["lat"], "lon": item["lon"]}
    return results


def _arc_color(delta_ms: float) -> str:
    if delta_ms < LATENCY_GREEN_MS:
        return "rgba(0,255,128,0.8)"
    if delta_ms < LATENCY_YELLOW_MS:
        return "rgba(255,220,0,0.8)"
    return "rgba(255,60,60,0.9)"


def _build_html(points: list[dict], arcs: list[dict]) -> str:
    pts = json.dumps(points)
    acs = json.dumps(arcs)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>netpath — AS path globe</title>
  <style>
    body{{margin:0;background:#0a0a1a;overflow:hidden}}
    #g{{width:100vw;height:100vh}}
    #legend{{position:fixed;top:16px;right:16px;background:rgba(0,0,0,.75);
            color:#ccc;font:13px monospace;padding:12px 16px;
            border-radius:8px;border:1px solid #333}}
    .r{{display:flex;align-items:center;gap:8px;margin:3px 0}}
    .c{{width:12px;height:12px;border-radius:50%;flex-shrink:0}}
  </style>
</head>
<body>
  <div id="g"></div>
  <div id="legend">
    <b>Latency delta per hop</b>
    <div class="r"><div class="c" style="background:#00ff80"></div>&lt; 20 ms</div>
    <div class="r"><div class="c" style="background:#ffdc00"></div>20–79 ms</div>
    <div class="r"><div class="c" style="background:#ff3c3c"></div>≥ 80 ms</div>
  </div>
  <script src="https://unpkg.com/globe.gl"></script>
  <script>
const G=Globe()
  .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-dark.jpg')
  .backgroundImageUrl('https://unpkg.com/three-globe/example/img/night-sky.png')
  .pointsData({pts})
  .pointLat(d=>d.lat).pointLng(d=>d.lon)
  .pointLabel(d=>d.label)
  .pointColor(()=>'#00cfff').pointRadius(.4).pointAltitude(.01)
  .arcsData({acs})
  .arcStartLat(d=>d.sLat).arcStartLng(d=>d.sLon)
  .arcEndLat(d=>d.eLat).arcEndLng(d=>d.eLon)
  .arcColor(d=>d.color).arcAltitudeAutoScale(.4)
  .arcStroke(1.5).arcDashLength(.4).arcDashGap(.2).arcDashAnimateTime(2000)
  (document.getElementById('g'));
G.controls().autoRotate=true;
G.controls().autoRotateSpeed=.5;
  </script>
</body>
</html>"""


def render(hubs_by_asn: dict[str, list[dict]]) -> None:
    """Geolocate hops, generate a Globe.gl HTML file, and open it in the browser."""
    candidates: list[str] = []
    seen_hosts: set[str] = set()
    for hubs in hubs_by_asn.values():
        for hub in hubs:
            host = hub.get("host") or ""
            if not host or host == "???":
                continue
            if _is_private(host):
                continue
            if host not in seen_hosts:
                seen_hosts.add(host)
                candidates.append(host)

    if not candidates:
        console.print(
            Panel(
                "  All hops are unresolvable or private IPs — globe skipped.",
                title="[bold yellow]Globe[/bold yellow]",
                border_style="yellow",
                expand=False,
            )
        )
        return

    try:
        geo = _geolocate(candidates)
    except RuntimeError as e:
        console.print(
            Panel(
                f"  Geolocation failed: {e}\n  Terminal probe results are unaffected.",
                title="[bold yellow]Globe warning[/bold yellow]",
                border_style="yellow",
                expand=False,
            )
        )
        return

    if not geo:
        console.print(
            Panel(
                "  No hops could be geolocated — globe skipped.",
                title="[bold yellow]Globe[/bold yellow]",
                border_style="yellow",
                expand=False,
            )
        )
        return

    points: list[dict] = []
    arcs: list[dict] = []
    seen_pts: set[tuple[float, float]] = set()

    for asn_str, hubs in hubs_by_asn.items():
        geo_hops: list[dict] = []
        for hub in hubs:
            host = hub.get("host") or ""
            if host and geo.get(host):
                geo_hops.append({
                    "lat": geo[host]["lat"],
                    "lon": geo[host]["lon"],
                    "count": hub.get("count", 0),
                    "asn": hub.get("ASN") or asn_str,
                    "avg_ms": float(hub.get("Avg") or 0),
                })

        for hop in geo_hops:
            key = (hop["lat"], hop["lon"])
            if key not in seen_pts:
                seen_pts.add(key)
                points.append({
                    "lat": hop["lat"],
                    "lon": hop["lon"],
                    "label": f"Hop {hop['count']} · {hop['asn']}",
                })

        for i in range(1, len(geo_hops)):
            prev, curr = geo_hops[i - 1], geo_hops[i]
            delta = curr["avg_ms"] - prev["avg_ms"]
            arcs.append({
                "sLat": prev["lat"],
                "sLon": prev["lon"],
                "eLat": curr["lat"],
                "eLon": curr["lon"],
                "color": _arc_color(delta),
            })

    if not points:
        console.print(
            Panel(
                "  No hops could be geolocated — globe skipped.",
                title="[bold yellow]Globe[/bold yellow]",
                border_style="yellow",
                expand=False,
            )
        )
        return

    html = _build_html(points, arcs)
    try:
        out = Path(tempfile.mkdtemp()) / "netpath-globe.html"
        out.write_text(html, encoding="utf-8")
        if not webbrowser.open(out.as_uri()):
            console.print(f"  [dim]Globe saved — open manually: {out}[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Globe write failed: {e}[/yellow]")
