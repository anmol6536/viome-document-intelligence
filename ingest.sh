#!/usr/bin/env bash
# Forward an already-succeeded extraction job's result to the gateway's
# ingest endpoint. Separate from the main pipeline on purpose - this
# service's output is not always destined for the gateway, so ingestion
# is a manual, opt-in step rather than something the worker does
# automatically for every job.
#
# Usage:
#   ./ingest.sh <job_id> [viome_user_id] [gateway_url] [api_base_url]
#
# Defaults:
#   viome_user_id = test-user-1  (must match the X-Viome-User-Id used when
#                                  the job was submitted, since that's what
#                                  ended up in the resource's subject.reference)
#   gateway_url   = ${GATEWAY_URL:-http://localhost:9000/ingest}  (placeholder -
#                    not yet a real, confirmed endpoint)
#   api_base_url  = http://localhost:8020  (this service's own API)

set -euo pipefail

JOB_ID="${1:?Usage: ./ingest.sh <job_id> [viome_user_id] [gateway_url] [api_base_url]}"
VIOME_USER_ID="${2:-test-user-1}"
GATEWAY_URL="${3:-${GATEWAY_URL:-http://localhost:9000/ingest}}"
API_BASE_URL="${4:-http://localhost:8020}"

STATUS_JSON=$(curl -s "$API_BASE_URL/extractions/$JOB_ID")
STATUS=$(echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")

if [ "$STATUS" != "succeeded" ]; then
  echo "Job $JOB_ID is not succeeded (status: $STATUS) - nothing to ingest." >&2
  echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))" >&2
  exit 1
fi

RESOURCE=$(echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['result']))")

echo "Ingesting job $JOB_ID (Viome user $VIOME_USER_ID) into $GATEWAY_URL ..."
curl -s -X POST "$GATEWAY_URL" \
  -H "Content-Type: application/json" \
  -H "X-EHR-Provider: viome-document-intelligence" \
  -H "X-Viome-User-ID: $VIOME_USER_ID" \
  -d "$RESOURCE" \
  -w "\nHTTP_STATUS:%{http_code}\n"
