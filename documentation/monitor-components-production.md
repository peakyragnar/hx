# Production Monitoring Components

This is the quick reference for what’s deployed, how we watch it, and how to verify live signals.

## 1. Front Door (Vercel)
- **Surface:** `https://heretix.ai`.
- **Monitor:** UptimeRobot HTTP check (“Heretix Front Door”), 5-minute interval.
- **Alert path:** email from UptimeRobot when HTTP check fails.
- **Verification:** Check UptimeRobot dashboard or run `curl -I https://heretix.ai`.

## 2. API Service (Render)
- **Surface:** `https://api.heretix.ai`.
- **Monitor:** UptimeRobot health monitor hitting `https://api.heretix.ai/healthz`.
- **In-service health:** FastAPI `/healthz` responds to GET/HEAD with JSON `{status:"ok"}`.
- **Render notifications:** Workspace Notifications set to “Only failure notifications” (deploy or instance failures trigger email).
- **Verification:** `curl -s -o /dev/null -w "%{http_code}" https://api.heretix.ai/healthz`.

## 3. Provider Failure Signals
- **OpenAI/GPT-5:** `scripts/check_openai.py` hits `https://api.openai.com/v1/models/<model>` (default `gpt-5`) with `OPENAI_API_KEY`. Runs via cron wrapper; logs `openai_model=<id> status=ok`.
- **Postmark (magic links):** 
  - Manual subscription to https://status.postmarkapp.com (email alerts).
  - Local heartbeat script `scripts/check_postmark.sh` (invoked via cron and wrapper).

## 4. Database (Neon Postgres)
- **Conn string:** `DATABASE_URL_PROD`.
- **Health script:** `scripts/check_db_health.py` (counts `checks`, `result_cache`, `usage_ledger`; prints recovery status).
- **Automation:** `scripts/run_monitor_checks.sh` wrapper.
- **Neon console:** Manual usage review (storage, connections). Upgrade when thresholds near limits.

## 5. Logs & Aggregates
- **SQLite artifacts:** `runs/heretix.sqlite` for mock/local runs.
- **JSON outputs:** stored under `runs/`.
- **Monitor log:** `runs/monitoring/monitor.log` (appends each health check run).
- **Cron log:** `runs/monitoring/cron.log` (stdout/stderr from cron wrapper).

## 6. Cron / Scheduled Tasks
- **Crontab entry** (`crontab -l`):
  ```
  */30 * * * * cd /Users/michael/Heretix && ./scripts/run_monitor_checks.sh >> /Users/michael/Heretix/runs/monitoring/cron.log 2>&1
  ```
  - Runs every 30 minutes.
  - Loads `.env.monitor` for `DATABASE_URL_PROD` and `POSTMARK_TOKEN`.
  - On failure, cron logs non-zero exit in `cron.log` (optionally extend with mail/Slack alert).
- **Wrapper script:** `scripts/run_monitor_checks.sh`
  - Sources `.env.monitor` if present.
  - Runs `uv run python scripts/check_db_health.py`.
  - Runs `scripts/check_postmark.sh`.
  - Logs pass/fail plus detail.

### Env file used by cron
- Path: `.env.monitor` (in repo root).
- Contains:
  ```
  DATABASE_URL_PROD=postgresql://...
  POSTMARK_TOKEN=...
  OPENAI_API_KEY=...
  HERETIX_OPENAI_HEALTH_MODEL=gpt-5    # optional override
  ```
- Permissions set to `chmod 600` (recommended).

## 7. Manual Verification Steps
- `tail runs/monitoring/monitor.log`: ensure recent timestamped “Monitor checks passed”.
- `crontab -l`: confirm schedule exists.
- `uv run python scripts/check_db_health.py`: ad-hoc DB health check.
- `POSTMARK_TOKEN=... scripts/check_postmark.sh`: ad-hoc Postmark heartbeat.
- `OPENAI_API_KEY=... uv run python scripts/check_openai.py`: ad-hoc OpenAI probe.

## 8. Next Monitoring Upgrades (optional)
- Add notifier (mail/Slack) when `scripts/run_monitor_checks.sh` exits non-zero.
- Explore Vercel Observability or client-side error reporting for UI runtime exceptions.
- Introduce queue/cache length checks when Redis/SQS is adopted.
