from __future__ import annotations

import re
import socket
import subprocess
import time


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
