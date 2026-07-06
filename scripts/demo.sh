#!/usr/bin/env bash
set -euo pipefail

PORT="${RESEARCHOS_DEV_PORT:-8001}"
HOST="${RESEARCHOS_DEV_HOST:-127.0.0.1}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT_DIR/.researchos-dev.log"
HEALTH_URL="http://$HOST:$PORT/health"
DASHBOARD_URL="http://$HOST:$PORT"

wait_for_health() {
  echo "Waiting for ResearchOS at $HEALTH_URL ..."
  for _ in $(seq 1 20); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      echo "ResearchOS backend is healthy."
      return 0
    fi
    sleep 1
  done

  echo "ResearchOS did not become healthy within 20 seconds."
  if [ -f "$LOG_FILE" ]; then
    echo "Last 80 lines of $LOG_FILE:"
    tail -n 80 "$LOG_FILE"
  fi
  return 1
}

open_dashboard_if_possible() {
  if [ "${RESEARCHOS_OPEN_BROWSER:-1}" = "0" ]; then
    return 0
  fi

  if command -v wslview >/dev/null 2>&1; then
    wslview "$DASHBOARD_URL" >/dev/null 2>&1 &
    return 0
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$DASHBOARD_URL" >/dev/null 2>&1 &
    return 0
  fi

  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Start-Process '$DASHBOARD_URL'" >/dev/null 2>&1 &
    return 0
  fi
}

echo "Starting ResearchOS demo on $DASHBOARD_URL ..."
"$ROOT_DIR/scripts/restart.sh"
wait_for_health

echo "Loading demo lab notes ..."
curl -fsS -X POST "$DASHBOARD_URL/demo/reset" >/dev/null

echo
echo "ResearchOS demo is ready."
echo "Dashboard: $DASHBOARD_URL"
echo "Health:    $HEALTH_URL"
echo

open_dashboard_if_possible || true
