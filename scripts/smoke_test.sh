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
request GET "/" >/dev/null
request GET "/service-worker.js" >/dev/null
request GET "/frontend-assets/manifest.webmanifest" >/dev/null
request GET "/auth/status" >/dev/null
request GET "/auth/me" >/dev/null
request GET "/auth/permissions" >/dev/null
request GET "/auth/readiness" >/dev/null
request GET "/users" >/dev/null
request GET "/workspaces" >/dev/null
SMOKE_WORKSPACE_ID="workspace:smoke-$(date +%s)"
request POST "/workspaces" "{\"workspace_id\":\"$SMOKE_WORKSPACE_ID\",\"name\":\"Smoke Test Lab\",\"description\":\"Smoke test workspace\",\"default_role\":\"researcher\"}" >/dev/null
request POST "/workspaces/bootstrap-default" "{}" >/dev/null
request GET "/workspaces/current" >/dev/null
request POST "/workspaces/current" '{"workspace_id":"workspace:demo-lab"}' >/dev/null
request GET "/workspaces/workspace:demo-lab/members" >/dev/null
request POST "/workspaces/workspace:demo-lab/members" '{"user_id":"user:dev-local","role":"admin"}' >/dev/null
request GET "/status/deployment" >/dev/null
request GET "/status/onenote-readiness" >/dev/null
request GET "/status/production-readiness" >/dev/null
request GET "/status/automation" >/dev/null
request GET "/agents" >/dev/null
request GET "/extensions" >/dev/null
request GET "/extensions/builtin.graphpad" >/dev/null
request POST "/extensions/builtin.graphpad/disable" "{}" >/dev/null
request POST "/extensions/builtin.graphpad/enable" "{}" >/dev/null
request GET "/mobile/status" >/dev/null
request GET "/mobile/auth/me" >/dev/null
request GET "/mobile/settings" >/dev/null
request GET "/mobile/dashboard" >/dev/null
request GET "/api/dashboard/daily?use_ai=false" >/dev/null
request GET "/demo/status" >/dev/null
request POST "/demo/reset" "{}" >/dev/null
request GET "/documents" >/dev/null
request GET "/documents?workspace_id=workspace:demo-lab" >/dev/null
EXPERIMENTS_FILE="$(request GET "/experiments")"
request GET "/experiments?workspace_id=workspace:demo-lab" >/dev/null
request GET "/mobile/experiments" >/dev/null
WIZARD_EXPERIMENT_ID="SMOKE-WIZARD-$(date +%s)"
WIZARD_FILE="$(request POST "/mobile/experiments/create" "{\"title\":\"Smoke Wizard Experiment\",\"experiment_id\":\"$WIZARD_EXPERIMENT_ID\",\"project\":\"Smoke test\",\"researcher\":\"ResearchOS\",\"protocol_mode\":\"create_new\",\"protocol_title\":\"Smoke protocol\",\"cell_line\":\"Demo cells\",\"organoid_batch\":\"Demo batch\",\"compounds\":[\"SAG\"],\"concentrations\":[\"100 nM\"],\"timepoints\":[\"D1\"],\"replicates\":\"n=3\",\"controls\":[\"DMSO\"],\"readouts\":[\"microscopy\"],\"markers\":[\"SIX6\"],\"microscopy\":true,\"graphpad\":true,\"create_notebook_draft\":true,\"start_session\":false}")"
WIZARD_INTERNAL_ID="$(
  python3 - "$WIZARD_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["experiment"]["id"])
PY
)"
request GET "/mobile/experiments/$WIZARD_INTERNAL_ID/workspace" >/dev/null
WORKFLOWS_FILE="$(request GET "/workflows")"
request GET "/workflows?workspace_id=workspace:demo-lab" >/dev/null
request GET "/workflows/definitions" >/dev/null
request GET "/protocols" >/dev/null
request GET "/sessions" >/dev/null
request GET "/sessions?workspace_id=workspace:demo-lab" >/dev/null
request GET "/mobile/sessions" >/dev/null
request GET "/mobile/sessions/active" >/dev/null
SESSION_FILE="$(request POST "/sessions/start" '{"experiment_id":"SMOKE_SESSION","notes":"Smoke test session started."}')"
SESSION_ID="$(
  python3 - "$SESSION_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["session_id"])
PY
)"
request POST "/sessions/$SESSION_ID/events" '{"event_type":"observation","title":"Smoke observation","content":"Session timeline smoke test."}' >/dev/null
request GET "/sessions/$SESSION_ID/timeline" >/dev/null
request POST "/sessions/$SESSION_ID/end" '{"notes":"Smoke test session ended."}' >/dev/null
MOBILE_SESSION_FILE="$(request POST "/mobile/sessions/start" '{"experiment_id":"SMOKE_MOBILE_SESSION","notes":"Mobile smoke test session started."}')"
MOBILE_SESSION_ID="$(
  python3 - "$MOBILE_SESSION_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["session_id"])
