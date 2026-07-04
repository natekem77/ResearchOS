#!/usr/bin/env bash
set -euo pipefail

PORT="${RESEARCHOS_DEV_PORT:-8001}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.researchos-dev.pid"

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

is_running() {
  kill -0 "$1" 2>/dev/null
}

PIDS=""
if [ -f "$PID_FILE" ]; then
  PID_FROM_FILE="$(cat "$PID_FILE")"
  if [ -n "$PID_FROM_FILE" ] && is_running "$PID_FROM_FILE"; then
    PIDS="$PIDS $PID_FROM_FILE"
  fi
fi

PORT_PIDS="$(find_port_pids)"
if [ -n "$PORT_PIDS" ]; then
  PIDS="$PIDS $PORT_PIDS"
fi

PIDS="$(printf "%s\n" $PIDS 2>/dev/null | sort -u | tr "\n" " " | xargs 2>/dev/null || true)"
if [ -z "$PIDS" ]; then
  echo "No process is listening on port $PORT."
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping process(es) on port $PORT: $PIDS"
for pid in $PIDS; do
  kill "$pid" 2>/dev/null || true
done

for _ in 1 2 3 4 5; do
  REMAINING=""
  for pid in $PIDS; do
    if is_running "$pid"; then
      REMAINING="$REMAINING $pid"
    fi
  done

  if [ -z "$REMAINING" ]; then
    rm -f "$PID_FILE"
    echo "Stopped."
    exit 0
  fi

  sleep 1
done

echo "Process(es) did not stop after SIGTERM; forcing stop: $REMAINING"
for pid in $REMAINING; do
  kill -9 "$pid" 2>/dev/null || true
done

rm -f "$PID_FILE"
echo "Stopped."
