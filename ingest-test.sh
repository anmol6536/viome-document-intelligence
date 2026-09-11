#!/usr/bin/env bash
# Submit a lab report file through this service, then forward the
# succeeded result to the gateway's ingest endpoint. A convenience
# wrapper for manually testing the full path end-to-end - the worker
# itself does NOT call the gateway automatically (this service's output
# is not always destined for the gateway).
#
# Usage:
#   ./ingest-test.sh [file] [schema_id] [viome_user_id] [api_base_url] [gateway_url]
#
# Defaults:
#   file          = data/Result Trends - LIPID PANEL - Aug 4, 2026.PDF
#   schema_id     = multi_observation
#   viome_user_id = test-user-1
#   api_base_url  = http://localhost:8020  (this service's own API)
#   gateway_url   = ${GATEWAY_URL:-http://localhost:8090/ingest}
#
# GATEWAY_BEARER_TOKEN env var overrides the demo bearer token used for
# the gateway's Authorization header (defaults to the shared demo token).

set -euo pipefail

FILE="${1:-data/Result Trends - LIPID PANEL - Aug 4, 2026.PDF}"
SCHEMA_ID="${2:-multi_observation}"
VIOME_USER_ID="${3:-Viome-User-ID-1}"
API_BASE_URL="${4:-http://localhost:8020}"
GATEWAY_URL="${5:-${GATEWAY_URL:-http://localhost:8090/ingest}}"
GATEWAY_BEARER_TOKEN="${GATEWAY_BEARER_TOKEN:-gt_demo_provider}"

if [ ! -f "$FILE" ]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

# curl's -F syntax splits "@path" on commas (it's how you attach multiple
# files to one field), so a filename containing a comma silently breaks the
# upload. Copy to a comma-free temp path before sending.
UPLOAD_PATH="$FILE"
case "$FILE" in
  *,*)
    UPLOAD_PATH="$(mktemp -t viome-upload).pdf"
    cp "$FILE" "$UPLOAD_PATH"
    ;;
esac

echo "Submitting $FILE (schema_id=$SCHEMA_ID) to $API_BASE_URL ..."
RESPONSE=$(curl -s -X POST "$API_BASE_URL/extractions" \
  -H "X-Viome-User-Id: $VIOME_USER_ID" \
  -F "file=@${UPLOAD_PATH};type=application/pdf" \
  -F "schema_id=${SCHEMA_ID}")

if [ "$UPLOAD_PATH" != "$FILE" ]; then
  rm -f "$UPLOAD_PATH"
fi

JOB_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['job_id'])")
echo "job_id=$JOB_ID"

echo "Polling for a terminal status..."
while true; do
  STATUS_JSON=$(curl -s "$API_BASE_URL/extractions/$JOB_ID")
  STATUS=$(echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 3
done

if [ "$STATUS" != "succeeded" ]; then
  echo "Job $JOB_ID did not succeed - nothing to ingest." >&2
  echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))" >&2
  exit 1
fi

RESOURCE=$(echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['result']))")

# Dump the exact payload being sent to the gateway, named by the document
# checksum already embedded in the resource (Bundle.identifier.value for
# multi_observation, Observation.identifier[0].value for lab_observation).
mkdir -p ./tmp
CHECKSUM=$(echo "$RESOURCE" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('resourceType') == 'Bundle':
    print(r['identifier']['value'])
else:
    print(r['identifier'][0]['value'])
")
PAYLOAD_PATH="./tmp/${CHECKSUM}.json"
echo "$RESOURCE" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))" > "$PAYLOAD_PATH"
echo "Gateway payload written to $PAYLOAD_PATH"

echo "Ingesting job $JOB_ID (Viome user $VIOME_USER_ID) into $GATEWAY_URL ..."
curl -s -X POST "$GATEWAY_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GATEWAY_BEARER_TOKEN" \
  -H "X-EHR-Provider: viome-document-intelligence" \
  -H "X-Viome-User-ID: $VIOME_USER_ID" \
  -d "$RESOURCE" \
  -w "\nHTTP_STATUS:%{http_code}\n"
