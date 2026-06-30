#!/usr/bin/env python3
"""
Analyze a Zoom call pcap for throughput, latency (TCP RTT), and jitter.

Usage: python3 zoom_analyze.py <capture.pcap>
"""

import sys
import struct
import socket
import dpkt
from collections import defaultdict

ZOOM_UDP_PORTS = {8801, 8802, 3478, 3479}
ZOOM_TCP_PORT = 443


def load_pcap(path):
    packets = []
    with open(path, "rb") as f:
        try:
            cap = dpkt.pcap.Reader(f)
            for ts, buf in cap:
                packets.append((ts, buf))
        except Exception as e:
            print(f"Error reading pcap: {e}")
            sys.exit(1)
    return packets


def is_zoom_udp(udp):
    return udp.sport in ZOOM_UDP_PORTS or udp.dport in ZOOM_UDP_PORTS


def is_zoom_tcp(tcp):
    return tcp.sport == ZOOM_TCP_PORT or tcp.dport == ZOOM_TCP_PORT


# ── Throughput ────────────────────────────────────────────────────────────────

def calc_throughput(packets):
    """Bytes per second in 1-second buckets, split by direction."""
    buckets_in = defaultdict(int)
    buckets_out = defaultdict(int)
    local_ip = socket.inet_aton("192.168.68.55")

    for ts, buf in packets:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            length = len(buf)
            bucket = int(ts)
            if ip.src == local_ip:
                buckets_out[bucket] += length
            else:
                buckets_in[bucket] += length
        except Exception:
            continue

    return buckets_in, buckets_out


def throughput_stats(buckets):
    if not buckets:
        return 0, 0, 0
    vals = list(buckets.values())
    avg = sum(vals) / len(vals)
    return avg * 8 / 1000, max(vals) * 8 / 1000, min(vals) * 8 / 1000  # kbps


# ── Jitter (UDP inter-arrival) ────────────────────────────────────────────────

def calc_jitter(packets):
    """
    RFC 3550 jitter estimate over UDP Zoom streams.
    Returns mean jitter in milliseconds per stream (sport,dport pair).
    """
    arrivals = defaultdict(list)

    for ts, buf in packets:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP):
                continue
            udp = ip.data
            if not is_zoom_udp(udp):
                continue
            key = (min(udp.sport, udp.dport), max(udp.sport, udp.dport))
            arrivals[key].append(ts)
        except Exception:
            continue

    stream_jitter = {}
    for key, times in arrivals.items():
        if len(times) < 2:
            continue
        inter = [times[i+1] - times[i] for i in range(len(times)-1)]
        # RFC 3550: D(i,j) = |arrival_diff - send_diff|; approximate with arrival only
        diffs = [abs(inter[i+1] - inter[i]) for i in range(len(inter)-1)]
        if diffs:
            stream_jitter[key] = (sum(diffs) / len(diffs)) * 1000  # ms
    return stream_jitter


# ── TCP RTT (SYN→SYN-ACK) ────────────────────────────────────────────────────

def calc_tcp_rtt(packets):
    """
    Estimate RTT from TCP SYN / SYN-ACK pairs on port 443.
    Returns list of RTT values in milliseconds.
    """
    syn_times = {}  # seq -> timestamp
    rtts = []

    for ts, buf in packets:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.tcp.TCP):
                continue
            tcp = ip.data
            if not is_zoom_tcp(tcp):
                continue

            flags = tcp.flags
            SYN = dpkt.tcp.TH_SYN
            ACK = dpkt.tcp.TH_ACK

            if flags & SYN and not (flags & ACK):
                syn_times[tcp.seq] = ts
            elif flags & SYN and flags & ACK:
                # SYN-ACK: ack_num - 1 is the original SYN seq
                orig_seq = (tcp.ack - 1) & 0xFFFFFFFF
                if orig_seq in syn_times:
                    rtt_ms = (ts - syn_times.pop(orig_seq)) * 1000
                    if 0 < rtt_ms < 5000:
                        rtts.append(rtt_ms)
        except Exception:
            continue

    return rtts


# ── Packet loss (sequence gap heuristic) ─────────────────────────────────────

