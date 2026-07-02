import ipaddress
import json
import math
import tempfile
import webbrowser
from pathlib import Path

import requests
from rich.panel import Panel

from netpath.display import LATENCY_GREEN_MS, LATENCY_YELLOW_MS, console

_BATCH_URL = "http://ip-api.com/batch"
_BATCH_SIZE = 100

_A2_TO_A3: dict[str, str] = {
    "AD": "AND", "AE": "ARE", "AF": "AFG", "AG": "ATG", "AI": "AIA",
    "AL": "ALB", "AM": "ARM", "AO": "AGO", "AQ": "ATA", "AR": "ARG",
    "AS": "ASM", "AT": "AUT", "AU": "AUS", "AW": "ABW", "AZ": "AZE",
    "BA": "BIH", "BB": "BRB", "BD": "BGD", "BE": "BEL", "BF": "BFA",
    "BG": "BGR", "BH": "BHR", "BI": "BDI", "BJ": "BEN", "BM": "BMU",
    "BN": "BRN", "BO": "BOL", "BR": "BRA", "BS": "BHS", "BT": "BTN",
    "BW": "BWA", "BY": "BLR", "BZ": "BLZ", "CA": "CAN", "CD": "COD",
    "CF": "CAF", "CG": "COG", "CH": "CHE", "CI": "CIV", "CK": "COK",
    "CL": "CHL", "CM": "CMR", "CN": "CHN", "CO": "COL", "CR": "CRI",
    "CU": "CUB", "CV": "CPV", "CW": "CUW", "CY": "CYP", "CZ": "CZE",
    "DE": "DEU", "DJ": "DJI", "DK": "DNK", "DM": "DMA", "DO": "DOM",
    "DZ": "DZA", "EC": "ECU", "EE": "EST", "EG": "EGY", "ER": "ERI",
    "ES": "ESP", "ET": "ETH", "FI": "FIN", "FJ": "FJI", "FK": "FLK",
    "FM": "FSM", "FO": "FRO", "FR": "FRA", "GA": "GAB", "GB": "GBR",
    "GD": "GRD", "GE": "GEO", "GF": "GUF", "GG": "GGY", "GH": "GHA",
    "GI": "GIB", "GL": "GRL", "GM": "GMB", "GN": "GIN", "GP": "GLP",
    "GQ": "GNQ", "GR": "GRC", "GT": "GTM", "GU": "GUM", "GW": "GNB",
    "GY": "GUY", "HK": "HKG", "HN": "HND", "HR": "HRV", "HT": "HTI",
    "HU": "HUN", "ID": "IDN", "IE": "IRL", "IL": "ISR", "IM": "IMN",
    "IN": "IND", "IQ": "IRQ", "IR": "IRN", "IS": "ISL", "IT": "ITA",
    "JE": "JEY", "JM": "JAM", "JO": "JOR", "JP": "JPN", "KE": "KEN",
    "KG": "KGZ", "KH": "KHM", "KI": "KIR", "KM": "COM", "KN": "KNA",
    "KP": "PRK", "KR": "KOR", "KW": "KWT", "KY": "CYM", "KZ": "KAZ",
    "LA": "LAO", "LB": "LBN", "LC": "LCA", "LI": "LIE", "LK": "LKA",
    "LR": "LBR", "LS": "LSO", "LT": "LTU", "LU": "LUX", "LV": "LVA",
    "LY": "LBY", "MA": "MAR", "MC": "MCO", "MD": "MDA", "ME": "MNE",
    "MG": "MDG", "MH": "MHL", "MK": "MKD", "ML": "MLI", "MM": "MMR",
    "MN": "MNG", "MO": "MAC", "MQ": "MTQ", "MR": "MRT", "MS": "MSR",
    "MT": "MLT", "MU": "MUS", "MV": "MDV", "MW": "MWI", "MX": "MEX",
    "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NC": "NCL", "NE": "NER",
    "NG": "NGA", "NI": "NIC", "NL": "NLD", "NO": "NOR", "NP": "NPL",
    "NR": "NRU", "NZ": "NZL", "OM": "OMN", "PA": "PAN", "PE": "PER",
    "PF": "PYF", "PG": "PNG", "PH": "PHL", "PK": "PAK", "PL": "POL",
    "PR": "PRI", "PS": "PSE", "PT": "PRT", "PW": "PLW", "PY": "PRY",
    "QA": "QAT", "RE": "REU", "RO": "ROU", "RS": "SRB", "RU": "RUS",
    "RW": "RWA", "SA": "SAU", "SB": "SLB", "SC": "SYC", "SD": "SDN",
    "SE": "SWE", "SG": "SGP", "SH": "SHN", "SI": "SVN", "SK": "SVK",
    "SL": "SLE", "SM": "SMR", "SN": "SEN", "SO": "SOM", "SR": "SUR",
    "SS": "SSD", "ST": "STP", "SV": "SLV", "SX": "SXM", "SY": "SYR",
    "SZ": "SWZ", "TD": "TCD", "TG": "TGO", "TH": "THA", "TJ": "TJK",
    "TL": "TLS", "TM": "TKM", "TN": "TUN", "TO": "TON", "TR": "TUR",
    "TT": "TTO", "TV": "TUV", "TW": "TWN", "TZ": "TZA", "UA": "UKR",
    "UG": "UGA", "US": "USA", "UY": "URY", "UZ": "UZB", "VA": "VAT",
    "VC": "VCT", "VE": "VEN", "VG": "VGB", "VI": "VIR", "VN": "VNM",
    "VU": "VUT", "WS": "WSM", "YE": "YEM", "YT": "MYT", "ZA": "ZAF",
    "ZM": "ZMB", "ZW": "ZWE",
}


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


