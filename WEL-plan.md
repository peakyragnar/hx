## Web-Informed Lens Integration Plan (WEL)

### Objectives
- Introduce a Web-Informed evaluation path that augments the existing RPL prior without altering current behaviour for baseline runs.
- Provide clear separation of concerns: retrieval, snippet preparation, scoring, aggregation, and fusion.
- Expose the new mode via the API while persisting provenance and metrics required for auditability.

### Deliverables
1. `heretix_wel` package with:
   - Core dataclasses (`types.py`) and pure helpers (`timeliness.py`, `weights.py`, `snippets.py`).
   - Retrieval abstraction with a Tavily provider implementation (`retriever.py`, `providers/tavily.py`).
   - GPT‑5 scoring harness (`scoring.py`) and replicate aggregator (`aggregate.py`).
   - Orchestrator (`evaluate_wel.py`) returning structured results for API consumption.
2. API fusion layer (`heretix_api/fuse.py`) plus updates to `routes_checks.py` to support `mode: baseline | web_informed`.
3. Database migration `V003_add_web_informed_columns.sql` storing prior, web, and combined fields with weights.
4. Unit tests covering timeliness heuristic, weighting logic, and probability fusion.
5. Environment sample updates documenting required WEL configuration variables.

### Sequenced Tasks
1. **Scaffolding**
   - Create `heretix_wel` module structure and stub files with docstrings.
   - Ensure `__init__.py` exposes top-level entry points as needed.
2. **Pure Utilities**
   - Implement dataclasses, timeliness heuristic, weighting/fusion math, snippet utilities, and associated tests.
   - Verify helper tests via `uv run pytest tests/test_timeliness.py tests/test_weights.py tests/test_fuse.py`.
3. **Retrieval Layer**
   - Implement provider-agnostic retriever factory and Tavily adapter with snippet normalization.
   - Add graceful failure for missing API keys and configurable timeouts.
4. **Scoring & Aggregation**
   - Implement GPT‑5 Responses API call with strict JSON parsing, provenance hash, and error handling.
   - Implement replicate aggregation in logit space returning `p_web`, CI, and dispersion metric.
5. **Evaluation Orchestrator**
   - Combine retrieval, snippet preparation, scoring, and aggregation into `evaluate_wel`.
   - Provide deterministic seeding for reproducibility and record metrics (coverage, diversity, timeliness, JSON validity).
6. **Fusion & API Update**
   - Add `heretix_api/fuse.py` with recency/strength weighting and probability fusion.
   - Update `routes_checks.py` to:
     - Accept `mode` parameter.
     - Call RPL only for baseline; call both RPL and WEL for web_informed mode.
     - Persist prior, web, combined, and weight data via existing storage utilities.
7. **Database Migration**
   - Add SQL migration for new columns and integrate with Alembic/DB workflow.
   - Document migration execution steps.
8. **Environment & Docs**
   - Extend `.env.sample` with WEL variables (provider, keys, doc/replicate counts).
   - Optionally add README entry describing WEL knobs and operational guidance.
9. **Validation**
   - Run targeted unit tests and smoke tests (`uv run pytest -q`).
   - Execute mock API call in both modes ensuring responses contain expected blocks.
   - Confirm DB persistence for web_informed mode including weight fields.
10. **Post-Integration Notes**
    - Outline caching opportunities (result/doc caches) for future optimizations.
    - Highlight tuning knobs (recency tau, strength thresholds, weight bounds).

### Acceptance Criteria
- Baseline mode behaviour remains unchanged (probabilities, CI, stability).
- Web-Informed mode returns structured payload with prior, web, and combined sections plus weight diagnostics.
- Retrieval and scoring gracefully handle missing/invalid data without crashing the pipeline.
- Database rows for web-informed checks capture all new metrics and weights.
- Unit tests cover key heuristics and fusion logic; CI suite passes.

