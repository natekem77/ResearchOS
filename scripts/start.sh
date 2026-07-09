#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${RESEARCHOS_DEV_PORT:-8001}}"
HOST="${HOST:-${RESEARCHOS_DEV_HOST:-127.0.0.1}}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PID_FILE="$ROOT_DIR/.researchos-dev.pid"
LOG_FILE="$ROOT_DIR/.researchos-dev.log"

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

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "Missing backend virtual environment: $BACKEND_DIR/.venv"
  echo "Create it with: cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ -n "$(find_port_pids)" ]; then
  echo "Port $PORT is already in use. Run ./scripts/status.sh or ./scripts/stop.sh."
  exit 1
fi

cd "$BACKEND_DIR"
source .venv/bin/activate

export RESEARCHOS_API_HOST="$HOST"
export RESEARCHOS_API_PORT="$PORT"

nohup python -m uvicorn app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"

echo "ResearchOS backend started on http://$HOST:$PORT"
echo "Health URL: http://$HOST:$PORT/health"
echo "PID: $PID"
echo "Log: $LOG_FILE"