def _build_coverage_html(a3_codes: list[str], raw_values: list[int], log_values: list[float]) -> str:
    codes_js = json.dumps(a3_codes)
    log_js = json.dumps(log_values)
    raw_js = json.dumps(raw_values)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>netpath — Globalping coverage globe</title>
  <style>body{{margin:0;background:#0a0a1a}}#g{{width:100vw;height:100vh}}</style>
</head>
<body>
  <div id="g"></div>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <script>
var raw = {raw_js};
var trace = {{
  type: 'choropleth',
  locationmode: 'ISO-3',
  locations: {codes_js},
  z: {log_js},
  text: raw.map(String),
  zmin: 0,
  colorscale: [
    [0, '#1a1a2e'], [0.05, '#16213e'], [0.15, '#0f3460'],
    [0.4, '#533483'], [0.7, '#e94560'], [1.0, '#ff9800']
  ],
  colorbar: {{
    title: 'Probes<br>(log scale)',
    bgcolor: 'rgba(0,0,0,0.6)',
    tickfont: {{color: '#ccc'}},
    titlefont: {{color: '#ccc'}}
  }},
  marker: {{line: {{color: '#333', width: 0.5}}}},
  hovertemplate: '%{{location}}: %{{text}} probes<extra></extra>'
}};
var layout = {{
  geo: {{
    showframe: false,
    showcoastlines: true,
    coastlinecolor: '#555',
    projection: {{type: 'natural earth'}},
    bgcolor: '#0a0a1a',
    showland: true,
    landcolor: '#1a1a2e',
    showocean: true,
    oceancolor: '#0a0a1a',
    showcountries: true,
    countrycolor: '#333'
  }},
  paper_bgcolor: '#0a0a1a',
  font: {{color: '#ccc'}},
  title: {{text: 'Globalping Coverage by Country', font: {{color: '#ccc', size: 18}}}}
}};
Plotly.newPlot('g', [trace], layout, {{responsive: true}});
  </script>
</body>
</html>"""


def render_coverage(coverage: dict[str, int]) -> None:
    """Render a choropleth globe showing Globalping probe density by country."""
    if not coverage:
        console.print(Panel(
            "  No coverage data to visualize.",
            title="[bold yellow]Globe[/bold yellow]",
            border_style="yellow",
            expand=False,
        ))
        return

    a3_codes: list[str] = []
    raw_values: list[int] = []
    for cc, total in coverage.items():
        a3 = _A2_TO_A3.get(cc)
        if a3:
            a3_codes.append(a3)
            raw_values.append(total)

    if not a3_codes:
        console.print(Panel(
            "  No countries could be mapped to ISO-3 codes — globe skipped.",
            title="[bold yellow]Globe[/bold yellow]",
            border_style="yellow",
            expand=False,
        ))
        return

    log_values = [math.log1p(v) for v in raw_values]
    html = _build_coverage_html(a3_codes, raw_values, log_values)
    try:
        out = Path(tempfile.mkdtemp()) / "netpath-coverage.html"
        out.write_text(html, encoding="utf-8")
        if not webbrowser.open(out.as_uri()):
            console.print(f"  [dim]Coverage globe saved — open manually: {out}[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Coverage globe write failed: {e}[/yellow]")
