#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

usage() {
  cat <<'EOF'
Usage: ./scripts/run_server.sh [options]

Run ResearchOS as a shared lab server in the foreground.

Options:
  --host HOST     Bind host. Default: HOST, RESEARCHOS_API_HOST, or 0.0.0.0
  --port PORT     Bind port. Default: PORT, RESEARCHOS_API_PORT, or 8001
  --help          Show this help.

Important environment variables:
  PUBLIC_BASE_URL              Public URL for phones/tablets/laptops, e.g. https://researchos.lab.edu
  MICROSOFT_REDIRECT_URI        Must match the public callback URL for OneNote auth
  DATA_DIR                      Base data directory for local server state
  RESEARCHOS_DATABASE_URL       SQLite database URL
  RESEARCHOS_CHROMA_PERSIST_DIRECTORY
  AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL

Examples:
  ./scripts/run_server.sh --host 0.0.0.0 --port 8001
  PUBLIC_BASE_URL=https://researchos.example.edu ./scripts/run_server.sh --host 0.0.0.0 --port 8001
EOF
}

HOST_VALUE="${HOST:-${RESEARCHOS_API_HOST:-0.0.0.0}}"
PORT_VALUE="${PORT:-${RESEARCHOS_API_PORT:-8001}}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      HOST_VALUE="${2:?Missing value for --host}"
      shift 2
      ;;
    --port)
      PORT_VALUE="${2:?Missing value for --port}"
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

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "Missing backend virtual environment: $BACKEND_DIR/.venv" >&2
  echo "Create it with: cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

cd "$BACKEND_DIR"
source .venv/bin/activate

export RESEARCHOS_API_HOST="$HOST_VALUE"
export RESEARCHOS_API_PORT="$PORT_VALUE"

echo "Starting ResearchOS lab server"
echo "Bind:          $HOST_VALUE:$PORT_VALUE"
echo "Dashboard:     ${PUBLIC_BASE_URL:-http://$HOST_VALUE:$PORT_VALUE}"
echo "Health:        ${PUBLIC_BASE_URL:-http://$HOST_VALUE:$PORT_VALUE}/health"
echo "Deployment:    ${PUBLIC_BASE_URL:-http://$HOST_VALUE:$PORT_VALUE}/status/deployment"
echo
echo "Use HTTPS and PUBLIC_BASE_URL for shared lab/mobile access."
echo

exec python -m uvicorn app.main:app --host "$HOST_VALUE" --port "$PORT_VALUE"
