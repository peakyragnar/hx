# Web Artifacts — Operating Guide

This note walks through how the Web-Informed Lens (WEL) evidence is now captured, where it lives, and how to inspect it in both local and production environments.

---

## 1. What Happens on a Run?
1. You trigger a WEL run (CLI, API, or UI).  
2. `perform_run` calls `write_web_artifact` with the prior block, web block, replicate payloads, and resolver debug data.  
3. The artifact adapter writes:
   - `manifest.json` (metadata, metrics, pointers)
   - `docs.json.gz` (deduped document list)
   - `replicates.json.gz` (per-replicate scores + doc refs)  
4. The manifest URI is persisted on the `checks` row (`Check.artifact_json_path`) and echoed back via CLI/API (`web_artifact` field).
5. SQLite/Postgres still store the usual rollups (`p_web`, `ci_web_*`, `resolved_*`); raw evidence stays in the artifact bundle.

---

## 2. Backends & Environment

| Env Var | Default | Purpose |
|---------|---------|---------|
| `HERETIX_ARTIFACT_BACKEND` | `local` | Switches storage backend (`local`, `gcs`, `disabled`). |
| `HERETIX_ARTIFACT_PATH` | `runs/artifacts` | Local filesystem root when backend=`local`. |
| `HERETIX_ARTIFACT_BUCKET` | — | Required when backend=`gcs` (Google Cloud Storage bucket name). |
| `HERETIX_ARTIFACT_PREFIX` | — | Optional prefix within the bucket for namespacing (no leading slash). |

Notes:
- `local` backend writes to the current machine (dev laptops, single-node prod); files live under `{HERETIX_ARTIFACT_PATH}/artifacts/{run_id}/{artifact_id}/`.
- `gcs` backend streams directly to Google Cloud Storage (requires the `google-cloud-storage` package and service credentials via `GOOGLE_APPLICATION_CREDENTIALS` or workload identity).
- `disabled` backend skips artifact creation entirely (rare; use only if storage is unavailable).

---

## 3. Running Locally (UI or CLI)

```
export OPENAI_API_KEY=sk-...
export TAVILY_API_KEY=tvly-...
# optional: export HERETIX_ARTIFACT_PATH=/custom/path

uv run heretix run --config runs/rpl_example.yaml --mode web_informed --out runs/sample.json
# or
uv run python ui/serve.py
```

After a run you’ll find:
```
runs/artifacts/artifacts/<run_id>/<artifact_id>/manifest.json
                                             /docs.json.gz
                                             /replicates.json.gz
```

The CLI/API response includes:
```json
"web_artifact": {
  "manifest": "runs/artifacts/artifacts/<run_id>/<artifact_id>/manifest.json",
  "replicates_uri": ".../replicates.json.gz",
  "docs_uri": ".../docs.json.gz"
}
```

Quick inspection shortcut:
```
uv run heretix artifact --run-id <run_id>
# or to grab the most recent run for a claim:
uv run heretix artifact --claim "The exact claim text"
```
This prints the manifest summary, top documents, and replicate support/oppose bullets without digging through SQLite or gzip files.

---

## 4. Production Setup (GCS)

Set the backend in your deployment environment:
```
export HERETIX_ARTIFACT_BACKEND=gcs
export HERETIX_ARTIFACT_BUCKET=heretix-web-artifacts
export HERETIX_ARTIFACT_PREFIX=prod   # optional
```

The files will appear under `gs://heretix-web-artifacts/prod/artifacts/<run_id>/<artifact_id>/...`.

Make sure the service account running the API/worker has write access to the bucket.
Typical steps:
- Create a dedicated bucket (e.g., `gsutil mb gs://heretix-web-artifacts`).
- Grant a service account `Storage Object Admin` (or tighter scoped) permissions.
- Provide credentials via `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json` or workload identity.

---

## 5. Inspecting Artifacts

