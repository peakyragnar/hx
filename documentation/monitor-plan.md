# Heretix Monitoring Plan (Simplicity First)

We keep the Elon-style bias for minimal tooling: smallest surface that still tells us when something breaks or drifts.

## Core Signals to Watch

- **Edge uptime** — Ping both front door (Render static site) and API (Render) and alert if either stays down >3 minutes.
- **Failure rates** — Track 4xx/5xx spikes from Render logs/metrics and client-side error reporting; page only on sustained 5xx.
- **Database health** — Let Neon warn on storage/connection thresholds; run a tiny script that checks `SELECT count(*) FROM runs;` and replication lag (if replicas).
- **Cache/queue** — For now, confirm the local SQLite file exists and is growing; when moving to Redis/SQS, add a single backlog length alert.
- **Backups & recovery** — Monthly Neon PITR restore smoke test + nightly SQLite snapshot with failure alerts.
- **Security sanity** — Render deploy hooks, GitHub branch protection, API key rotation reminder, audit log review quarterly.

## Build Plan

1. **Uptime checks**
   - Pick a service (Pingdom, UptimeRobot, or Render native).
   - Add two monitors: Render UI URL and Render API health endpoint.
   - Set notification target (email/Slack) for >3 minute downtime.

2. **Error-rate visibility**
   - Enable Render metrics for HTTP status distribution; configure alert on 5xx >2% over 5 minutes.
   - Add client-side error reporting (e.g., Sentry) for UI runtime failures.
   - Pipe alerts to same notification channel for consistency.

3. **Database guardrails**
   - In Neon console, set storage + connection thresholds (e.g., 70% usage).
   - Write a `scripts/check_db_health.py` that:
     - Runs `SELECT count(*) FROM runs;`
     - (If replicas) queries `pg_last_wal_replay_lsn()` to gauge lag.
     - Emits warning if counts flatline for >24h or lag >30s.
   - Schedule the script via Render cron or GitHub Actions daily.

4. **Cache/queue check**
   - Add a cron job that ensures `runs/heretix.sqlite` exists and file size changes weekly.
   - When migrating to Redis/SQS, extend the same script to check queue length and alert if >N (e.g., 100 jobs).

5. **Backups & recovery**
   - Configure Neon PITR snapshot download + restore dry-run monthly (store logs in S3/GCS bucket).
   - Create nightly job that copies `runs/heretix.sqlite` to a dated archive; alert on failure.

6. **Security housekeeping**
   - Enable Render deploy hooks → push notifications on production deploys.
   - Confirm GitHub branch protection (main requires PR + CI).
   - Add quarterly calendar reminder to rotate OPENAI_API_KEY, Neon credentials, and review Render audit logs.

## Automation Helpers

- `scripts/check_db_health.py`: connects to Neon via `DATABASE_URL_PROD` (or `DATABASE_URL`) and prints counts for `checks`, `result_cache`, and `usage_ledger`.
- `scripts/check_postmark.sh`: HEAD-style heartbeat against Postmark using `POSTMARK_TOKEN`.
- `scripts/check_openai.py`: fetches OpenAI model metadata (default `gpt-5`) using `OPENAI_API_KEY`.
- `scripts/run_monitor_checks.sh`: convenience wrapper that sources `.env.monitor` (if present), runs both checks, and appends output to `runs/monitoring/monitor.log`. Exit code is non-zero if either check fails—perfect for cron/UptimeRobot.

### Suggested Cron (macOS/Linux)
1. Create `.env.monitor` at repo root:
   ```
   DATABASE_URL_PROD=postgresql://user:pass@host/db?sslmode=require
   POSTMARK_TOKEN=server-token
   OPENAI_API_KEY=sk-live...
   HERETIX_OPENAI_HEALTH_MODEL=gpt-5  # optional override
   ```
2. Add cron entry (`crontab -e`):
   ```
   */30 * * * * cd /Users/michael/Heretix && /Users/michael/Heretix/scripts/run_monitor_checks.sh || mail -s "Heretix monitor failure" you@example.com
   ```
   Adjust cadence, path, and notification channel as desired.

## Operating Cadence

- **Daily** — Review any uptime or error alerts; scan Run database count from automated report.
- **Weekly** — Verify no backlog alerts; skim Render dashboards.
- **Monthly** — Check Neon restore log; confirm backups succeeded.
- **Quarterly** — Rotate keys, review audit logs, sanity-check monitoring coverage.

This plan keeps tooling minimal while guaranteeing we notice availability issues, failure spikes, data-store pressure, backup failures, or security drift.
