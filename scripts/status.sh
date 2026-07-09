#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${RESEARCHOS_DEV_PORT:-8001}}"
HOST="${HOST:-${RESEARCHOS_DEV_HOST:-127.0.0.1}}"
HEALTH_HOST="$HOST"
if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  HEALTH_HOST="127.0.0.1"
fi
HEALTH_URL="http://$HEALTH_HOST:$PORT/health"

find_port_pids() {
  local pids=""

  if command -v ss >/dev/null 2>&1; then
    pids="$(ss -H -ltnp "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' || true)"
    if [ -n "$pids" ]; then
      printf "%s\n" "$pids"
    fi
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP@"$HOST":"$PORT" -sTCP:LISTEN -t 2>/dev/null || \
      lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true
  fi
}

PIDS="$(find_port_pids | sort -u | tr "\n" " " | xargs 2>/dev/null || true)"
if [ -z "$PIDS" ]; then
  echo "No listener PID detected on $HOST:$PORT."
else
  echo "Port $PORT is listening on $HOST by process(es): $PIDS"
fi

echo "Health check:"
if command -v curl >/dev/null 2>&1; then
  if curl -fsS "$HEALTH_URL"; then
    echo
  else
    echo
    echo "Health endpoint is not responding at $HEALTH_URL."
    exit 1
  fi
elif [ -z "$PIDS" ]; then
  echo "curl is not installed; could not verify $HEALTH_URL"
  exit 1
else
  echo "curl is not installed; open $HEALTH_URL"
fi