PY
)"
request POST "/mobile/sessions/$MOBILE_SESSION_ID/note" '{"note_type":"observation","text":"Mobile smoke observation."}' >/dev/null
request POST "/mobile/sessions/$MOBILE_SESSION_ID/observation" '{"text":"Bench Mode observation smoke test."}' >/dev/null
request POST "/mobile/sessions/$MOBILE_SESSION_ID/treatment" '{"compound":"SAG","dose":"100","units":"nM","time":"D32","notes":"Bench Mode treatment smoke test."}' >/dev/null
request POST "/mobile/sessions/$MOBILE_SESSION_ID/media-change" '{"media_type":"retinal differentiation medium","notes":"Bench Mode media change smoke test."}' >/dev/null
request POST "/mobile/sessions/$MOBILE_SESSION_ID/voice-note" '{"transcript":"Bench Mode voice placeholder smoke test.","placeholder":true}' >/dev/null
request POST "/mobile/sessions/$MOBILE_SESSION_ID/attach-placeholder" '{"attachment_type":"image","title":"Bench Mode image placeholder","notes":"Camera capture not implemented yet."}' >/dev/null
request POST "/mobile/sessions/$MOBILE_SESSION_ID/end" '{"notes":"Mobile smoke session ended."}' >/dev/null
request GET "/providers/graphpad/status" >/dev/null
request POST "/providers/graphpad/scan" "{}" >/dev/null
request GET "/providers/images/status" >/dev/null
request POST "/providers/images/scan" "{}" >/dev/null
request GET "/providers/spreadsheets/status" >/dev/null
request POST "/providers/spreadsheets/scan" "{}" >/dev/null
request GET "/experiments/NK_Expt_31/workspace?use_ai=false" >/dev/null
request GET "/mobile/experiments/NK_Expt_31/workspace" >/dev/null
request GET "/experiments/NK_Expt_31/quantification?use_ai=false" >/dev/null
request GET "/mobile/experiments/NK_Expt_31/quantification" >/dev/null
SPREADSHEETS_FILE="$(request GET "/spreadsheets")"
request GET "/spreadsheets?workspace_id=workspace:demo-lab" >/dev/null
IMAGES_FILE="$(request GET "/images")"
request GET "/images?workspace_id=workspace:demo-lab" >/dev/null
STATISTICS_FILE="$(request GET "/statistics")"
request GET "/statistics?workspace_id=workspace:demo-lab" >/dev/null
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
request GET "/statistics/$GRAPH_PAD_STAT_ASSET_ID/compact-summary" >/dev/null
request GET "/statistics/$GRAPH_PAD_STAT_ASSET_ID/interpretation" >/dev/null
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
request GET "/spreadsheets/$SPREADSHEET_ASSET_ID/compact-summary" >/dev/null
request GET "/spreadsheets/$SPREADSHEET_ASSET_ID/download" >/dev/null
request GET "/assets" >/dev/null
request GET "/assets?workspace_id=workspace:demo-lab" >/dev/null
SMOKE_RESOURCE_FILE="$(request POST "/resources" '{"resource_type":"compound","name":"Smoke SAG Resource","aliases":["Smoke Smoothened agonist"],"vendor":"ResearchOS","catalog_number":"SAG-SMOKE","lot_number":"LOT-SMOKE","storage_location":"Demo freezer","concentration":"100","units":"nM","notes":"Smoke test resource."}')"
SMOKE_RESOURCE_ID="$(
  python3 - "$SMOKE_RESOURCE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["resource_id"])
PY
)"
request GET "/resources" >/dev/null
request GET "/resources/type/compound" >/dev/null
request GET "/resources/$SMOKE_RESOURCE_ID" >/dev/null
request PUT "/resources/$SMOKE_RESOURCE_ID" '{"resource_type":"compound","name":"Smoke SAG Resource","aliases":["Smoke Smoothened agonist","Smoke SAG"],"vendor":"ResearchOS","catalog_number":"SAG-SMOKE","lot_number":"LOT-SMOKE-2","storage_location":"Demo freezer","concentration":"100","units":"nM","notes":"Updated smoke test resource."}' >/dev/null
SMOKE_INVENTORY_FILE="$(request POST "/inventory" "{\"name\":\"Smoke SAG Inventory\",\"category\":\"compound\",\"vendor\":\"ResearchOS\",\"catalog_number\":\"SAG-SMOKE\",\"lot_number\":\"LOT-SMOKE\",\"rrid\":\"RRID:SMOKE\",\"price\":125.5,\"unit\":\"vial\",\"storage_location\":\"Demo freezer\",\"quantity\":1,\"reorder_threshold\":2,\"expiration_date\":\"2027-01-01\",\"linked_resource_id\":\"$SMOKE_RESOURCE_ID\",\"notes\":\"Smoke inventory item.\"}")"
SMOKE_INVENTORY_ID="$(
  python3 - "$SMOKE_INVENTORY_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["item_id"])
