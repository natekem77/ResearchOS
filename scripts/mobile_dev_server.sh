#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/mobile_dev_server.sh

Start ResearchOS for mobile testing using HOST=0.0.0.0 and PORT=8001 by default.

Environment:
  PORT=8001
  PUBLIC_BASE_URL=http://<lan-or-tailscale-ip>:8001

Examples:
  ./scripts/mobile_dev_server.sh
  PUBLIC_BASE_URL=http://192.168.1.25:8001 ./scripts/mobile_dev_server.sh
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

first_lan_ip() {
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
    return 0
  fi
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1
  fi
}

if [ -z "$PUBLIC_BASE_URL" ]; then
  LAN_IP="$(first_lan_ip || true)"
  if [ -n "$LAN_IP" ]; then
    PUBLIC_BASE_URL="http://$LAN_IP:$PORT"
  fi
fi

echo "Starting ResearchOS for mobile testing..."
echo "Bind host:       $HOST"
echo "Port:            $PORT"
if [ -n "$PUBLIC_BASE_URL" ]; then
  echo "Mobile URL:      $PUBLIC_BASE_URL"
else
  echo "Mobile URL:      set PUBLIC_BASE_URL=http://<windows-or-lan-ip>:$PORT"
fi
echo
echo "On iPhone/Android, enter the Mobile URL in the ResearchOS Server Connection screen."
echo "If running under WSL, you may need Windows firewall and port-forwarding setup."
echo

export HOST
export PORT
export PUBLIC_BASE_URL
ARGS=(--host "$HOST" --port "$PORT")
if [ -n "$PUBLIC_BASE_URL" ]; then
  ARGS+=(--public-base-url "$PUBLIC_BASE_URL")
fi
exec "$ROOT_DIR/scripts/demo.sh" "${ARGS[@]}"
