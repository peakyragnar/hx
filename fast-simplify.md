Got it — we need a speed-focused bias product that works cleanly in:
	•	Local CLI / single-claim runs (SQLite)
	•	The hosted app (FastAPI + Postgres: local dev Postgres + production Neon)

…and we don’t want to shred the codebase to get there.

Below is a spec you can hand directly to your coding agent. I’ll call out what’s shared vs what’s SQLite-only vs Postgres-only.

⸻

0. Goals & constraints (for your agent)

Product goals
	•	For a single claim and 1–3 models (GPT‑5, Gemini, Grok):
	•	Return p(model thinks claim is true) per model
	•	Return short explanation per model
	•	Target < 20 seconds wall time for 3 models

Technical constraints
	•	RPL estimator invariants stay intact
(logit aggregation, equal‑by‑template weighting, 20% trimmed center, cluster bootstrap)  ￼
	•	Support local CLI RPL runs that persist to SQLite + JSON (current Single-Claim Workflow).  ￼
	•	Support API runs that persist to Postgres:
	•	Local dev: Docker Postgres (via DATABASE_URL=postgresql+psycopg://...@localhost:5433/heretix)  ￼
	•	Production: Neon Postgres (via DATABASE_URL on Render)  ￼
	•	Minimal migrations, ideally just adding profile+metadata columns or using existing JSON fields.

⸻

1. Architecture after refactor (high level)

You’re going to end up with three main layers:
	1.	RPL harness (heretix/)
	•	Defines profiles (e.g. bias_fast, rpl_research)
	•	Defines multi-model planning (how many samples per provider)
	•	Talks to providers (GPT‑5, Gemini, Grok) through a uniform interface
	•	Optionally persists runs to SQLite (for CLI use) and always writes an output JSON
	2.	Heretix API wrapper (heretix_api/)
	•	Thin adapter between the harness and the web API
	•	Lets API call “run bias_fast for claim X and models Y,Z” and get a structured result
	•	Can choose whether to let harness write to SQLite or not
	3.	FastAPI app (api/) + DB (Postgres: local & Neon)
	•	HTTP endpoint /api/checks/run
	•	Reads/writes app data (users, runs, plans, etc.) in Postgres
	•	Stores:
	•	Claim, user, profile name
	•	Per-model probabilities + labels + explanations
	•	Full RPL output JSON (jsonb) for audit/debug

The key: harness logic is DB-agnostic. SQLite and Postgres are two consumers of the same RunResult object:
	•	CLI → harness → writes SQLite + JSON file
	•	API → harness via heretix_api → API writes to Postgres

⸻

2. Harness-level changes (heretix/)

2.1. Introduce RPL profiles

Create a small profile object in the harness, e.g. heretix/profiles.py:

from dataclasses import dataclass
from typing import Literal

@dataclass
class RPLProfile:
    name: str
    K: int
    R: int
    T: int
    B: int | None          # None or 0 = skip bootstrap for hot path
    max_output_tokens: int
    total_sample_budget: int  # used when multiple models selected
    explanation_mode: Literal["separate_call", "inline", "none"]

Define at least two profiles:

BIAS_FAST = RPLProfile(
    name="bias_fast",
    K=4,
    R=1,
    T=6,                  # keep T ≥ 5 to preserve trimmed center invariants
    B=0,                  # hot path: no bootstrap
    max_output_tokens=192,
    total_sample_budget=72,   # total samples across models
    explanation_mode="separate_call",
)

RPL_RESEARCH = RPLProfile(
    name="rpl_research",
    K=8,
    R=2,
    T=8,
    B=5000,
    max_output_tokens=1024,
    total_sample_budget=999999,  # effectively unbounded
    explanation_mode="inline",
)

Wiring:
	•	CLI config can continue to specify K/R/T/B directly, or accept a profile field and populate defaults from RPLProfile.
	•	API will always use BIAS_FAST (unless you later add an override).
		•	UI default profile: bias_fast (K=4, R=1, T=6, B=0, max_output_tokens=192), with multi-model submissions clamped to those ceilings so the UI stays on the fast path.

2.2. Multi-model sampling planner

Add a planner function at the harness layer that translates:

(claim, list_of_models, profile) → a per-model sampling plan

Pseudo-code:

def derive_sampling_plan(models: list[str], profile: RPLProfile) -> dict[str, tuple[int,int,int]]:
    M = len(models)
    K, R, T = profile.K, profile.R, profile.T
    per_model = K * R * T
    total = per_model * M

    if total <= profile.total_sample_budget or profile.total_sample_budget <= 0:
        # no need to adjust
        return {m: (K, R, T) for m in models}

    # downscale K to keep total samples under budget
    target_per_model = profile.total_sample_budget // M
    K_scaled = max(1, target_per_model // (R * T))

    return {m: (K_scaled, R, T) for m in models}

Usage:
	•	Single-model CLI runs: models = ["gpt-5"] → plan = { "gpt-5": (4,1,6) }
	•	Multi-model API runs: models = ["gpt-5","gemini","grok"] → plan = each ~24 samples, total ≤ 72.

This planner is shared between:
	•	Local CLI (SQLite persistence)
	•	API (Postgres persistence via heretix_api)

2.3. Provider abstraction for GPT‑5, Gemini, Grok

Define a common provider interface (e.g. heretix/providers/base.py):

from typing import Protocol, Any

class LLMProvider(Protocol):
    name: str  # "gpt-5", "gemini", "grok"

    async def sample_prior(self, prompt: str, max_output_tokens: int, seed: int | None) -> dict[str, Any]:
        """
        Return small JSON-like dict:
        {
            "label": "true" | "false",
            "p_true": float  # model's probability in this sample
        }
        """

Implement three concrete providers:
	•	GPT5Provider – uses OpenAI API with the configured OPENAI_API_KEY
	•	GeminiProvider – uses Google Gemini API key/env
	•	GrokProvider – uses xAI API

Crucial constraint for speed:
	•	Sampling prompts must request short JSON only:
	•	No chain-of-thought
	•	No multi-paragraph explanation
	•	Cap max_output_tokens using profile (e.g. 192).

2.4. Separate measurement vs explanation

Update the harness so that each RPL sample returns only:

{ "label": "true", "p_true": 0.74 }

No explanations, no essays. That cuts tokens per call dramatically.

After all samples are collected and aggregated:
	•	Compute p_RPL per model using the existing estimator (unchanged).
	•	Then run one explanation call per model:

async def explain_bias(
    provider: LLMProvider,
    claim: str,
    p_rpl: float,
    maybe_template_counts: dict | None = None,
) -> str:
    """
    Ask the model for a short 1-2 sentence explanation
    of why it leans toward this probability.
    """

These explanation calls:
	•	Use a slightly higher max_output_tokens (e.g. 256–512)
	•	Run in parallel across models via the same concurrency pool

Result object

Define a run result object (RunResult) that harness returns:

@dataclass
class ModelBiasResult:
    model: str
    p_rpl: float
    label: str                # e.g. "leans_true" / "leans_false" / "uncertain"
    explanation: str
    # you can add counts, raw templates, etc., if needed

@dataclass
class RunResult:
    run_id: str
    claim: str
    profile: str
    models: list[ModelBiasResult]
    raw_rpl_output: dict      # full RPL JSON, including per-template stats
    timings: dict             # stage timings (from existing telemetry)

This RunResult is:
	•	Written to SQLite (CLI flow)
	•	Serialized to JSON/returned to heretix_api (API flow)
	•	Eventually persisted to Postgres (API layer)

2.5. Concurrency & fast-configuration (works local & prod)

Use existing tunables for both environments:
	•	HERETIX_RPL_CONCURRENCY (default 8) – thread pool for provider calls
	•	HERETIX_FAST_B, HERETIX_FINAL_B, HERETIX_FAST_FINAL – still available for research profile; for bias_fast you can choose:
	•	B=0 or None for hot path
	•	Optionally run a background “full CI” with HERETIX_FINAL_B for logging only
	•	HERETIX_CACHE_TTL – set in prod to reuse identical runs

These env vars work identically with:
	•	CLI runs (heretix harness → SQLite)
	•	API runs (heretix harness via heretix_api → Postgres, Neon/Dev)

⸻

3. CLI / local RPL (SQLite) integration

Current state:
	•	Single-Claim Workflow: heretix run --config ... persists outputs to SQLite and a JSON file.

3.1. New fast bias config for CLI

Add runs/rpl_bias_fast.yaml:

claim: "__OVERRIDE_ME__"
models: ["gpt-5"]          # CLI default; can be one model
profile: bias_fast

# Optional explicit overrides, but profile should fill these:
K: 4
R: 1
T: 6
B: 0
max_prompt_chars: 900
max_output_tokens: 192
seed: 42

Update heretix CLI:
	•	Accept an optional --profile flag:
	•	--profile bias_fast
	•	--profile rpl_research
	•	If profile is provided:
	•	Load defaults from RPLProfile
	•	Allow config file to override individual fields if needed

3.2. SQLite persistence strategy

The simplest way to avoid schema churn:
	•	Assume the SQLite DB has a table like rpl_runs with:
	•	id, claim, model/models, created_at, raw_output (JSON), etc.
	•	Keep the schema exactly as-is, but:
	•	Let raw_output store the new RunResult.raw_rpl_output (which already contains more detail, plus profile etc.).
	•	If the table has a single model column, keep writing single-model runs there as before; for multi-model CLI usage, you can:
	•	Either not support multi-model in CLI yet, OR
	•	Store models as a JSON array in raw_output and log a single “composite” run row (the agent can pick whichever is simpler after seeing schema).

Key point: do not add SQLite-only migrations unless strictly necessary. You get free flexibility by shoving richer JSON into the existing JSON column.

3.3. Local workflow remains simple

After changes, local RPL usage:

# Fast bias run with GPT-5 only
uv run heretix run --config runs/rpl_bias_fast.yaml --out runs/bias_gpt5.json

# Fast bias run with multiple models (if you wire CLI to allow it)
uv run heretix run \
  --config runs/rpl_bias_fast.yaml \
  --models gpt-5 gemini grok \
  --out runs/bias_multi.json

This will:
	•	Call harness with profile=bias_fast
	•	Persist to SQLite + JSON just like today (just with slightly richer JSON)

No interaction with Postgres here.

⸻

4. API + Postgres integration (local dev & Neon)

Current state from README:
	•	Local dev:
	•	docker compose up -d postgres
	•	DATABASE_URL=postgresql+psycopg://heretix:heretix@localhost:5433/heretix
	•	uv run alembic upgrade head
	•	Run API: uv run uvicorn api.main:app --reload
	•	Production:
	•	Neon connection string in DATABASE_URL
	•	Same Alembic migrations applied

We want /api/checks/run to:
	•	Accept claim + list of models
	•	Use bias_fast harness profile
	•	Persist results to Postgres (local or Neon depending on env)
	•	Return per-model probabilities + explanations to the frontend

4.1. heretix_api wrapper

Inside heretix_api/, implement a thin function, e.g.:

from heretix.profiles import BIAS_FAST
from heretix.run import run_rpl  # whatever your main harness entry is
from heretix.types import RunResult

async def run_bias_fast(
    claim: str,
    models: list[str],
    persist_to_sqlite: bool = False,
) -> RunResult:
    """
    Orchestrates a bias_fast RPL run across one or more models.
    - Uses BIAS_FAST profile
    - Uses multi-model sampling planner
    - Can optionally persist to SQLite (CLI usage) or skip for API
    """
    profile = BIAS_FAST
    # multi-model plan & execution
    result = await run_rpl(
        claim=claim,
        models=models,
        profile=profile,
        persist=persist_to_sqlite,
    )
    return result

Important:
	•	run_rpl(.., persist=True) → harness behaves as CLI: writes to SQLite + JSON.
	•	run_rpl(.., persist=False) → harness only returns RunResult in memory; no SQLite writes.

API must call with persist_to_sqlite=False.
CLI can still call run_rpl directly or via existing CLI machinery with persist=True.

4.2. FastAPI endpoint /api/checks/run

Update the request schema to something like:

class RunCheckRequest(BaseModel):
    claim: str
    models: list[str] | None = None   # default ["gpt-5","gemini","grok"] or similar
    profile: str | None = None        # ignore for now; force "bias_fast" server-side
    mock: bool = False

Handler:

@app.post("/api/checks/run")
async def run_check(req: RunCheckRequest, user=Depends(current_user_optional)):
    models = req.models or ["gpt-5"]  # or a default trio
    # In production, ignore req.profile and always use bias_fast for UX runs

    if req.mock:
        # existing mock behavior; keep as-is
        ...

    result: RunResult = await heretix_api.run_bias_fast(
        claim=req.claim,
        models=models,
        persist_to_sqlite=False,
    )

    # persist to Postgres (see 4.3)
    db_run = await save_run_to_db(user, result)

    # build API response
    return {
        "run_id": db_run.id,
        "profile": result.profile,
        "claim": result.claim,
        "models": [
            {
                "name": m.model,
                "p_rpl": m.p_rpl,
                "label": m.label,
                "explanation": m.explanation,
            }
            for m in result.models
        ],
        "timing": result.timings,
    }

This code doesn’t care whether DATABASE_URL points at local Postgres or Neon; that’s handled by your existing SQLAlchemy/Alembic setup.

4.3. Postgres schema & migrations (Dev + Neon)

Your agent needs to inspect the existing Postgres schema (Alembic migrations under migrations/ and/or db/migrations/). But here’s the target we want:
	•	A table that links:
	•	id (run id)
	•	user_id (nullable for anon)
	•	claim (text)
	•	profile (text, e.g. "bias_fast")
	•	models (JSONB: array of model names, e.g. ["gpt-5","gemini"])
	•	result_json (JSONB: the full RunResult.raw_rpl_output from the harness)
	•	Optionally: denormalized summary fields:
	•	gpt5_p_rpl, gemini_p_rpl, grok_p_rpl, etc.

Migration strategy (minimal risk)
	1.	If there is already a result_json column storing the old RPL output:
	•	Keep it and just write the new shape into it (JSON is flexible; no migration needed).
	2.	Add new columns only if missing:
	•	profile (VARCHAR / TEXT, nullable, default NULL)
	•	models (JSONB, nullable)

The Alembic migration would:

op.add_column("checks", sa.Column("profile", sa.String(), nullable=True))
op.add_column("checks", sa.Column("models", sa.JSON(), nullable=True))  # or sa.JSONB for Postgres

Then:
	•	Local dev: DATABASE_URL=... uv run alembic upgrade head
	•	Production Neon: DATABASE_URL="<NEON_CONNECTION>" uv run alembic upgrade head

Both environments share the same schema; only the connection string differs.

4.4. Environment & performance knobs (Dev + Neon)

Same harness env variables should be used in both local and production API containers:
	•	HERETIX_RPL_CONCURRENCY=6 or 8
	•	HERETIX_CACHE_TTL=86400 (or similar)
	•	For research runs only (not UI), you may also define:
	•	HERETIX_FAST_B, HERETIX_FINAL_B, HERETIX_FAST_FINAL

Render prod also needs:
	•	DATABASE_URL="<Neon connection>"
	•	OPENAI_API_KEY, Gemini & Grok keys, Stripe/Postmark keys, etc.

Local dev uses:
	•	docker compose up -d postgres
	•	DATABASE_URL=postgresql+psycopg://heretix:heretix@localhost:5433/heretix

All the new harness behavior is independent of which DB that URL points at.

⸻

5. End-to-end implementation steps for your agent

Here’s the “do this in order” checklist.

Step 1 — Harness profiles & planner (heretix/)
	•	Implement RPLProfile and define BIAS_FAST and RPL_RESEARCH.
	•	Implement derive_sampling_plan(models, profile).
	•	Integrate profile into heretix.run so it can:
	•	Accept a profile param
	•	Fall back to config K/R/T/B when no profile is specified

Step 2 — Provider abstraction & explanation split
	•	Implement LLMProvider protocol and concrete providers for GPT‑5, Gemini, Grok.
	•	Update RPL sampling prompts to:
	•	Return only JSON { "label": ..., "p_true": ... }
	•	Enforce max_output_tokens from profile (<= 192 for bias_fast)
	•	Introduce a second step that:
	•	After aggregation, calls explain_bias once per model
	•	Populates ModelBiasResult.explanation fields
	•	Define RunResult and ModelBiasResult dataclasses to be the canonical output of the harness.

Step 3 — CLI wiring + SQLite
	•	Add runs/rpl_bias_fast.yaml.
	•	Extend CLI to support:
	•	profile field in config
	•	Optional --profile CLI arg
	•	Ensure CLI runs:
	•	Call harness with persist=True
	•	Continue to write to SQLite & JSON
	•	Verify SQLite schema doesn’t need migration; ensure raw_output or equivalent JSON column can hold new RunResult.raw_rpl_output.

Step 4 — heretix_api adapter (no DB logic here)
	•	Implement run_bias_fast(claim, models, persist_to_sqlite=False) -> RunResult inside heretix_api.
	•	It should:
	•	Use BIAS_FAST profile
	•	Use derive_sampling_plan
	•	Call harness (run_rpl) with persist=persist_to_sqlite

Step 5 — FastAPI endpoint + Postgres persistence
	•	Update /api/checks/run request schema to include models and (optionally) profile.
	•	Handler should:
	•	Resolve models (default set if none provided)
	•	Call heretix_api.run_bias_fast(..., persist_to_sqlite=False)
	•	Persist result to Postgres via existing ORM layer:
	•	checks.profile = "bias_fast"
	•	checks.models = ["gpt-5", ...] (JSON/JSONB)
	•	checks.result_json = result.raw_rpl_output
	•	Response should return:
	•	run_id, profile, claim
	•	models: array of { name, p_rpl, label, explanation }
	•	timing: aggregated stage times from RunResult.timings

Step 6 — Alembic migration (shared Dev + Neon)
	•	If needed, add profile and models columns to the relevant table (probably checks or runs).
	•	Apply migrations:
	•	Local dev: DATABASE_URL=postgresql+psycopg://... uv run alembic upgrade head
	•	Neon prod: DATABASE_URL="<Neon>" uv run alembic upgrade head

No special handling for SQLite here, because CLI harness uses its own SQLite DB and schema, not Alembic.

Step 7 — Tuning & verification
	•	On local dev:
	•	Set HERETIX_RPL_CONCURRENCY=8.
	•	Hit /api/checks/run with 1–3 models and measure latency.
	•	Confirm call counts ≈ 24 per model and total ≤ 72 for 3 models.
	•	Confirm output JSON shape is stable between CLI and API (apart from DB IDs).
	•	On Neon prod:
	•	Same env flags, just with live keys and Neon DATABASE_URL.
	•	Confirm runs are persisted correctly and returned to the UI.

⸻

Net effect:
	•	Same harness powers:
	•	Local RPL experiments (SQLite)
	•	Web bias checker (Postgres, local + Neon)
	•	Users see a multi-model bias readout with probability + explanation under ~20 seconds, without you having to maintain two divergent implementations or wreck your existing statistics layer.