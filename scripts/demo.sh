#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${RESEARCHOS_DEV_PORT:-8001}}"
HOST="${HOST:-${RESEARCHOS_DEV_HOST:-127.0.0.1}}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-${RESEARCHOS_PUBLIC_BASE_URL:-}}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT_DIR/.researchos-dev.log"
CHECKLIST_PATH="$ROOT_DIR/docs/DEMO_CHECKLIST.md"
IT_APPROVAL_PATH="$ROOT_DIR/docs/UCSD_IT_APPROVAL_REQUEST.md"

usage() {
  cat <<'EOF'
Usage: ./scripts/demo.sh [options]

Start/restart the ResearchOS demo backend and load demo data.

Options:
  --host HOST              Bind host. Default: HOST, RESEARCHOS_DEV_HOST, or 127.0.0.1
  --port PORT              Bind port. Default: PORT, RESEARCHOS_DEV_PORT, or 8001
  --public-base-url URL    URL phones/tablets should use, e.g. http://192.168.1.25:8001
  --help                   Show this help.

Examples:
  ./scripts/demo.sh
  HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://192.168.1.25:8001 ./scripts/demo.sh
  ./scripts/demo.sh --host 0.0.0.0 --port 8001 --public-base-url http://192.168.1.25:8001
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      HOST="${2:?Missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?Missing value for --port}"
      shift 2
      ;;
    --public-base-url)
      PUBLIC_BASE_URL="${2:?Missing value for --public-base-url}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

first_lan_ip() {
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
    return 0
  fi
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1
  fi
}

LOCAL_HOST="$HOST"
if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  LOCAL_HOST="127.0.0.1"
fi

if [ -z "$PUBLIC_BASE_URL" ] && { [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; }; then
  LAN_IP="$(first_lan_ip || true)"
  if [ -n "$LAN_IP" ]; then
    PUBLIC_BASE_URL="http://$LAN_IP:$PORT"
  fi
fi

export HOST
export PORT
if [ -n "$PUBLIC_BASE_URL" ]; then
  export PUBLIC_BASE_URL
  export RESEARCHOS_PUBLIC_BASE_URL="$PUBLIC_BASE_URL"
fi

HEALTH_URL="http://$LOCAL_HOST:$PORT/health"
DASHBOARD_URL="http://$LOCAL_HOST:$PORT"
BIND_URL="http://$HOST:$PORT"
MOBILE_URL="${PUBLIC_BASE_URL:-}"

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
echo "Bind address: $HOST:$PORT"
if [ -n "$MOBILE_URL" ]; then
  echo "Mobile/network URL: $MOBILE_URL"
elif [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  echo "Mobile/network URL: set PUBLIC_BASE_URL=http://<your-ip>:$PORT for phones/tablets."
fi
"$ROOT_DIR/scripts/restart.sh"
wait_for_health

echo "Loading demo lab notes ..."
curl -fsS -X POST "$DASHBOARD_URL/demo/reset" >/dev/null

echo "Loading sample literature if available ..."
curl -fsS -X POST "$DASHBOARD_URL/ingest/papers" >/dev/null || true

echo
echo "ResearchOS demo is ready."
echo "Dashboard:      $DASHBOARD_URL"
echo "Health:         $HEALTH_URL"
echo "Bind:           $BIND_URL"
if [ -n "$MOBILE_URL" ]; then
  echo "Mobile/PWA:     $MOBILE_URL"
else
  echo "Mobile/PWA:     set PUBLIC_BASE_URL and HOST=0.0.0.0 for device testing"
fi
echo "Demo checklist: $CHECKLIST_PATH"
echo "UCSD IT doc:    $IT_APPROVAL_PATH"
echo
echo "Suggested questions:"
echo "  1. Which experiments used SAG?"
echo "  2. Compare our SAG experiments with the literature."
echo "  3. Do our SIX6/BRN3B results match published expectations?"
echo

open_dashboard_if_possible || true
