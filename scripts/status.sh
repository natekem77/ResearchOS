#!/usr/bin/env bash
set -euo pipefail

PORT="${RESEARCHOS_DEV_PORT:-8001}"
HOST="${RESEARCHOS_DEV_HOST:-127.0.0.1}"

find_port_pids() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p'
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$PORT" 2>/dev/null || true
    return
  fi
}

PIDS="$(find_port_pids | tr "\n" " " | xargs 2>/dev/null || true)"
if [ -z "$PIDS" ]; then
  echo "Port $PORT is not in use."
  exit 0
fi

echo "Port $PORT is in use by process(es): $PIDS"
echo "Health check:"
if command -v curl >/dev/null 2>&1; then
  curl -s "http://$HOST:$PORT/health" || true
  echo
else
  echo "curl is not installed; open http://$HOST:$PORT/health"
fi