PY
)"
request GET "/inventory" >/dev/null
request GET "/inventory/$SMOKE_INVENTORY_ID" >/dev/null
request GET "/inventory/$SMOKE_INVENTORY_ID/methods-citation" >/dev/null
request PUT "/inventory/$SMOKE_INVENTORY_ID" '{"name":"Smoke SAG Inventory","category":"compound","vendor":"ResearchOS","catalog_number":"SAG-SMOKE","lot_number":"LOT-SMOKE-2","quantity":3,"reorder_threshold":1}' >/dev/null
request GET "/inventory/export-csv" >/dev/null
SMOKE_PURCHASE_FILE="$(request POST "/purchases" '{"item_name":"Smoke SAG Purchase","vendor":"ResearchOS","catalog_number":"SAG-SMOKE","purchase_date":"2026-07-08","cost":125.5,"quantity":1,"grant_or_funding_source":"Smoke Grant","purchaser":"ResearchOS","oracle_po_number":"PO-SMOKE","invoice_number":"INV-SMOKE","status":"ordered","notes":"Smoke purchase."}')"
SMOKE_PURCHASE_ID="$(
  python3 - "$SMOKE_PURCHASE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["purchase_id"])
PY
)"
request GET "/purchases" >/dev/null
request GET "/purchases/$SMOKE_PURCHASE_ID" >/dev/null
request PUT "/purchases/$SMOKE_PURCHASE_ID" '{"item_name":"Smoke SAG Purchase","vendor":"ResearchOS","catalog_number":"SAG-SMOKE","purchase_date":"2026-07-08","cost":130,"quantity":2,"grant_or_funding_source":"Smoke Grant","purchaser":"ResearchOS","oracle_po_number":"PO-SMOKE","invoice_number":"INV-SMOKE","status":"received","notes":"Updated smoke purchase."}' >/dev/null
request POST "/purchases/import-csv" '{"csv_text":"PO Number,Supplier,Item,Amount,Grant,Buyer\nPO-SMOKE-CSV,ResearchOS,Smoke CSV Item,44.00,Smoke Grant,ResearchOS\n"}' >/dev/null
request POST "/purchases/import-preview" '{"csv_text":"Item Description,Supplier,Catalog #,Order Date,Total Cost,Qty,Project/Grant,Requester,PO Number,Invoice Number,Status\nSmoke Mapped Item,ResearchOS,MAP-1,2026-07-08,55.00,1,Smoke Grant,ResearchOS,PO-SMOKE-MAP,INV-MAP,received\n"}' >/dev/null
request POST "/purchases/import-mapped-csv" '{"csv_text":"Item Description,Supplier,Catalog #,Order Date,Total Cost,Qty,Project/Grant,Requester,PO Number,Invoice Number,Status\nSmoke Mapped Item,ResearchOS,MAP-1,2026-07-08,55.00,1,Smoke Grant,ResearchOS,PO-SMOKE-MAP,INV-MAP,received\n","mapping":{"item_name":"Item Description","vendor":"Supplier","catalog_number":"Catalog #","purchase_date":"Order Date","cost":"Total Cost","quantity":"Qty","grant_or_funding_source":"Project/Grant","purchaser":"Requester","oracle_po_number":"PO Number","invoice_number":"Invoice Number","status":"Status"}}' >/dev/null
request GET "/purchases/import-templates" >/dev/null
request POST "/purchases/import-templates" '{"name":"Smoke Oracle Mapping","mapping":{"item_name":"Item Description","vendor":"Supplier","oracle_po_number":"PO Number"},"provider":"oracle_purchasing"}' >/dev/null
request GET "/purchases/export-csv" >/dev/null
request GET "/papers" >/dev/null
request GET "/papers?workspace_id=workspace:demo-lab" >/dev/null
request GET "/graph/stats" >/dev/null
request GET "/search/universal?q=SAG" >/dev/null
request GET "/mobile/search?q=SAG" >/dev/null
request GET "/knowledgegraph" >/dev/null
request GET "/knowledgegraph?workspace_id=workspace:demo-lab" >/dev/null
request GET "/knowledgegraph/search?q=SAG" >/dev/null
request GET "/knowledgegraph/entity/SAG" >/dev/null
request GET "/knowledgegraph/type/marker" >/dev/null
INTELLIGENCE_FILE="$(request GET "/intelligence/feed")"
request GET "/mobile/intelligence/feed" >/dev/null
INTELLIGENCE_ITEM_ID="$(
  python3 - "$INTELLIGENCE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)

