#!/usr/bin/env bash
set -euo pipefail

PORT="${RESEARCHOS_DEV_PORT:-8001}"
HOST="${RESEARCHOS_DEV_HOST:-127.0.0.1}"
BASE_URL="${RESEARCHOS_BASE_URL:-http://$HOST:$PORT}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

pass() {
  echo "PASS $1" >&2
}

request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local output="$TMP_DIR/$(echo "$path" | tr '/:' '__').json"

  if [ "$method" = "GET" ]; then
    curl -fsS "$BASE_URL$path" > "$output"
  else
    curl -fsS -X "$method" "$BASE_URL$path" \
      -H "Content-Type: application/json" \
      -d "$body" > "$output"
  fi

  test -s "$output"
  pass "$method $path"
  printf "%s" "$output"
}

echo "Running ResearchOS smoke test against $BASE_URL"

request GET "/health" >/dev/null
request GET "/demo/status" >/dev/null
request POST "/demo/reset" "{}" >/dev/null
request GET "/documents" >/dev/null
EXPERIMENTS_FILE="$(request GET "/experiments")"
request GET "/providers/graphpad/status" >/dev/null
request POST "/providers/graphpad/scan" "{}" >/dev/null
request GET "/providers/images/status" >/dev/null
request POST "/providers/images/scan" "{}" >/dev/null
request GET "/providers/spreadsheets/status" >/dev/null
request POST "/providers/spreadsheets/scan" "{}" >/dev/null
SPREADSHEETS_FILE="$(request GET "/spreadsheets")"
IMAGES_FILE="$(request GET "/images")"
STATISTICS_FILE="$(request GET "/statistics")"
GRAPH_PAD_STAT_ASSET_ID="$(
  python3 - "$STATISTICS_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    assets = json.load(handle)

if not assets:
    raise SystemExit("Need at least one parsed GraphPad statistics asset.")

print(assets[0]["asset_id"])
PY
)"
request GET "/providers/graphpad/assets/$GRAPH_PAD_STAT_ASSET_ID/summary" >/dev/null
SPREADSHEET_ASSET_ID="$(
  python3 - "$SPREADSHEETS_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    assets = json.load(handle)

if not assets:
    raise SystemExit("Need at least one spreadsheet asset.")

print(assets[0]["asset_id"])
PY
)"
request GET "/spreadsheets/$SPREADSHEET_ASSET_ID" >/dev/null
request GET "/spreadsheets/$SPREADSHEET_ASSET_ID/summary" >/dev/null
request GET "/spreadsheets/$SPREADSHEET_ASSET_ID/download" >/dev/null
request GET "/assets" >/dev/null
request GET "/papers" >/dev/null
request GET "/graph/stats" >/dev/null
request GET "/entry-templates" >/dev/null
request POST "/entries/draft" '{"template":"retinal_organoid","dictation":"Create NK Expt 31. Date today. Researcher Nathan. D18 SAG plus GRKi rescue with 100 nM SAG and 250 nM GRK inhibitor. DMSO control. Readouts SIX6 and BRN3B. Next steps quantify SIX6 intensity.","use_ai":false}' >/dev/null
SAVED_ENTRY_FILE="$(request POST "/entries/save-draft" '{"title":"Smoke Test Pending Entry","experiment_id":"SMOKE-ENTRY-1","template":"general_experiment","structured":{"title":"Smoke Test Pending Entry","experiment_id":"SMOKE-ENTRY-1"},"markdown":"# Smoke Test Pending Entry\n\nLocal pending entry smoke test.","status":"draft"}')"
request GET "/entries" >/dev/null
SAVED_ENTRY_ID="$(
  python3 - "$SAVED_ENTRY_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["id"])
PY
)"
request GET "/entries/$SAVED_ENTRY_ID" >/dev/null
request GET "/entries/$SAVED_ENTRY_ID/markdown" >/dev/null
request GET "/entries/$SAVED_ENTRY_ID/download" >/dev/null
request DELETE "/entries/$SAVED_ENTRY_ID" >/dev/null

FIRST_EXPERIMENT_ID="$(
  python3 - "$EXPERIMENTS_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    experiments = json.load(handle)

if not experiments:
    raise SystemExit("Need at least one experiment for asset link smoke test.")

print(experiments[0]["id"])
PY
)"
IMAGE_ASSET_ID="$(
  python3 - "$IMAGES_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    assets = json.load(handle)

for asset in assets:
    if asset.get("provider") == "microscopy":
        print(asset["asset_id"])
        break
else:
    raise SystemExit("Need at least one microscopy asset for timeline smoke test.")
PY
)"
IMAGE_LINK_BODY="$(
  python3 - "$IMAGE_ASSET_ID" "$FIRST_EXPERIMENT_ID" <<'PY'
import json
import sys

print(json.dumps({"asset_id": sys.argv[1], "experiment_id": sys.argv[2]}))
PY
)"
request POST "/assets/link" "$IMAGE_LINK_BODY" >/dev/null
request GET "/experiments/$FIRST_EXPERIMENT_ID/timeline" >/dev/null
ASSET_FILE="$(
  request POST "/assets/register" '{"asset_type":"image","title":"Smoke Test Research Asset","filename":"smoke-test-image.tif","provider":"local","path":"data/assets/smoke-test-image.tif","metadata":{"source":"smoke_test"}}'
)"
ASSET_ID="$(
  python3 - "$ASSET_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["asset_id"])
PY
)"
request GET "/assets/$ASSET_ID" >/dev/null
request GET "/assets/$ASSET_ID/links" >/dev/null
ASSET_UNRESOLVED_BODY="$(
  python3 - "$ASSET_ID" <<'PY'
import json
import sys

print(json.dumps({"asset_id": sys.argv[1], "experiment_id": "NK_Expt_31"}))
PY
)"
request POST "/assets/link" "$ASSET_UNRESOLVED_BODY" >/dev/null
request GET "/assets/$ASSET_ID/links" >/dev/null
ASSET_LINK_BODY="$(
  python3 - "$ASSET_ID" "$FIRST_EXPERIMENT_ID" <<'PY'
import json
import sys

print(json.dumps({"asset_id": sys.argv[1], "experiment_id": sys.argv[2]}))
PY
)"
request POST "/assets/link" "$ASSET_LINK_BODY" >/dev/null
request GET "/experiments" >/dev/null
request DELETE "/assets/$ASSET_ID" >/dev/null

request POST "/assistant/ask" '{"question":"Which experiments used SAG?","use_ai":false}' >/dev/null

COMPARE_BODY="$(
  python3 - "$EXPERIMENTS_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    experiments = json.load(handle)

ids = [experiment["id"] for experiment in experiments[:2]]
if len(ids) < 2:
    raise SystemExit("Need at least two experiments for /experiments/compare smoke test.")

print(json.dumps({"experiment_ids": ids, "use_ai": False}))
PY
)"
request POST "/experiments/compare" "$COMPARE_BODY" >/dev/null

echo "ResearchOS smoke test passed."
