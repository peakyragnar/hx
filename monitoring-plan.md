# Monitoring Plan

## 1. Instrumentation Scope
- Inventory every user-facing path: claim submission API/web routes, claim output rendering, async completion jobs, third-party callback/webhook handlers.
- Capture consistent context on every hop: `request_id`, `claim_id`, partner identifier, template/prompt version, timing checkpoints, error codes, payload size.

## 2. Error & Failure Logging
- Emit structured JSON logs for HTTP 4xx/5xx, provider errors, validation failures, and internal exceptions.
- Add explicit events for "claim output failure" causes (provider rejection, compliance violation, aggregation error) including retry attempt counters and root-cause tags.
- Capture client-side exceptions via browser SDK (e.g., Sentry/Rollbar) keyed by the same correlation IDs to connect front-end and back-end traces.

## 3. Latency & Throughput Metrics
- Publish histogram timers for: API request handling latency, provider time-to-first-token, total claim completion time, cache hit latency; segment by partner and template.
- Track async queue depth, oldest job age, and retry counts to surface processing delays.
- Record throughput counters (claims started/completed per minute) and external API rate-limit responses.

## 4. Usage & Experience KPIs
- Log user actions (claim submitted, result viewed, export/download) with partner metadata and feature flags for adoption analysis.
- Derive success rate = completed claims / initiated claims per partner, template, and time window.
- Instrument real user monitoring (RUM) beacons for page load metrics (LCP, TTFB, CLS) on third-party surfaces.

## 5. Dashboards & Visualization
- Operational dashboard: error rate by service and partner, incident timeline, queue depth, average and P95 completion latency, top failing templates.
- User-impact dashboard: real-time success rates, P95 latency per partner, throughput trends, cache contribution, partner usage league tables.
- Provide trace drill-down views linking logs, metrics, and request IDs for root-cause analysis.

## 6. Alerting & Notifications
- Define SLO thresholds (e.g., error rate >2% for 5 minutes, P95 completion latency >30 seconds, queue depth >100, provider failure streak >3).
- Route alerts to Slack/email/on-call pager with payload containing impacted partners, recent changes, sample claim IDs, and runbook links.
- Add heartbeat alerts for ingestion/log pipeline silence >10 minutes to detect broken telemetry.

## 7. Runbooks & Continuous Review
- Document resolution steps for each alert class (provider outage, database slow writes, cache miss spikes, front-end JS errors).
- Schedule weekly review of dashboards/alerts with stakeholders to tune thresholds and prioritize platform fixes.
- After incidents, capture retro notes, update instrumentation gaps, and track follow-up tasks.

## 8. Implementation Phases
- **Phase 1:** Structured logging + critical latency/error metrics shipped to central sink, baseline dashboards.
- **Phase 2:** Alert rules, client-side monitoring, queue/dependency metrics, on-call rotation kickoff.
- **Phase 3:** Usage analytics enrichment, partner reporting, automated runbook links, SLO tuning and compliance reviews.

