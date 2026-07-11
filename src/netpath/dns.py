from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import random
import re
import socket
import struct
import subprocess
import time
from collections import Counter

SUPPORTED_RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA")
_QTYPE = {"A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "MX": 15, "TXT": 16, "AAAA": 28}
_RCODE = {
    0: "NOERROR",
    1: "FORMERR",
    2: "SERVFAIL",
    3: "NXDOMAIN",
    4: "NOTIMP",
    5: "REFUSED",
}


@dataclass(frozen=True)
class PublicResolver:
    name: str
    location: str
    ip: str
    lat: float
    lon: float


PUBLIC_RESOLVERS: tuple[PublicResolver, ...] = (
    PublicResolver("Google Public DNS", "Anycast", "8.8.8.8", 37.4, -122.1),
    PublicResolver("Cloudflare", "Anycast", "1.1.1.1", 37.8, -122.4),
    PublicResolver("Quad9", "CH/Any", "9.9.9.9", 47.4, 8.5),
    PublicResolver("OpenDNS (Cisco)", "US/Any", "208.67.222.222", 33.9, -118.2),
    PublicResolver("CleanBrowsing", "Anycast", "185.228.168.9", 33.4, -112.0),
    PublicResolver("Level3", "US", "4.2.2.2", 39.7, -105.0),
    PublicResolver("Lumen (Qwest)", "US", "205.171.3.66", 40.4, -104.0),
    PublicResolver("Hurricane Electric", "US", "74.82.42.42", 37.6, -122.0),
    PublicResolver("Neustar UltraDNS", "US/Any", "64.6.64.6", 39.0, -77.5),
    PublicResolver("Comodo Secure DNS", "US", "8.26.56.26", 40.9, -74.2),
    PublicResolver("FortiGuard", "US/Any", "208.91.112.53", 37.3, -121.9),
    PublicResolver("CIRA Canadian Shield", "CA", "149.112.121.10", 45.4, -75.7),
    PublicResolver("ControlD", "CA/Any", "76.76.2.0", 43.7, -79.4),
    PublicResolver("DNS4EU", "EU/Any", "86.54.11.100", 50.1, 14.4),
    PublicResolver("CZ.NIC ODVR", "CZ", "193.17.47.1", 49.9, 15.3),
    PublicResolver("AdGuard DNS", "EU/Any", "94.140.14.14", 34.7, 33.0),
    PublicResolver("Gcore DNS", "LU/Any", "95.85.95.85", 49.6, 6.1),
    PublicResolver("DNS.SB", "DE/Any", "185.222.222.222", 50.1, 8.7),
    PublicResolver("SafeDNS", "RU", "195.46.39.39", 55.8, 37.6),
    PublicResolver("Yandex DNS", "RU", "77.88.8.8", 55.6, 37.9),
    PublicResolver("Comss.one", "RU", "83.220.169.155", 56.3, 38.1),
    PublicResolver("Bezeq Intl", "IL", "192.115.106.10", 32.1, 34.8),
    PublicResolver("114DNS", "CN", "114.114.114.114", 32.1, 118.8),
    PublicResolver("AliDNS", "CN", "223.5.5.5", 30.3, 120.2),
    PublicResolver("DNSPod (Tencent)", "CN", "119.29.29.29", 22.5, 114.1),
    PublicResolver("Baidu DNS", "CN", "180.76.76.76", 39.9, 116.4),
    PublicResolver("CNNIC sDNS", "CN", "1.2.4.8", 40.5, 116.9),
    PublicResolver("360 Secure DNS", "CN", "101.226.4.6", 31.2, 121.5),
    PublicResolver("KT (Kornet)", "KR", "168.126.63.1", 37.6, 127.0),
    PublicResolver("LG U+", "KR", "164.124.101.2", 36.5, 127.9),
    PublicResolver("HiNet (Chunghwa)", "TW", "168.95.1.1", 25.0, 121.6),
    PublicResolver("Telstra", "AU", "139.130.4.4", -33.9, 151.2),
    PublicResolver("SafeSurfer", "NZ", "104.197.28.121", -36.8, 174.8),
    PublicResolver("UOL", "BR", "200.221.11.100", -23.5, -46.6),
)


def _resolver_ips() -> list[str]:
    resolvers: list[str] = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == "nameserver":
                    resolvers.append(parts[1])
    except OSError:
        pass
    return resolvers


def _dig_answers(hostname: str, record_type: str) -> list[dict]:
    try:
        proc = subprocess.run(
            ["dig", "+nocmd", hostname, record_type, "+noall", "+answer"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    answers: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        name, ttl, _, rtype = parts[:4]
        value = " ".join(parts[4:]).rstrip(".")
        if rtype not in {"A", "AAAA", "CNAME"}:
            continue
        try:
            ttl_value = int(ttl)
        except ValueError:
            ttl_value = None
        answers.append({
            "name": name.rstrip("."),
            "type": rtype,
            "ttl": ttl_value,
            "value": value,
        })
    return answers


def _short_dig_error(message: str) -> str:
    message = message.strip().splitlines()[-1] if message.strip() else "error"
    lower = message.lower()
    if "timed out" in lower or "timeout" in lower:
        return "timeout"
    if "refused" in lower:
        return "refused"
    return message[:48]


def _parse_dig_output(output: str, record_type: str) -> tuple[str, list[dict]]:
    status = "NOERROR"
    rows: list[dict] = []
    status_match = re.search(r"status:\s*([A-Z]+)", output)
    if status_match:
        status = status_match.group(1)
    for line in output.splitlines():
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        name, ttl, dns_class, rtype = parts[:4]
        if dns_class != "IN":
            continue
        value = " ".join(parts[4:]).rstrip(".")
        try:
            ttl_value = int(ttl)
        except ValueError:
            ttl_value = None
        value_type = rtype if rtype == record_type else f"{rtype}→{record_type}"
        rows.append({
            "name": name.rstrip("."),
            "type": value_type,
            "ttl": ttl_value,
            "value": value,
        })
    return status, rows


def _encode_name(name: str) -> bytes:
    labels = name.rstrip(".").split(".")
    return b"".join(bytes([len(label)]) + label.encode("ascii") for label in labels) + b"\x00"


def _decode_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels = []
    jumped = False
    next_offset = offset
    seen = set()
    while True:
        if offset >= len(packet):
            raise ValueError("truncated name")
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("truncated pointer")
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if pointer in seen:
                raise ValueError("compression loop")
            seen.add(pointer)
            if not jumped:
                next_offset = offset + 2
            offset = pointer
            jumped = True
            continue
        if length == 0:
            if not jumped:
                next_offset = offset + 1
            return ".".join(labels), next_offset
        offset += 1
        end = offset + length
        if end > len(packet):
            raise ValueError("truncated label")
        labels.append(packet[offset:end].decode("ascii", errors="replace"))
        offset = end


def _build_query(domain: str, record_type: str, query_id: int) -> bytes:
    header = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0)
    question = _encode_name(domain) + struct.pack("!HH", _QTYPE[record_type], 1)
    return header + question


def _tcp_exchange(server: str, payload: bytes, timeout: int) -> bytes:
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((server, 53))
        sock.sendall(struct.pack("!H", len(payload)) + payload)
        prefix = sock.recv(2)
        if len(prefix) != 2:
            raise TimeoutError("truncated tcp response")
        expected = struct.unpack("!H", prefix)[0]
        chunks = []
        remaining = expected
        while remaining:
            chunk = sock.recv(remaining)
            if not chunk:
                raise TimeoutError("truncated tcp response")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def _udp_exchange(server: str, payload: bytes, timeout: int) -> bytes:
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(payload, (server, 53))
        response, _ = sock.recvfrom(4096)
        return response


def _format_rdata(packet: bytes, rtype: int, rdata: bytes, rdata_offset: int) -> str:
    if rtype == 1 and len(rdata) == 4:
        return socket.inet_ntop(socket.AF_INET, rdata)
    if rtype == 28 and len(rdata) == 16:
        return socket.inet_ntop(socket.AF_INET6, rdata)
    if rtype in {2, 5}:
        value, _ = _decode_name(packet, rdata_offset)
        return value
    if rtype == 15 and len(rdata) >= 3:
        preference = struct.unpack("!H", rdata[:2])[0]
        exchange, _ = _decode_name(packet, rdata_offset + 2)
        return f"{preference} {exchange}"
    if rtype == 16:
        strings = []
        offset = 0
        while offset < len(rdata):
            length = rdata[offset]
            offset += 1
            strings.append(rdata[offset:offset + length].decode("utf-8", errors="replace"))
            offset += length
        return " ".join(f'"{value}"' for value in strings)
    if rtype == 6:
        mname, offset = _decode_name(packet, rdata_offset)
        rname, offset = _decode_name(packet, offset)
        if offset + 20 <= len(packet):
            serial, refresh, retry, expire, minimum = struct.unpack("!IIIII", packet[offset:offset + 20])
            return f"{mname} {rname} {serial} {refresh} {retry} {expire} {minimum}"
        return f"{mname} {rname}"
    return rdata.hex()


def _parse_dns_response(packet: bytes, query_id: int, record_type: str) -> tuple[str, list[dict], bool]:
    if len(packet) < 12:
        raise ValueError("truncated response")
    resp_id, flags, qdcount, ancount, _, _ = struct.unpack("!HHHHHH", packet[:12])
    if resp_id != query_id:
        raise ValueError("mismatched response id")
    status = _RCODE.get(flags & 0x000F, str(flags & 0x000F))
    truncated = bool(flags & 0x0200)
    offset = 12
    for _ in range(qdcount):
        _, offset = _decode_name(packet, offset)
        offset += 4
    rows = []
    qtype = _QTYPE[record_type]
    type_names = {value: key for key, value in _QTYPE.items()}
    for _ in range(ancount):
        name, offset = _decode_name(packet, offset)
        if offset + 10 > len(packet):
            raise ValueError("truncated record")
        rtype, dns_class, ttl, rdlength = struct.unpack("!HHIH", packet[offset:offset + 10])
        offset += 10
        rdata_offset = offset
        rdata = packet[offset:offset + rdlength]
        offset += rdlength
        if dns_class != 1:
            continue
        value_type = type_names.get(rtype, str(rtype))
        if rtype != qtype and rtype != _QTYPE["CNAME"]:
            continue
        rows.append({
            "name": name,
            "type": value_type if rtype == qtype else f"{value_type}→{record_type}",
            "ttl": ttl,
            "value": _format_rdata(packet, rtype, rdata, rdata_offset),
        })
    return status, rows, truncated


def _native_dns_query(server: str, domain: str, record_type: str, timeout: int) -> tuple[str, list[dict]]:
    query_id = random.randrange(0, 65536)
    payload = _build_query(domain, record_type, query_id)
    packet = _udp_exchange(server, payload, timeout)
    status, rows, truncated = _parse_dns_response(packet, query_id, record_type)
    if truncated:
        packet = _tcp_exchange(server, payload, timeout)
        status, rows, _ = _parse_dns_response(packet, query_id, record_type)
    return status, rows


def query_public_resolver(
    resolver: PublicResolver,
    domain: str,
    record_type: str,
    timeout: int = 3,
) -> dict:
    start = time.monotonic()
    try:
        status, records = _native_dns_query(resolver.ip, domain, record_type, timeout)
    except (OSError, TimeoutError, ValueError) as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000.0)
        return {
            **asdict(resolver),
            "elapsed_ms": elapsed_ms,
            "status": "error",
            "error": _short_dig_error(str(exc)),
            "records": [],
            "values": [],
            "min_ttl": None,
        }

    elapsed_ms = round((time.monotonic() - start) * 1000.0)
    values = sorted({record["value"] for record in records})
    ttls = [record["ttl"] for record in records if record.get("ttl") is not None]
    if status == "SERVFAIL":
        row_status = "servfail"
    elif values:
        row_status = "ok"
    else:
        row_status = "none"
    return {
        **asdict(resolver),
        "elapsed_ms": elapsed_ms,
        "status": row_status,
        "dns_status": status,
        "error": None,
        "records": records,
        "values": values,
        "min_ttl": min(ttls) if ttls else None,
    }


def query_public_resolvers(
    domain: str,
    record_type: str,
    resolvers: tuple[PublicResolver, ...] = PUBLIC_RESOLVERS,
    timeout: int = 3,
) -> list[dict]:
    rows: list[dict | None] = [None] * len(resolvers)
    with ThreadPoolExecutor(max_workers=min(16, len(resolvers))) as pool:
        futures = {
            pool.submit(query_public_resolver, resolver, domain, record_type, timeout): i
            for i, resolver in enumerate(resolvers)
        }
        for future in as_completed(futures):
            rows[futures[future]] = future.result()
    return [row for row in rows if row is not None]


def _answer_key(row: dict) -> tuple[str, ...] | None:
    if row.get("status") == "ok":
        return tuple(row.get("values") or ())
    return None


def summarize_public_resolver_rows(rows: list[dict]) -> dict:
    keys = [_answer_key(row) for row in rows]
    counts = Counter(key for key in keys if key is not None)
    majority_key: tuple[str, ...] | None = None
    if counts:
        majority_key = counts.most_common(1)[0][0]
    majority_rows = [key == majority_key and key is not None for key in keys]
    # Only concrete record sets participate in propagation agreement.  Empty,
    # SERVFAIL, and transport-error outcomes are resolver availability
    # exceptions, not alternate DNS answers.
    usable = sum(1 for key in keys if key is not None)
    responding = sum(1 for row in rows if row.get("status") != "error")
    agree = sum(majority_rows)
    total = len(rows)
    return {
        "total": total,
        "done": total,
        "responding": responding,
        "usable": usable,
        "agree": agree,
        "percentage": round((agree / usable) * 100.0) if usable else 0,
        "errors": sum(1 for row in rows if row.get("status") == "error"),
        "none": sum(1 for row in rows if row.get("status") == "none"),
        "servfail": sum(1 for row in rows if row.get("status") == "servfail"),
        "groups": len(counts),
        "majority_values": list(majority_key or ()),
        "majority_rows": majority_rows,
    }


def _family_name(family: int) -> str:
    if family == socket.AF_INET6:
        return "AAAA"
    if family == socket.AF_INET:
        return "A"
    return str(family)


def measure(hostname: str) -> dict:
    """Capture resolver metadata and hostname answer timing without requiring dnspython."""
    result: dict = {
        "input": hostname,
        "lookup_ms": None,
        "answers": [],
        "cnames": [],
        "resolver_ips": _resolver_ips(),
        "error": None,
    }
    if not hostname:
        result["error"] = "empty hostname"
        return result

    t0 = time.monotonic()
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        result["lookup_ms"] = round((time.monotonic() - t0) * 1000.0, 2)
        result["error"] = str(exc)
        return result
    result["lookup_ms"] = round((time.monotonic() - t0) * 1000.0, 2)

    seen: set[tuple[str, str]] = set()
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        rtype = _family_name(family)
        key = (rtype, ip)
        if key in seen:
            continue
        seen.add(key)
        result["answers"].append({"type": rtype, "address": ip})

    dig_rows = _dig_answers(hostname, "A") + _dig_answers(hostname, "AAAA")
    ttl_by_value = {
        row["value"]: row.get("ttl")
        for row in dig_rows
        if row.get("type") in {"A", "AAAA"} and row.get("ttl") is not None
    }
    for answer in result["answers"]:
        if answer["address"] in ttl_by_value:
            answer["ttl"] = ttl_by_value[answer["address"]]

    cnames = []
    for row in dig_rows:
        if row.get("type") == "CNAME":
            pair = {"name": row["name"], "value": row["value"]}
            if pair not in cnames:
                cnames.append(pair)
    result["cnames"] = cnames

    v4 = any(answer.get("type") == "A" for answer in result["answers"])
    v6 = any(answer.get("type") == "AAAA" for answer in result["answers"])
    result["dual_stack"] = v4 and v6
    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", hostname) or ":" in hostname:
        result["literal"] = True
    return result