def estimate_loss(packets):
    """Rough UDP loss estimate: count sequence gaps > 1 in Zoom UDP streams."""
    seqs = defaultdict(list)
    local_ip = socket.inet_aton("192.168.68.55")

    for ts, buf in packets:
        try:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if not isinstance(ip.data, dpkt.udp.UDP):
                continue
            udp = ip.data
            if not is_zoom_udp(udp):
                continue
            # Only inbound streams for loss detection
            if ip.dst == local_ip and len(udp.data) >= 4:
                key = (ip.src, udp.sport, udp.dport)
                # Zoom sequence number is typically in bytes 2-3 of payload
                seq = struct.unpack(">H", udp.data[2:4])[0]
                seqs[key].append(seq)
        except Exception:
            continue

    total_gaps = 0
    total_expected = 0
    for key, seq_list in seqs.items():
        if len(seq_list) < 2:
            continue
        seq_list.sort()
        for i in range(1, len(seq_list)):
            diff = (seq_list[i] - seq_list[i-1]) & 0xFFFF
            if 1 < diff < 1000:
                total_gaps += diff - 1
                total_expected += diff
            elif diff == 1:
                total_expected += 1

    loss_pct = (total_gaps / total_expected * 100) if total_expected > 0 else 0
    return total_gaps, total_expected, loss_pct


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 zoom_analyze.py <capture.pcap>")
        sys.exit(1)

    path = sys.argv[1]
    print(f"\nLoading {path}...")
    packets = load_pcap(path)
    print(f"Loaded {len(packets)} packets\n")

    if not packets:
        print("No packets found.")
        sys.exit(1)

    duration = packets[-1][0] - packets[0][0]
    print(f"{'='*54}")
    print(f"  ZOOM CALL NETWORK ANALYSIS")
    print(f"{'='*54}")
    print(f"  Capture duration : {duration:.1f} seconds ({duration/60:.1f} min)")
    print(f"  Total packets    : {len(packets):,}")
    print()

    # ── Throughput
    buckets_in, buckets_out = calc_throughput(packets)
    avg_in, max_in, min_in = throughput_stats(buckets_in)
    avg_out, max_out, min_out = throughput_stats(buckets_out)

    total_bytes = sum(len(buf) for _, buf in packets)
    overall_mbps = (total_bytes * 8) / (duration * 1_000_000) if duration > 0 else 0

    print(f"  THROUGHPUT")
    print(f"  {'─'*50}")
    print(f"  Overall           : {overall_mbps:.2f} Mbps")
    print(f"  Inbound  (avg)    : {avg_in:.0f} kbps  (peak {max_in:.0f} kbps)")
    print(f"  Outbound (avg)    : {avg_out:.0f} kbps  (peak {max_out:.0f} kbps)")
    print()

    # ── Jitter
    stream_jitter = calc_jitter(packets)
    if stream_jitter:
        all_jitter = list(stream_jitter.values())
        mean_jitter = sum(all_jitter) / len(all_jitter)
        max_jitter = max(all_jitter)
        print(f"  JITTER (UDP streams)")
        print(f"  {'─'*50}")
        print(f"  Mean              : {mean_jitter:.2f} ms")
        print(f"  Max               : {max_jitter:.2f} ms")
        print(f"  Streams analyzed  : {len(stream_jitter)}")
        if mean_jitter < 20:
            verdict = "Excellent (< 20 ms)"
        elif mean_jitter < 50:
            verdict = "Good (20–50 ms)"
        else:
            verdict = "Degraded (> 50 ms) — expect audio/video issues"
        print(f"  Quality           : {verdict}")
    else:
        print(f"  JITTER            : No UDP Zoom streams found")
    print()

    # ── Latency (TCP RTT)
    rtts = calc_tcp_rtt(packets)
    if rtts:
        avg_rtt = sum(rtts) / len(rtts)
        min_rtt = min(rtts)
        max_rtt = max(rtts)
        print(f"  LATENCY (TCP RTT, port 443)")
        print(f"  {'─'*50}")
        print(f"  Min RTT           : {min_rtt:.1f} ms")
        print(f"  Avg RTT           : {avg_rtt:.1f} ms")
        print(f"  Max RTT           : {max_rtt:.1f} ms")
        print(f"  Samples           : {len(rtts)}")
        if avg_rtt < 50:
            verdict = "Excellent (< 50 ms)"
        elif avg_rtt < 150:
            verdict = "Good (50–150 ms)"
        else:
            verdict = "High (> 150 ms) — noticeable delay"
        print(f"  Quality           : {verdict}")
    else:
        print(f"  LATENCY           : No TCP SYN/SYN-ACK pairs found (UDP-only call)")
    print()

    # ── Packet loss
    gaps, expected, loss_pct = estimate_loss(packets)
    print(f"  PACKET LOSS (inbound UDP, heuristic)")
    print(f"  {'─'*50}")
    print(f"  Estimated loss    : {loss_pct:.2f}%  ({gaps} gaps / {expected} expected)")
    if loss_pct < 1:
        verdict = "Excellent (< 1%)"
    elif loss_pct < 3:
        verdict = "Acceptable (1–3%)"
    else:
        verdict = "High (> 3%) — expect choppy audio/video"
    print(f"  Quality           : {verdict}")
    print()
    print(f"{'='*54}")


if __name__ == "__main__":
    main()
