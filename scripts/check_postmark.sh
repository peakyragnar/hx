#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${POSTMARK_TOKEN:-}" ]]; then
  echo "POSTMARK_TOKEN not set" >&2
  exit 1
fi

endpoint="https://api.postmarkapp.com/server"
if curl -sf -H "X-Postmark-Server-Token: ${POSTMARK_TOKEN}" "${endpoint}" >/dev/null; then
  printf "%s Postmark OK\n" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
else
  printf "%s Postmark check failed\n" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >&2
  exit 2
fi