items = payload.get("items") or []
if not items:
    raise SystemExit("Need at least one Laboratory Intelligence item for smoke test.")

print(items[0]["item_id"])
PY
)"
request POST "/intelligence/feed/$INTELLIGENCE_ITEM_ID/pin" '{"pinned":true}' >/dev/null
request POST "/mobile/intelligence/feed/$INTELLIGENCE_ITEM_ID/dismiss" '{}' >/dev/null
request GET "/intelligence/morning" >/dev/null
request GET "/intelligence/morning?period=yesterday" >/dev/null
request GET "/intelligence/morning?period=last_week" >/dev/null
request GET "/mobile/intelligence/morning" >/dev/null
request GET "/memory" >/dev/null
request GET "/entry-templates" >/dev/null
request POST "/entries/draft" '{"template":"retinal_organoid","dictation":"Create NK Expt 31. Date today. Researcher Nathan. D18 SAG plus GRKi rescue with 100 nM SAG and 250 nM GRK inhibitor. DMSO control. Readouts SIX6 and BRN3B. Next steps quantify SIX6 intensity.","use_ai":false}' >/dev/null
SAVED_ENTRY_FILE="$(request POST "/entries/save-draft" '{"title":"Smoke Test Pending Entry","experiment_id":"SMOKE-ENTRY-1","template":"general_experiment","structured":{"title":"Smoke Test Pending Entry","experiment_id":"SMOKE-ENTRY-1"},"markdown":"# Smoke Test Pending Entry\n\nLocal pending entry smoke test.","status":"draft"}')"
request GET "/entries" >/dev/null
request GET "/entries?workspace_id=workspace:demo-lab" >/dev/null
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
MEMORY_BODY="$(
  python3 - "$FIRST_EXPERIMENT_ID" <<'PY'
import json
import sys

print(json.dumps({"experiment_id": sys.argv[1], "limit": 3}))
PY
)"
request GET "/memory/experiment/$FIRST_EXPERIMENT_ID" >/dev/null
request POST "/memory/similar" "$MEMORY_BODY" >/dev/null
request GET "/mobile/experiments/$FIRST_EXPERIMENT_ID" >/dev/null
request GET "/mobile/experiments/$FIRST_EXPERIMENT_ID/timeline" >/dev/null
request GET "/mobile/experiments/$FIRST_EXPERIMENT_ID/workspace" >/dev/null
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
request GET "/experiments/$FIRST_EXPERIMENT_ID/lifecycle" >/dev/null
WORKFLOW_ID="$(
  python3 - "$WORKFLOWS_FILE" "$FIRST_EXPERIMENT_ID" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    workflows = json.load(handle)

for workflow in workflows:
    if workflow.get("subject_id") == sys.argv[2]:
        print(workflow["workflow_id"])
        break
else:
    print(f"workflow:experiment:{sys.argv[2]}")
PY
)"
request GET "/workflows/$WORKFLOW_ID" >/dev/null
request GET "/workflows/experiment/$FIRST_EXPERIMENT_ID" >/dev/null
request POST "/workflows/$WORKFLOW_ID/note" '{"note":"Smoke test workflow note.","actor":"smoke_test"}' >/dev/null
request GET "/experiments/$FIRST_EXPERIMENT_ID/timeline" >/dev/null
request GET "/experiments/$FIRST_EXPERIMENT_ID/workspace?use_ai=false" >/dev/null
request GET "/knowledgegraph/experiment/$FIRST_EXPERIMENT_ID" >/dev/null
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
request POST "/evidence/query" '{"question":"Does early SAG improve retinal differentiation?"}' >/dev/null
request POST "/assistant/knowledge" '{"question":"What do we know about SAG?","use_ai":false}' >/dev/null
request POST "/assistant/reason" '{"question":"Which experiments involve BRN3B?","use_ai":false}' >/dev/null
request GET "/mobile/knowledge/entity/SAG" >/dev/null
request POST "/mobile/assistant/ask" '{"message":"Which experiments used SAG?","use_ai":false}' >/dev/null
request POST "/mobile/assistant/copilot" '{"question":"What do we know about SAG?","use_ai":false}' >/dev/null

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
