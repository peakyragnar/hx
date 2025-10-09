#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.monitor"
LOG_DIR="${ROOT_DIR}/runs/monitoring"
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# Ensure uvx/httpx binaries are discoverable when running via cron.
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

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

UVX_BIN="${UVX_BIN:-$(command -v uvx || true)}"
if [[ -z "${UVX_BIN}" ]]; then
  log "uvx not found in PATH"
  exit 10
fi

cd "${ROOT_DIR}"

if ! "${UVX_BIN}" --with psycopg[binary] python scripts/check_db_health.py >> "${LOG_FILE}" 2>&1; then
  log "DB health check FAILED"
  exit 1
fi

if ! "${ROOT_DIR}/scripts/check_postmark.sh" >> "${LOG_FILE}" 2>&1; then
  log "Postmark heartbeat FAILED"
  exit 2
fi

if ! "${UVX_BIN}" --with httpx python scripts/check_openai.py >> "${LOG_FILE}" 2>&1; then
  log "OpenAI heartbeat FAILED"
  exit 3
fi

log "Monitor checks passed"
