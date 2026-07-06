#!/usr/bin/env bash
set -euo pipefail

PORT="${RESEARCHOS_DEV_PORT:-8001}"
HOST="${RESEARCHOS_DEV_HOST:-127.0.0.1}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT_DIR/.researchos-dev.log"
HEALTH_URL="http://$HOST:$PORT/health"

"$ROOT_DIR/scripts/stop.sh"
"$ROOT_DIR/scripts/start.sh"

echo "Waiting for ResearchOS health check at $HEALTH_URL ..."
for _ in $(seq 1 15); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "ResearchOS backend is healthy at $HEALTH_URL"
    exit 0
  fi
  sleep 1
done

echo "ResearchOS backend did not become healthy within 15 seconds."
if [ -f "$LOG_FILE" ]; then
  echo "Last 80 lines of $LOG_FILE:"
  tail -n 80 "$LOG_FILE"
else
  echo "Log file not found: $LOG_FILE"
fi

exit 1
