#!/bin/bash
# Capture Zoom call traffic on en0 (Wi-Fi at 192.168.68.55)
# Zoom ports: 8801/8802 UDP (AV), 443 TCP/UDP (QUIC/HTTPS), 3478/3479 UDP (STUN)

IFACE="en0"
OUTFILE="zoom_capture_$(date +%Y%m%d_%H%M%S).pcap"

echo "=== Zoom Capture ==="
echo "Interface : $IFACE (192.168.68.55)"
echo "Output    : $OUTFILE"
echo ""
echo "1. Join your Zoom call NOW"
echo "2. Press Ctrl+C when the call ends"
echo ""
echo "Starting capture..."

sudo tcpdump -i "$IFACE" \
  -w "$OUTFILE" \
  -B 65536 \
  '(udp port 8801 or udp port 8802 or udp port 3478 or udp port 3479) or (tcp port 443) or (udp port 443)' \
  2>&1

echo ""
echo "Capture saved to: $OUTFILE"
echo ""
echo "Run analysis:"
echo "  python3 zoom_analyze.py $OUTFILE"
