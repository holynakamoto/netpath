from typing import Optional, TypedDict


Hub = TypedDict("Hub", {
    "count": int,
    "host": str,
    "ASN": str,
    "asn_name": str,
    "Loss%": float,
    "Avg": float,
    "Best": float,
    "Wrst": float,
    "StDev": float,
    "p50": Optional[float],
    "p95": Optional[float],
    "p99": Optional[float],
    "type": str,
}, total=False)


class MeasurementResult(TypedDict, total=False):
    as_path: list
    last_rtt_ms: Optional[float]
    rum: Optional[dict]
    hubs: list
    bufferbloat_ms: Optional[float]
    download_mbps: Optional[float]
    upload_mbps: Optional[float]
    verdict: dict
    path_complete: bool
    verified_rtt_ms: Optional[float]
    entry_transit_asn: Optional[str]
    stall_hop: Optional[int]
    jitter_ms: Optional[float]
    probe_count: int
    probe_errors: Optional[dict]
    pmtu: Optional[dict]
    tcp_connect_ms: Optional[float]
    tls_handshake_ms: Optional[float]
    ecmp_paths: Optional[int]
    path_changes: int
    hubs_v4: Optional[list]
    hubs_v6: Optional[list]
    trace_truncated: bool
    remote_only: bool
    skip_reason: Optional[str]
    _trace_method: Optional[str]
    _trace_error: Optional[str]
    _iperf_upload: Optional[dict]
    _iperf_download: Optional[dict]
    _iperf_idle_rtt: Optional[float]
    _iperf_loaded_rtt: Optional[float]
    _iperf_error: Optional[str]
    _speedtest_upload: Optional[dict]
    _speedtest_download: Optional[dict]
    _speedtest_error: Optional[str]
    _v6_warn: Optional[str]
