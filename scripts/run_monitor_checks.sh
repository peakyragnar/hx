#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.monitor"
LOG_DIR="${ROOT_DIR}/runs/monitoring"
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090,SC2163
  set -a
  source "${ENV_FILE}"
  set +a
fi

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/monitor.log"

log() {
  printf "%s %s\n" "${TIMESTAMP}" "$1" | tee -a "${LOG_FILE}"
}

cd "${ROOT_DIR}"

if ! uv run python scripts/check_db_health.py >> "${LOG_FILE}" 2>&1; then
  log "DB health check FAILED"
  exit 1
fi

if ! "${ROOT_DIR}/scripts/check_postmark.sh" >> "${LOG_FILE}" 2>&1; then
  log "Postmark heartbeat FAILED"
  exit 2
fi

if ! uv run python scripts/check_openai.py >> "${LOG_FILE}" 2>&1; then
  log "OpenAI heartbeat FAILED"
  exit 3
fi

log "Monitor checks passed"
