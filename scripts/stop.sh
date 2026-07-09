#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${RESEARCHOS_DEV_PORT:-8001}}"
HOST="${HOST:-${RESEARCHOS_DEV_HOST:-127.0.0.1}}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.researchos-dev.pid"

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
