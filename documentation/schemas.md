# Canonical Schemas (Phase‑1 Harness)

The Heretix harness treats serialized model output and aggregated metrics as versioned
Pydantic models under `heretix/schemas/`. These classes are the single source of truth
for request/response payloads across the CLI, API, adapters, and tests.

## Location

- Module: `heretix/schemas`
- Files:
  - `rpl_sample_v1.py` — `RPLSampleV1`, `Belief`, `Flags`
  - `wel_doc_v1.py` — `WELDocV1`
  - `prior_block_v1.py` — `PriorBlockV1`
  - `web_block_v1.py` — `WebBlockV1`
  - `combined_block_v1.py` — `CombinedBlockV1`
  - `simple_expl_v1.py` — `SimpleExplV1`
  - `__init__.py` — exports all schemas

Each class enforces:

- `extra="forbid"` — reject unmodeled keys as soon as they appear.
- `validate_assignment=True` — mutations in long‑lived objects (e.g., API view models)
  re‑run validation.
- Field constraints matching the estimator contract (probabilities in [0,1], CI bounds,
  weight sums, etc.).

## Usage

- Provider adapters convert raw JSON into `RPLSampleV1`/`WELDocV1` before aggregation,
  using the shared helper `heretix.provider.json_utils.extract_and_validate`.
- `heretix.pipeline.perform_run` builds `PriorBlockV1`, `WebBlockV1`, `CombinedBlockV1`,
  and `SimpleExplV1` before exposing payloads via the CLI/API.
- `api/schemas.py` simply re‑exports the canonical models—there is no bespoke FastAPI
  schema to maintain.
- UI/CLI smoke tests (`heretix/tests/test_schemas.py`, `test_json_utils.py`,
  `api/tests/test_run_endpoint.py`) validate canonical examples and edge cases.

## Contract

- Schema changes require a version bump (`*_v1.py` → `*_v2.py`) plus a migration plan.
- Tests must cover:
  - happy path instantiation for each model
  - coercion/normalization (e.g., string lists)
  - invalid payload rejection (e.g., `weight_prior + weight_web != 1`)
  - extractor behavior (`json_utils`) for fenced JSON / reasoning tags.
- Docs that describe API contracts should reference these models rather than duplicating
  shapes (see `documentation/how-full-system-works.md` for the API section).

Refer to this file whenever you add a new schema or evolve an existing one so downstream
agents stay aligned on the canonical shapes.
