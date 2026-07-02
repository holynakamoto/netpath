from __future__ import annotations

import socket
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed


def resolve_host(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except (socket.gaierror, OSError):
        return None


def resolve_hosts_parallel(hostnames: list[str], workers: int = 50) -> dict[str, str]:
    """Returns {hostname: ip} for successful resolutions."""
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_to_host = {ex.submit(resolve_host, h): h for h in hostnames}
        for future in as_completed(future_to_host):
            host = future_to_host[future]
            ip = future.result()
            if ip:
                results[host] = ip
    return results


def _cymru_query(ips: list[str], timeout: int = 30) -> str:
    """Raw Cymru bulk whois query. Returns the full response text."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(("whois.cymru.com", 43))
    s.sendall(("begin\nverbose\n" + "\n".join(ips) + "\nend\n").encode())
    chunks = []
    while True:
        try:
            data = s.recv(8192)
            if not data:
                break
            chunks.append(data)
        except socket.timeout:
            break
    s.close()
    return b"".join(chunks).decode(errors="replace")


def cymru_bulk_lookup(ips: list[str], timeout: int = 30) -> dict[str, str]:
    """
    Bulk ASN lookup via Team Cymru whois.
    Returns {ip: "AS12345"} for all IPs with known ASNs.
    """
    if not ips:
        return {}
    try:
        response = _cymru_query(ips, timeout)
    except OSError:
        try:
            time.sleep(1)
            response = _cymru_query(ips, timeout)
        except OSError as exc:
            warnings.warn(f"Cymru bulk lookup failed after retry: {exc}")
            return {}

    result: dict[str, str] = {}
    for line in response.splitlines():
        line = line.strip()
        if not line or line.startswith("Bulk") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        asn_num, ip = parts[0], parts[1]
        if asn_num and asn_num not in ("NA", ""):
            result[ip] = f"AS{asn_num}"
    return result


def cymru_bulk_lookup_rich(ips: list[str], timeout: int = 30) -> dict[str, dict]:
    """
    Bulk Cymru whois returning full record per IP.
    Response format: ASN | IP | prefix | country | registry | date | name
    Returns {ip: {asn, prefix, name}}.
    """
    if not ips:
        return {}
    try:
        response = _cymru_query(ips, timeout)
    except OSError:
        try:
            time.sleep(1)
            response = _cymru_query(ips, timeout)
        except OSError as exc:
            warnings.warn(f"Cymru rich lookup failed after retry: {exc}")
            return {}

    result: dict[str, dict] = {}
    for line in response.splitlines():
        line = line.strip()
        if not line or line.startswith("Bulk") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        asn_num = parts[0]
        ip      = parts[1]
        prefix  = parts[2] if len(parts) > 2 else ""
        name    = parts[6].split(",")[0].strip() if len(parts) > 6 else ""
        if asn_num and asn_num not in ("NA", "") and ip:
            result[ip] = {
                "asn":    f"AS{asn_num}",
                "prefix": prefix,
                "name":   name,
            }
    return result


def normalize_asn(asn: str) -> str:
    asn = asn.upper().strip()
    if not asn.startswith("AS"):
        asn = f"AS{asn}"
    return asn
