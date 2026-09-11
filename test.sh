#!/usr/bin/env bash
# Submit a lab report file to the /extractions API and poll until it finishes.
#
# Usage:
#   ./test.sh [file] [schema_id] [base_url]
#
# Defaults:
#   file      = data/Result Trends - LIPID PANEL - Aug 4, 2026.PDF
#   schema_id = multi_observation
#   base_url  = http://localhost:8020

set -euo pipefail

FILE="${1:-data/Result Trends - LIPID PANEL - Aug 4, 2026.PDF}"
SCHEMA_ID="${2:-multi_observation}"
BASE_URL="${3:-http://localhost:8020}"
USER_ID="${X_VIOME_USER_ID:-test-user-1}"

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

echo "Submitting $FILE (schema_id=$SCHEMA_ID) to $BASE_URL ..."
RESPONSE=$(curl -s -X POST "$BASE_URL/extractions" \
  -H "X-Viome-User-Id: $USER_ID" \
  -F "file=@${UPLOAD_PATH};type=application/pdf" \
  -F "schema_id=${SCHEMA_ID}")

JOB_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['job_id'])")
echo "job_id=$JOB_ID"

echo "Polling for a terminal status..."
while true; do
  STATUS_JSON=$(curl -s "$BASE_URL/extractions/$JOB_ID")
  STATUS=$(echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 3
done

echo "$STATUS_JSON" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))"

if [ "$UPLOAD_PATH" != "$FILE" ]; then
  rm -f "$UPLOAD_PATH"
fi
