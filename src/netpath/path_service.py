from __future__ import annotations

from collections.abc import Callable

import requests

from netpath import globalping, targets
from netpath.asn import normalize_asn
from netpath.cli_json import _apply_path_json_contract
from netpath.cli_measurement import _merge_globalping_path_results

StatusCallback = Callable[[str], None]


def _noop_status(_message: str) -> None:
    pass


def _http_error(exc: requests.HTTPError, source: str) -> RuntimeError:
    status = exc.response.status_code if exc.response is not None else None
    if status == 429:
        return RuntimeError("Globalping rate limit reached; configure NETPATH_GLOBALPING_TOKEN")
    if status == 422:
        return RuntimeError(f"No Globalping probes matched {source}")
    if status == 401:
        return RuntimeError("Globalping authentication failed")
    return RuntimeError(str(exc))


def _collect(
    result: dict,
    target_asn: str | None,
    token: str | None,
    schedule: Callable[[], dict[str, str]],
    status: StatusCallback,
) -> dict:
    status("Scheduling Globalping ping and MTR measurements")
    try:
        mids = schedule()
    except requests.HTTPError as exc:
        raise _http_error(exc, result["source_asn"]) from exc

    result["measurement_ids"] = mids
    status("Waiting for Globalping probes")
    statuses = globalping.poll_until_done(list(mids.values()), token)
    result["statuses"] = statuses
    status("Parsing paths and geolocating public hops")
    _merge_globalping_path_results(
        result,
        mids,
        statuses,
        result["target_ip"],
        target_asn,
        result["target"],
        token,
    )
    return _apply_path_json_contract(result)


def measure_aspath(
    source: str,
    dest: str,
    token: str | None = None,
    target_ip: str | None = None,
    status: StatusCallback = _noop_status,
) -> dict:
    """Measure and rank paths between two ASNs without rendering output."""
    source_asn = normalize_asn(source)
    dest_asn = normalize_asn(dest)

    status(f"Checking probe coverage in {source_asn}")
    try:
        probes = globalping.fetch_probes(token)
    except globalping.GlobalpingAuthError as exc:
        raise RuntimeError("Globalping authentication failed") from exc
    if not globalping.count_probes_by_asn(probes).get(int(source_asn[2:])):
        raise RuntimeError(f"No connected Globalping probes are available in {source_asn}")

    status(f"Finding a live target in {dest_asn}")
    target = targets.discover_target(dest_asn, user_target=target_ip)
    if not target:
        raise RuntimeError(f"No live target found in {dest_asn}")

    result = {
        "source_asn": source_asn,
        "dest_asn": dest_asn,
        "target_ip": target["ip"],
        "target_origin": target.get("origin"),
        "target": target,
        "candidates": [],
    }
    return _collect(
        result,
        dest_asn,
        token,
        lambda: globalping.schedule_path_measurements(source_asn, target["ip"], token),
        status,
    )


def measure_citypath(
    source_query: str,
    dest_query: str,
    token: str | None = None,
    status: StatusCallback = _noop_status,
) -> dict:
    """Measure and rank paths between two geocoded cities without rendering output."""
    status("Geocoding source and destination")
    try:
        source = targets.geocode_city(source_query)
        dest = targets.geocode_city(dest_query)
    except Exception as exc:
        raise RuntimeError(f"City geocoding failed: {exc}") from exc
    if not source or not dest:
        raise RuntimeError("Could not geocode one or both cities")

    status(f"Finding a connected Atlas target near {dest['name']}")
    target = targets.atlas_target_near_city(dest)
    if not target:
        raise RuntimeError(
            f"No connected RIPE Atlas IPv4 target with a matching registry "
            f"country found near {dest['name']}, {dest['country_code']}"
        )

    source_label = f"{source['name']}, {source['country_code']}"
    dest_label = f"{dest['name']}, {dest['country_code']}"
    result = {
        "source_city": source,
        "dest_city": dest,
        "source_asn": source_label,
        "dest_asn": dest_label,
        "target_ip": target["ip"],
        "target_origin": target.get("origin"),
        "target": target,
        "candidates": [],
    }
    location = {
        "name": source["name"],
        "city": source["name"],
        "country": source["country_code"],
    }
    return _collect(
        result,
        target.get("asn"),
        token,
        lambda: globalping.schedule_location_path_measurements(location, target["ip"], token),
        status,
    )