### Manifest (always JSON)
```
jq '.' runs/artifacts/artifacts/<run_id>/<artifact_id>/manifest.json
```
Key fields:
- `web` block mirrors the API response (prob, CI, resolved state, evidence metrics).
- `replicates_uri`, `docs_uri` point to the compressed payloads (local paths or gs:// URIs).
- `debug_votes` holds resolver vote summaries when a resolution attempt ran.

(Shortcut: `uv run heretix artifact --run-id <run_id>` prints the same summary.)

### Documents
```
python -m gzip -dc runs/.../docs.json.gz | jq '.[0]'
```
Each entry: `doc_id`, `url`, `domain`, `title`, `snippet`, `published_at`, `published_confidence`.

(Shortcut: the CLI helper lists the first few docs automatically.)

### Replicates
```
python -m gzip -dc runs/.../replicates.json.gz | jq '.[0]'
```
Each replicate: `replicate_idx`, `p_web`, `support_bullets`, `oppose_bullets`, `notes`, `json_valid`, `docs` (list of `doc_id` keys).

(Shortcut: the CLI helper formats these support/oppose bullets for the first replicates.)

---

## 6. Analytics Export

Use the helper script to flatten artifacts into analytics tables:
```
uv run python scripts/export_web_artifacts.py \
  --artifact-root runs/artifacts \
  --out-dir runs/exports \
  --parquet      # optional, requires duckdb
```
Outputs:
- `runs.jsonl` / `runs.parquet` — per-run summary (one row per artifact).
- `docs.jsonl` / `docs.parquet` — document catalog aggregated across runs.
- `replicates.jsonl` / `replicates.parquet` — replicate-level details (doc references serialized as JSON arrays).

Works with local paths; for `gs://` URIs the current script logs a “not yet supported” message (extend with `gcsfs` or `google-cloud-storage` blob download if needed).

---

## 7. Disabling Capture (Rare)

Set `HERETIX_ARTIFACT_BACKEND=disabled` before the process starts. Useful for quick smoke tests when storage isn’t available or to keep CI ephemeral.

---

## 8. Failure Modes & Logging

- If artifact writing fails, we log the exception (`heretix/pipeline.py` emits a warning) and continue the run; summary metrics still persist.
- For GCS, ensure `google-cloud-storage` is installed (`uv add google-cloud-storage`) and the service account key or workload identity is valid.
- Monitor disk usage when sticking with local storage; rotate or prune old artifacts if needed.

---

## 9. Next Steps / Extensions

- **Retention policy**: apply a cron/job to prune artifacts older than N days if storage is tight.
- **Remote export**: enhance `export_web_artifacts.py` to download `gs://` URIs, then run in prod to generate Parquet directly in the bucket.
- **UI link**: front-end can read `web_artifact.manifest` to add a “View evidence” link per run.
- **RL/Analytics**: point DuckDB/Polars/BigQuery at the Parquet output for model improvement and reporting.

---

## 10. Production Checklist Before Merge

1. **Dependencies**  
   - Ensure the runtime image includes `google-cloud-storage` (already added to `pyproject.toml`).
2. **Bucket & Credentials**  
   - Create/select a GCS bucket and grant write access to the app’s service account.  
   - Configure `GOOGLE_APPLICATION_CREDENTIALS` (JSON key) or workload identity for the deployment.
3. **Environment Variables**  
   - Set `HERETIX_ARTIFACT_BACKEND=gcs`, `HERETIX_ARTIFACT_BUCKET=<bucket>`, and optional `HERETIX_ARTIFACT_PREFIX`.  
   - Leave local dev on `local` (default) if desired.
4. **Redeploy**  
   - Build and deploy the updated application so the pipeline includes artifact capture.  
   - Verify by running a web-informed claim in staging/production and checking for the manifest in the bucket.
5. **Post-Deploy Tests**  
   - Use `uv run heretix artifact --run-id <run_id>` on a staging box (with access to the bucket or downloaded files) to spot-check evidence.  
   - Optionally schedule the export script (with remote download support) for analytics jobs.

With these pieces, we now have a clean separation: lightweight DB summaries for the product, full evidence bundles in artifact storage, and tooling to convert them into datasets whenever analysis or RL needs arise.
