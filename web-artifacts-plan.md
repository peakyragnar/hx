# Web Artifacts Plan

## Purpose
- Preserve the full Web-Informed Lens (WEL) evidence for audits, analysis, and future RL without bloating the operational database.
- Keep the current SQLite/Postgres schema lean—store only summaries and pointers (already implemented in `checks` via fields like `p_web`, `ci_web_*`, `resolved_*`).
- Leverage existing Google Cloud credits by default; stay portable to Cloudflare R2 or other S3-compatible storage.

## Current State
- RPL data is persisted in SQLite/Postgres with aggregate metrics only (`p_web`, doc/domain counts, dispersion).
- Detailed evidence (URLs, snippets, quotes, per-replicate records) lives transiently in the run artifact produced via `--out`. Not every run saves an artifact, and nothing is automatically uploaded.
- No artifact pointer is stored in the DB, so UI/API cannot fetch raw web evidence after the fact.
- No analytics pipeline exists—there is no structured dataset of per-document verdicts for model analysis or RL.

## Design Overview

### Operational Storage (unchanged schema)
- Keep `checks` as the summary table. Add two optional pointer columns:
  - `artifact_id`: opaque identifier for the stored artifact bundle.
  - `artifact_uri`: signed or relative path to the manifest in object storage (optional if derivable from `artifact_id`).
- Populate these columns for every `web_informed` run so UI/API can fetch the evidence bundle on demand.

### Artifact Store (Google Cloud Storage)
- Bucket: `gs://heretix-web-artifacts` (configurable via `HERETIX_ARTIFACT_BUCKET`).
- Layout:
  - `/artifacts/{run_id}/manifest.json`
  - `/artifacts/{run_id}/verdicts.json.zst`
  - `/artifacts/{run_id}/search_results.json.zst`
  - `/doc_cache/{content_hash}.json.zst` (optional normalized page cache, deduped across runs).
- **Manifest contents** (JSON):
  - Metadata: `artifact_id`, `run_id`, `claim_hash`, `claim_text`, `mode`, `provider`, `model`, timestamps, requesting user id (if allowed).
  - Query plan: list of templates/final queries.
  - Evidence summary: doc ranks, URLs, titles, snippets, publish dates, scores, resolver outputs, replicate IDs.
  - Pointers: fully qualified URIs to `verdicts.json.zst`, `search_results.json.zst`, cached documents.
- **Verdicts file** (`verdicts.json.zst`):
  - One record per doc verdict: URL, domain, replicate index, stance, quote text, extracted field/value, publish date, weight contributions (domain, recency, quote bonus, total).
  - Supports reproducing resolver decisions or training a downstream model.
- **Search results file** (`search_results.json.zst`):
  - Raw retrieval metadata: API response, ranking scores, dedupe decisions, capped/filtered docs.
- All files compressed via Zstandard (level ≈ 6) to minimize storage costs.

### Document Cache
- Optional caching of normalized page text or HTML (obey provider ToS).
- Deduplicate by SHA256 content hash; store once under `/doc_cache/{hash}.json.zst`.
- Track metadata (URL, first_seen, last_seen) in a small `doc_cache_index` table if access/audit is needed.
- Apply TTL (e.g., 90 days) for raw HTML to minimize risk.

### Analytics Lake (Parquet + DuckDB)
- Nightly ETL job emits normalized tables into Parquet under the same bucket:
  - `/parquet/date=YYYY-MM-DD/runs.parquet` — run-level metrics (p_prior, p_web, combined, costs, seeds, resolved flags).
  - `/parquet/date=YYYY-MM-DD/docs.parquet` — unique documents (content hash, URL, domain, publish date, first seen).
  - `/parquet/date=YYYY-MM-DD/verdicts.parquet` — run_id × doc verdicts (stance, quote, weight).
- Use DuckDB or Polars locally; optionally expose to BigQuery for SQL analytics if credits permit.

## Implementation Steps

1. **Config & Secrets**
   - Add `HERETIX_ARTIFACT_BUCKET` and `HERETIX_ARTIFACT_PREFIX` env vars.
   - Define `ARTIFACT_BACKEND` switch (`local_fs` vs `gcs`), defaulting to local in dev.

2. **Artifact Store Adapter**
   - Implement `ArtifactStore` interface with `write_manifest`, `write_jsonz`, and `ensure_doc_cached`.
   - Provide `LocalFSArtifactStore` (writes to `./artifacts`) and `GCSArtifactStore` (uses `google-cloud-storage` client).
   - Ensure objects are world-private; use signed URLs or service-bound access.

3. **Pipeline Integration**
   - During every `web_informed` run:
     - Collect the WEL payload (docs, verdicts, replicate scores).
     - Serialize normalized structures and upload through the adapter.
     - Persist artifact metadata (ID, URI, citation preview) in memory.
   - Update `heretix/pipeline.py` to:
     - Store `artifact_id`/`artifact_uri` on the `Check` object.
     - Optionally truncate the top 2–3 citations into `checks.resolved_citations` for UI quick view.

4. **CLI/API Exposure**
   - Extend API response to include `artifact_id` and `artifact_uri` (or a signed fetch endpoint).
   - Add CLI flag `--no-artifact` to skip writing for test runs (default: write).
   - Update docs (`documentation/how-to-run.md`) to mention artifact location.

5. **ETL Pipeline**
   - Create `scripts/export_web_artifacts.py`:
     - Incrementally scan new artifacts (using a manifest log or `checks.created_at > last_snapshot`).
     - Download manifests/verdicts, normalize into Pandas/Polars frames, append to partitioned Parquet.
     - Optionally push summary stats to BigQuery or a metrics dashboard.
   - Schedule via cron/GitHub Action/k8s job.

6. **Governance & Retention**
   - Set bucket lifecycle rules:
     - `doc_cache` objects expire after 90 days (configurable).
     - Manifests/verdicts retained indefinitely (or per compliance).
   - Redact/omit PII; ensure artifact includes user IDs only if required.
   - Document deletion procedure: remove DB row, delete artifact prefix, purge cache entries.

7. **Monitoring & Validation**
   - Add smoke test that runs `--mode web_informed --mock`, ensures artifact files are created locally, and confirms DB pointer non-null.
   - Add integration test with `LocalFSArtifactStore` to verify manifest schema and Parquet export.
   - (Optional) collect metrics: artifact write latency, size, error rate.

## Cost Notes
- **Google Cloud Storage** (Standard): ~$0.026/GB-month; covered by existing credits for now.
- **DuckDB/Polars**: free; runs in the same environment.
- **Data transfer**: avoid cross-region egress by colocating compute with the bucket; consider Coldline archive for older artifacts if storage grows large.
- When credits expire, the design is portable to cheaper S3-compatible stores (Cloudflare R2 at ~$0.015/GB-month, no egress).

## Open Questions
- Do we need row-level access control (per user) for artifact fetches? If yes, API must proxy artifact downloads instead of exposing raw URIs.
- What retention policy satisfies legal/compliance for cached web content? Decide before caching HTML bodies.
- Should we capture provider cost/token usage per artifact for spend analysis? (Likely yes—include in manifest.)
- Is a BigQuery sink required now, or can down-stream teams rely on DuckDB/Parquet until scale demands otherwise?

## Next Actions
1. Implement artifact adapter + pipeline wiring (Steps 1–3).
2. Update API/CLI and documentation (Step 4).
3. Build the ETL and Parquet export job (Step 5).
4. Configure lifecycle + monitoring (Steps 6–7).
5. Revisit analytic requirements once Parquet exports are validated.

