#!/bin/sh
# Install iperf3 and run it as a hardened systemd service, so netpath users
# can measure real throughput into this network.
#
# Usage:  sh install.sh            (or:  netpath serve --emit install | sh)
# Then open TCP+UDP 5201 in your firewall and register the server — see
# `netpath serve --setup-only` or the deploy README.
set -eu

PORT="${IPERF3_PORT:-5201}"
UNIT=/etc/systemd/system/iperf3-server.service

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root (sudo sh install.sh)" >&2
    exit 1
fi

if ! command -v iperf3 >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y -qq iperf3
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y -q iperf3
    elif command -v apk >/dev/null 2>&1; then
        apk add --no-cache iperf3
    else
        echo "no supported package manager found — install iperf3 manually" >&2
        exit 1
    fi
fi

if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd not available — run 'iperf3 -s -p ${PORT}' under your own supervisor" >&2
    exit 1
fi

cat > "$UNIT" <<EOF
[Unit]
Description=iperf3 throughput test server (netpath)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/env iperf3 -s -p ${PORT}
Restart=always
RestartSec=5
DynamicUser=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now iperf3-server.service
echo "iperf3 server running on TCP/UDP ${PORT} — remember to open the port in your firewall."
