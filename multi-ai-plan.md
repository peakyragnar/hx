Here’s a ready-to-drop multi-ai-plan.md for your repo.

# Multi-Model Architecture & Refactor Plan (Heretix / hx)

This document describes how to evolve the current hx / Heretix system from a **GPT‑5-only** implementation into a **multi-model** system supporting GPT‑5, Grok, Gemini, DeepSeek (and future models), while:

## Live Coordination (updated 2025-11-13 17:27 UTC)

> 17:18 UTC — Worker-8 (**BrownLake**) captured the assignments below (picking up from Worker-1).  
> 17:23 UTC — Worker-1 (**BlueSnow**) recorded the canonical schema completion, and Worker-3 (**LilacHill**) logged the new Rich CLI tests so BrownLake can focus on JSON utils next.  
> 17:27 UTC — Worker-5 (**ChartreuseCat**) confirmed ownership for the DB/API + UI slices (bd 1bb.11-1bb.16 + 2jf.8/10) and paired with Worker-2 on the agent workflow (2jf.22) + rich CLI coverage.

| Plan Section | BD issue(s) | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| §4 Canonical Schemas | Heretix-1bb.1, Heretix-o4a.5 | Worker-1 (BlueSnow) | Ready for review | `heretix/schemas/*` + `heretix/tests/test_schemas.py` landed (17:23 UTC). Need adapter + API reviewers (ChartreuseCat, FuchsiaMountain). |
| §5 Provider Capabilities/Config | Heretix-1bb.3, Heretix-lq1.* | Worker-7 (OrangeSnow) | Ready for review | Capability YAML set + loader + pytest (incl. rich logging snapshot) landed; awaiting peer review + adapter wiring before closing BD items. |
| §6 JSON Utils | Heretix-1bb.5, Heretix-1mg | Worker-8 (BrownLake) | Active | `heretix/provider/json_utils.py` + `heretix/tests/test_json_utils.py` landed locally (strip, repair, warning hooks); wiring into adapters next. |
| §7 Provider Adapters | Heretix-2jf.12, 1bb.6-1bb.8 | Worker-4 (FuchsiaMountain) | Active | Adapter abstraction underway; waiting on schema/json contract to finalize outputs. |
| §8 Pipeline Integration | Heretix-1bb.9, Heretix-1bb.10 | Pending (Worker-2/PurpleDog + Worker-8 once adapters ready) | On deck | Will start after schemas + adapters merge; need alignment on config/plumbing. |
| §10 API + DB Contract | Heretix-1bb.11, Heretix-1bb.12, Heretix-1bb.13 | Worker-5 (ChartreuseCat) + Worker-2 (PurpleDog assist) | In progress | Worker-5 claimed bd 1bb.11-1bb.13 to extend Check + RunRequest/RunResponse + add alembic; pairing with Worker-2/LilacHill for verification + workflow docs. |
| §11 UI Multi-Model Layout | Heretix-1bb.14, Heretix-1bb.15, Heretix-1bb.16 | Worker-5 (ChartreuseCat) w/ Worker-3 review | In progress | Multi-card grid + selector + neon palette refactor underway; Worker-3 owns Matrix-state wiring + review. |
| §12 Tests & Rich Logging | Heretix-50f.18, Heretix-dph, Heretix-h77 | Worker-3 (LilacHill) + Worker-5 (ChartreuseCat) + Worker-6 (BlackStone) + Worker-8 (BrownLake) | In progress | Rich multi-model CLI pytest (`heretix/tests/test_rich_cli_logging.py`, bd-dph) now live (ChartreuseCat + LilacHill). Worker-6 focusing on eval logging, Worker-8 on schema/json fixtures—grabbing reviews keeps adapters unblocked. |

Requests / resolutions (17:27 UTC):
- Provider capabilities (Heretix-1bb.3/lq1.*) remain with Worker-7/OrangeSnow; reviews requested from ChartreuseCat + FuchsiaMountain before adapters wire them in.
- DB/API + UI ownership locked: Worker-5/ChartreuseCat is driving bd 1bb.11-1bb.16 + 2jf.8/10 with Worker-3 reviewing Matrix-page wiring.
- Agent workflow runbook (Heretix-2jf.22) now a Worker-2 + Worker-5 pair; PurpleDog will keep docs/tests in sync while ChartreuseCat adds the helper script + plan doc notes.

### Worker-7 / OrangeSnow review notes — 17:22 UTC

- Reviewed `heretix/provider/registry.py` + `__init__.py` to ensure adapter autoload skips (`config`, `factory`, etc.) stay untouched; confirmed new YAML files don’t get imported accidentally.
- Double-checked `heretix/provider/openai_gpt5.py` rate-limit flow; no changes required (still uses `get_rate_limits` + env fallback), so capability loader remains additive-only.
- Flag for adapters: once they adopt `load_provider_capabilities()`, they should continue to honor `_OPENAI_RATE_LIMITER` semantics or thread through provider-level rate limits if needed.

### Worker-8 / BrownLake progress — 17:26 UTC

- Implemented the new schema package (`heretix/schemas/*`) plus coverage in `heretix/tests/test_schemas.py`; local run: `uv run pytest heretix/tests/test_schemas.py`.
- Added `heretix/provider/json_utils.py` and `heretix/tests/test_json_utils.py` covering fence stripping, repairs, and strict vs. coerced validation (`uv run pytest heretix/tests/test_json_utils.py`).
- Updated BD issues (Heretix-736 + Heretix-o4a.5 ↔ §4, Heretix-1bb.5 + Heretix-1mg ↔ §6) with comments; adapters can now import these contracts while preserving Phase-1 math constraints.
- Added schema-focused Rich logging coverage via `heretix/tests/test_schema_rich_logging.py` (writes `schema_pipeline.log` artifacts, BD Heretix-h77) to document inputs → functions → outputs for the JSON/schema flow.

### Worker-5 / ChartreuseCat checkpoint — 17:27 UTC

- Claimed bd `Heretix-1bb.11-1bb.16`, `Heretix-2jf.8`, `Heretix-2jf.10`, and paired on `Heretix-2jf.22` + `Heretix-dph`; BD updates and Agent Mail replies posted for audit.
- DB/API plan: add provider/logical-model/tokens/cost/schema_version columns via Alembic, extend RunRequest/RunResponse/Pydantic models, and thread the metadata through CLI + pipeline before Worker-3 reviews.
- UI plan: implement the multi-model selector + card grid + neon palette refresh while keeping Matrix status/state work under Worker-3; will capture screenshots + `uv run pytest -q` output ahead of review.
- Agent-workflow deliverables: Rich CLI pytest is merged; next up is drafting the deterministic `uv run heretix run --mock --config runs/rpl_example.yaml --out runs/smoke.json --mode baseline` helper + documenting `HERETIX_RPL_SEED=42` so everyone can reuse the log recipe.

- Preserving the existing RPL/WEL math and pipeline.
- Preserving the existing UI look and feel.
- Exposing a **uniform, stable output schema** to the UI and API regardless of provider.
- Adding a **dense unit test and evaluation suite** suitable for automated agent iteration.

The intent is that any engineer or automated agent can safely follow this plan to extend and maintain the system over time.

---

## 0. Multi-Agent Coordination Snapshot (2025-11-13 17:27 UTC)

| Task ID(s) | Focus | Owner | Status | Next Steps |
| --- | --- | --- | --- | --- |
| Heretix-1bb.1 + Heretix-o4a.5 | Canonical schema package (RPL sample, WEL doc, block models, simple expl) | Worker-1 / `BlueSnow` | Ready for review | `heretix/schemas/*` + `heretix/tests/test_schemas.py` complete; reviews requested from ChartreuseCat + FuchsiaMountain. |
| Heretix-1bb.5 + Heretix-1mg | JSON extraction & repair utility | Worker-8 / `BrownLake` | Planning → coding (paired with schemas) | Land `heretix/provider/json_utils.py` w/ strip/validate/warning hooks + pytest coverage. |
| Heretix-2jf.12 | Provider adapters + registry | Worker-4 / `FuchsiaMountain` | Active | RPL path already uses `get_rpl_adapter`; next up is swapping API/UI explanation paths onto the factory + adding regression + Rich CLI tests before review (cc Worker-8 + LilacHill). |
| Heretix-2jf.16 | Prompt templates + paraphrase builder | Worker-6 / `BlackStone` | Builder + tests staged (17:22 UTC) | Shared/provider prompt files plus `prompt_builder.py` + pytest coverage landed; next wire into RPL + schema validation. |
| Heretix-50f.18 + Heretix-dph + Heretix-h77 | Rich-logged tests (CLI + schema/json) | Worker-3 / `LilacHill`, Worker-6 / `BlackStone`, Worker-8 / `BrownLake` | Split coverage | Worker-3 delivered baseline + web_informed Rich CLI pytest + DB assertions (bd-dph). Worker-6 is building eval logging, Worker-8 covering schema/json fixtures; align on shared helpers. |
| Heretix-1bb.3 | Provider capabilities + YAML schema | Worker-7 / `OrangeSnow` | Ready for review | Loader + config YAMLs + pytest landed; waiting on reviews + adapter consumers before closing BD item. |
| Heretix-1bb.11-1bb.16 | API/DB contract + UI multi-card | Worker-5 / `ChartreuseCat` (pairing w/ Worker-2 + Worker-3) | In progress | Designing Alembic + RunRequest/RunResponse updates (bd 1bb.11-1bb.13) and multi-card UI (bd 1bb.14-1bb.16); Worker-2 supplies workflow context, Worker-3 reviews Matrix wiring. |
| Heretix-2jf.8 + Heretix-2jf.10 | Dark theme + processing/matrix UI polish | Worker-5 / `ChartreuseCat` + Worker-3 / `LilacHill` | In progress | Worker-5 owns neon palette + multi-card grid CSS, Worker-3 retains Matrix status logic; screenshots + `uv run pytest -q` required pre-review. |
| Heretix-2jf.22 | Agent-ready workflows + helper scripts | Worker-2 / `PurpleDog` + Worker-5 / `ChartreuseCat` | In progress | Co-author deterministic uv/bd/mail quickstart, seed recipe, and Rich-log example; Worker-2 handles prose, Worker-5 lands script + pytest. |

> Worker-4 / **FuchsiaMountain**: ready to integrate the schema package once merged; will reciprocate review on that diff.
>
> Worker-6 / **BlackStone**: drafting prompt builder tonight; will cc Worker-8 + Worker-3 for JSON-only validation once ready.
>
> Worker-3 / **LilacHill**: landed the baseline + web_informed Rich CLI pytest (Heretix-dph) w/ DB snapshots; next up is reviewing Worker-8’s schema fixtures and adding provider mock coverage.
>
> Worker-2 / **PurpleDog**: partnering with Worker-5 on Heretix-2jf.22 (workflow doc + helper script) and ready to help verify the API/DB patches once they land.

**Open asks (refreshed 17:27 UTC)**

- Reviews needed for canonical schemas (Heretix-1bb.1 / o4a.5), provider capabilities (Heretix-1bb.3 / lq1.*), and Worker-3’s Rich CLI pytest (Heretix-dph). Please grab one so Worker-8 can stay on JSON utils + adapter wiring.
- Worker-5 will share the helper script + DB/API draft shortly; Worker-2 + Worker-3 volunteered to review once diffs are up.
- Worker-8 still needs adapter consumers to adopt `heretix/provider/json_utils.py` once tests land.
- Baseline harness documentation issues (`Heretix-zup*`) remain unstaffed; propose Worker-1 + Worker-2 pairing after current reviews.

> Worker-6 / **BlackStone** (17:20 UTC): posted coordination mail w/ proposed splits, claimed `Heretix-2jf.16`, and offered to cover the rich pytest harness for `Heretix-50f.18` alongside BrownLake (eval datasets). Waiting on Worker-5/7 ACKs for the workflow/UI tasks plus Worker-1/2 for the baseline docs before updating this section again.

### Worker-3 / **LilacHill** update — 17:27 UTC

- Paired with ChartreuseCat to land `heretix/tests/test_rich_cli_logging.py`, which exercises baseline + `web_informed` CLI paths under `--mock`, captures Rich panels for inputs/command/env/function calls/results, and verifies the SQLite `checks` table contents (bd-dph).
- Updated Beads + this plan, and pinged Workers 2/5/7/8 in Agent Mail so they can confirm ownership of workflows/UI/DB follow-ups.
- Next: review Worker-8’s JSON utils fixtures, add provider adapter mock tests, and extend the Rich harness to capture schema validation warnings.

### Worker-2 / **PurpleDog** update — 17:21 UTC

- Staying focused on **Heretix-2jf.22** (agent-ready workflow quickstart) and coordinating deterministic `uv run` + `bd` instructions.
- Confirmed hand-off of **Heretix-2jf.18** to Worker-3 while remaining available for reviews and workflow doc updates.

## 1. Goals

### 1.1 Product / UX goals

- Support multiple AI models (GPT‑5, Grok, Gemini, DeepSeek) for the same claim.
- Present **consistent output structure** to users:
  - Prior (training-only) verdict.
  - Web-informed verdict.
  - Combined verdict (with explicit weighting).
  - Clear, concise explanation text in a stable layout.
- Preserve the current **visual design**:
  - Dark theme, neon green.
  - Landing page composition.
  - Processing (“Matrix agent”) page.
  - Single-model result card style (extended to multi-model grid).

### 1.2 Engineering goals

- Abstract away provider-specific quirks into **adapters**, so the core RPL/WEL pipeline remains unchanged.
- Use **canonical, versioned schemas** for all model-generated data.
- Ensure that adding or updating a model touches as few files as possible:
  - Provider config.
  - Prompt templates.
  - One adapter module.
- Provide a **robust test and evaluation suite** that:
  - Validates schemas and invariants.
  - Mocks provider APIs for deterministic tests.
  - Supports calibration / correctness evals.
  - Is easy for automated agents to run after changes.

---

## 2. Current Baseline (hx)

The current repo already has substantial infrastructure:

- **Core harness (`heretix/`)**
  - Raw Prior Lens (RPL):
    - K×R sampling over paraphrases.
    - Logit-space aggregation, trimmed center, clustered bootstrap, calibration metrics.
  - Web-Informed Lens (WEL):
    - Web retrieval, doc-level scoring, aggregation, artifact writing.
- **Provider layer**
  - GPT‑5-specific `openai_gpt5` provider.
  - `score_claim_mock` for deterministic testing.
- **Pipeline**
  - A pipeline that runs RPL + optional WEL and produces prior, web, combined blocks and explanation.
- **Database**
  - `Check` table stores claims, model, prior/web/combined metrics, artifact paths, etc.
- **API**
  - FastAPI-based API exposing a run endpoint, auth, and usage tracking.
- **UI**
  - Static HTML/CSS/JS UI with the Heretix landing page, processing page, and result card.

This plan builds on that structure and does **not** rewrite the stack.

---

## 3. High-Level Target Architecture

We will introduce:

1. **Canonical schemas** (Pydantic models) for:
   - RPL samples (single prior verdict sample).
   - WEL doc scores (per web snippet).
   - Block-level summaries (prior, web, combined).
   - Simple explanation (text shown to users).
2. **Provider capabilities & configs** describing:
   - Supported features (JSON mode, tools, seeds, etc.).
   - Mapping from **logical model IDs** to **concrete API model names**.
3. **Prompt templates per provider & task**:
   - Shared task prompt (provider-agnostic).
   - Provider-specific tweaks (formatting, warnings).
4. **A shared JSON extraction & repair utility**:
   - Handles messy model outputs once, centrally.
   - Validates against Pydantic schemas.
5. **Provider adapters for each task**:
   - RPL (prior sample).
   - WEL (web doc scoring).
   - Explanation (simple explanation).
6. **Registry keyed by `(provider, logical_model)`**:
   - All pipelines look up adapters through this registry.
7. **DB and API extensions**:
   - Store provider, logical model, model IDs, tokens, cost, schema version.
   - API returns a consistent `RunResponse` for all providers.
8. **Multi-model UI layout**:
   - Same card style, multiple models side-by-side.
9. **Test & eval suite**:
   - Unit tests (schemas, JSON utils, combination logic).
   - Provider adapter tests (mocked HTTP).
   - Integration tests (CLI + API).
   - Evals (calibration / correctness) with small claim cohorts.

---

## 4. Canonical Schemas

> 2025-11-13 17:25 UTC — Worker-1 (**BlueSnow**) wired up `heretix/schemas/` with the v1 Pydantic models plus `heretix/tests/test_schemas.py` unit coverage (BD Heretix-1bb.1). Ready for downstream consumers once PR is raised.

### 4.1 Directory layout

Create:

```text
heretix/schemas/
  __init__.py
  rpl_sample_v1.py
  wel_doc_v1.py
  prior_block_v1.py
  web_block_v1.py
  combined_block_v1.py
  simple_expl_v1.py

Each file defines a Pydantic model representing the internal shape of that component.

4.2 RPL sample (RPLSampleV1)

File: heretix/schemas/rpl_sample_v1.py

from pydantic import BaseModel, Field
from typing import List

class Belief(BaseModel):
    prob_true: float = Field(ge=0.0, le=1.0)
    label: str = Field(regex="^(very_unlikely|unlikely|uncertain|likely|very_likely)$")

class Flags(BaseModel):
    refused: bool = False
    off_topic: bool = False

class RPLSampleV1(BaseModel):
    belief: Belief
    reasons: List[str]
    assumptions: List[str]
    uncertainties: List[str]
    flags: Flags = Flags()

All providers must produce RPL samples that validate against this schema.

4.3 WEL doc (WELDocV1)

File: heretix/schemas/wel_doc_v1.py

from pydantic import BaseModel, Field
from typing import List

class WELDocV1(BaseModel):
    stance_prob_true: float = Field(ge=0.0, le=1.0)
    stance_label: str = Field(regex="^(supports|contradicts|mixed|irrelevant)$")
    support_bullets: List[str]
    oppose_bullets: List[str]
    notes: List[str] = []

Each evaluated web snippet must be mapped into this shape.

4.4 Block summaries

File: heretix/schemas/prior_block_v1.py:

from pydantic import BaseModel

class PriorBlockV1(BaseModel):
    prob_true: float
    ci_lo: float
    ci_hi: float
    width: float
    stability: float
    compliance_rate: float
    # additional existing metrics can be added here

File: heretix/schemas/web_block_v1.py:

from pydantic import BaseModel

class WebBlockV1(BaseModel):
    prob_true: float
    ci_lo: float
    ci_hi: float
    evidence_strength: str  # 'weak' | 'moderate' | 'strong'
    # additional metrics as needed

File: heretix/schemas/combined_block_v1.py:

from pydantic import BaseModel

class CombinedBlockV1(BaseModel):
    prob_true: float
    ci_lo: float
    ci_hi: float
    label: str
    weight_prior: float
    weight_web: float

4.5 Simple explanation (SimpleExplV1)

File: heretix/schemas/simple_expl_v1.py:

from pydantic import BaseModel
from typing import List

class SimpleExplV1(BaseModel):
    title: str
    body_paragraphs: List[str]
    bullets: List[str] = []

The UI consumes this text structure regardless of provider.

⸻

5. Provider Capabilities & Config

5.1 Capabilities model

File: heretix/provider/config.py:

from pydantic import BaseModel
from typing import Dict

class ProviderCapabilities(BaseModel):
    provider: str                # 'openai', 'xai', 'google', 'deepseek'
    default_model: str           # logical model id, e.g. 'gpt5-default'
    api_model_map: Dict[str, str]  # logical -> concrete API model
    supports_json_schema: bool
    supports_json_mode: bool
    supports_tools: bool
    supports_seed: bool
    max_output_tokens: int
    default_temperature: float = 0.0

PROVIDERS: Dict[str, ProviderCapabilities] = {}

5.2 Provider config files

Create YAML files, e.g.:

heretix/provider/config_openai.yaml
heretix/provider/config_grok.yaml
heretix/provider/config_gemini.yaml
heretix/provider/config_deepseek.yaml

Example config_openai.yaml:

provider: "openai"
default_model: "gpt5-default"
api_model_map:
  "gpt5-default": "gpt-5.2025-01-15"
supports_json_schema: true
supports_json_mode: true
supports_tools: true
supports_seed: true
max_output_tokens: 4096
default_temperature: 0.0

Example config_grok.yaml:

provider: "xai"
default_model: "grok4-default"
api_model_map:
  "grok4-default": "grok-4"
supports_json_schema: false
supports_json_mode: true
supports_tools: false
supports_seed: true
max_output_tokens: 4096
default_temperature: 0.0

A loader function will parse these YAML files into ProviderCapabilities instances and cache them.

5.3 Logical model IDs

Use logical model IDs throughout the system (DB, API, UI):
	•	gpt5-default
	•	grok4-default
	•	gemini25-default
	•	deepseek-r1-default

Concrete API model names live only in the provider configs. Updating to a new API model version should only require editing the YAML.

⸻

6. Prompt Templates

6.1 Directory structure

heretix/prompts/
  rpl_sample/
    shared_v1.md
    openai_v1.md
    grok_v1.md
    gemini_v1.md
    deepseek_v1.md
  wel_doc/
    shared_v1.md
    openai_v1.md
    grok_v1.md
    gemini_v1.md
    deepseek_v1.md
  simple_expl/
    shared_v1.md
    narrator_v1.md

6.2 Shared intent prompt (example: RPL)

prompts/rpl_sample/shared_v1.md:
	•	Describes the RPL task in provider-agnostic terms:
	•	Evaluate a factual claim.
	•	Output a probability in [0,1] and categorical label.
	•	Provide reasons, assumptions, uncertainties.
	•	Return JSON only, matching RPLSampleV1 schema.

Provider-specific prompts (openai_v1.md, grok_v1.md, etc.):
	•	Add instructions tailored to the provider:
	•	“You are in JSON Schema mode; do not emit any non-JSON text.” (OpenAI).
	•	“Return a single JSON object. Do not preface with explanations.” (Grok/Gemini/DeepSeek).
	•	Any needed quirks.

6.3 Prompt builder

File: heretix/provider/prompt_builder.py:

def load_text(path: str) -> str:
    # load file from package resources
    ...

def build_rpl_prompt(provider: str, claim: str, paraphrase: str) -> dict:
    shared = load_text("prompts/rpl_sample/shared_v1.md")
    specific = load_text(f"prompts/rpl_sample/{provider}_v1.md")
    system = shared + "\n\n" + specific

    user = f'Claim: "{claim}"\nParaphrase: "{paraphrase}"\nReturn JSON now.'

    return {"system": system, "user": user}

Adapters will use these to construct provider-specific API requests.

⸻

7. JSON Extraction & Repair

7.1 Shared utility

File: heretix/provider/json_utils.py:

import json
from typing import Type, Tuple, List
from pydantic import BaseModel, ValidationError

def strip_markdown_json(text: str) -> str:
    # Remove ```json fences, text before the first '{', text after the last '}'.
    ...

def extract_and_validate(
    raw_text: str,
    schema_model: Type[BaseModel],
) -> Tuple[BaseModel, List[str]]:
    """
    Parse raw_text into JSON, then validate against schema_model.
    Returns (obj, warnings). Raises ValueError on hard failure.
    """
    warnings: List[str] = []

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        cleaned = strip_markdown_json(raw_text)
        data = json.loads(cleaned)
        warnings.append("json_repaired_simple")

    try:
        obj = schema_model.model_validate(data)
        return obj, warnings
    except ValidationError:
        # second chance: coercive validation
        obj = schema_model.model_validate(data, strict=False)
        warnings.append("validation_coerced")
        return obj, warnings

All provider adapters call this function with the appropriate schema (RPLSampleV1, WELDocV1, SimpleExplV1).

Later, we may add a “JSON fixer” LLM step as a fallback, but the above should capture most issues.

⸻

8. Provider Adapters

8.1 Telemetry

File: heretix/provider/telemetry.py:

from pydantic import BaseModel

class LLMTelemetry(BaseModel):
    provider: str
    logical_model: str
    api_model: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    cache_hit: bool = False

Every adapter returns telemetry alongside the schema object.

8.2 Adapter protocols and registry

File: heretix/provider/base.py:

from typing import Protocol, Tuple
from heretix.schemas.rpl_sample_v1 import RPLSampleV1
from heretix.schemas.wel_doc_v1 import WELDocV1
from heretix.schemas.simple_expl_v1 import SimpleExplV1
from .telemetry import LLMTelemetry

class RPLAdapter(Protocol):
    provider: str
    logical_model: str

    async def score_claim(
        self,
        *,
        claim: str,
        paraphrase: str,
        max_output_tokens: int,
        seed: int | None = None,
    ) -> Tuple[RPLSampleV1, LLMTelemetry]: ...

class WELAdapter(Protocol):
    provider: str
    logical_model: str

    async def score_snippet(
        self,
        *,
        claim: str,
        snippet: str,
        max_output_tokens: int,
        seed: int | None = None,
    ) -> Tuple[WELDocV1, LLMTelemetry]: ...

class ExplanationAdapter(Protocol):
    provider: str
    logical_model: str

    async def write_simple_expl(
        self,
        *,
        claim: str,
        prior_block: dict,
        web_block: dict | None,
        combined_block: dict,
    ) -> Tuple[SimpleExplV1, LLMTelemetry]: ...

Registry in heretix/provider/registry.py:

RPL_REGISTRY: dict[tuple[str, str], RPLAdapter] = {}
WEL_REGISTRY: dict[tuple[str, str], WELAdapter] = {}
EXPL_REGISTRY: dict[tuple[str, str], ExplanationAdapter] = {}

def register_rpl_adapter(adapter: RPLAdapter):
    RPL_REGISTRY[(adapter.provider, adapter.logical_model)] = adapter

def get_rpl_adapter(provider: str, logical_model: str) -> RPLAdapter:
    return RPL_REGISTRY[(provider, logical_model)]

Adapters register themselves at import-time.

8.3 GPT‑5 RPL adapter (example)

File: heretix/provider/rpl_gpt5.py (adapt existing GPT‑5 code):

from time import monotonic
from heretix.schemas.rpl_sample_v1 import RPLSampleV1
from .telemetry import LLMTelemetry
from .config import load_provider_capabilities
from .prompt_builder import build_rpl_prompt
from .json_utils import extract_and_validate

class Gpt5RPLAdapter:
    provider = "openai"
    logical_model = "gpt5-default"

    async def score_claim(
        self,
        *,
        claim: str,
        paraphrase: str,
        max_output_tokens: int,
        seed: int | None = None,
    ):
        caps = load_provider_capabilities()["openai"]
        api_model = caps.api_model_map[self.logical_model]

        prompt = build_rpl_prompt("openai", claim, paraphrase)
        # Build OpenAI Responses API request here based on caps & prompt.

        t0 = monotonic()
        response = await openai_client.responses.create(...)
        latency_ms = (monotonic() - t0) * 1000.0

        raw_text = ...  # extract text from response
        obj, warnings = extract_and_validate(raw_text, RPLSampleV1)

        telemetry = LLMTelemetry(
            provider=self.provider,
            logical_model=self.logical_model,
            api_model=api_model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=latency_ms,
        )

        return obj, telemetry

Registration (e.g. in heretix/provider/__init__.py):

from .rpl_gpt5 import Gpt5RPLAdapter
from .registry import register_rpl_adapter

register_rpl_adapter(Gpt5RPLAdapter())

Repeat analogous adapters for Grok, Gemini, DeepSeek using their respective client libraries and configs.

8.4 WEL and explanation adapters
	•	WEL adapters (wel_gpt5.py, wel_grok.py, etc.) follow a similar pattern:
	•	Use WEL-specific prompts.
	•	Return WELDocV1 + telemetry.
	•	Explanation adapter:
	•	For consistency, we can initially use a single narrator model (e.g. GPT‑5) for SimpleExplV1 across all providers.
	•	Later, we may experiment with provider-specific explanations if desired.

⸻

9. Pipeline Integration

9.1 RPL pipeline

In heretix/rpl.py, replace direct GPT‑5 calls with adapters:
	•	Resolve provider & logical model from config / runtime settings:

runtime = load_runtime_settings()
provider = cfg.provider or runtime.provider or "openai"
logical_model = cfg.logical_model or runtime.logical_model or "gpt5-default"
adapter = get_rpl_adapter(provider, logical_model)

	•	Within the sampling loop, call:

sample, telemetry = await adapter.score_claim(
    claim=claim_text,
    paraphrase=paraphrase_text,
    max_output_tokens=cfg.max_output_tokens,
    seed=seed,
)
# sample is RPLSampleV1; use this in aggregation.
# Accumulate telemetry across samples.

All other RPL math remains unchanged.

9.2 WEL pipeline

Use get_wel_adapter(provider, logical_model) inside WEL scoring:

wel_adapter = get_wel_adapter(wel_provider, wel_logical_model)
doc_sample, telemetry = await wel_adapter.score_snippet(
    claim=claim_text,
    snippet=snippet_text,
    max_output_tokens=cfg.max_output_tokens,
    seed=seed,
)
# doc_sample is WELDocV1

Aggregation into WebBlockV1 is provider-agnostic.

9.3 Combined block & explanation
	•	Combine PriorBlockV1 and WebBlockV1 numerically into CombinedBlockV1 using existing logit-based weighting logic.
	•	Use ExplanationAdapter (or narrator adapter) to produce SimpleExplV1:

expl_adapter = get_expl_adapter("narrator", "gpt5-default")  # or similar
simple_expl, telemetry = await expl_adapter.write_simple_expl(
    claim=claim_text,
    prior_block=prior_block.model_dump(),
    web_block=web_block.model_dump() if web_block else None,
    combined_block=combined_block.model_dump(),
)


⸻

10. Database & API Changes

10.1 Database (Check model)

Extend Check (in heretix/db/models.py) to include provider metadata and metrics:

provider = mapped_column(String(32), nullable=True)
logical_model = mapped_column(String(64), nullable=True)
provider_model_id = mapped_column(String(128), nullable=True)  # already present or add now

tokens_in = mapped_column(BigInteger, nullable=True)
tokens_out = mapped_column(BigInteger, nullable=True)
cost_usd = mapped_column(Numeric(10, 6), nullable=True)
schema_version = mapped_column(String(16), nullable=True)  # e.g. "v1"

Add an Alembic migration for both SQLite and Postgres.

10.2 API request/response

In api/schemas.py:
	•	RunRequest:

class RunRequest(BaseModel):
    claim: str
    mode: Literal["baseline", "web_informed"]
    provider: Optional[str] = Field(None, description="Provider id, e.g. 'openai', 'xai'")
    logical_model: Optional[str] = Field(None, description="Logical model id, e.g. 'grok4-default'")
    mock: bool = False
    # other existing fields like K/R/B, prompt_version, etc.

	•	RunResponse:

class RunResponse(BaseModel):
    # existing fields ...
    provider: str
    logical_model: str
    provider_model_id: str
    schema_version: str

    prior: PriorBlockV1
    web: Optional[WebBlockV1]
    combined: CombinedBlockV1
    simple_expl: SimpleExplV1

    tokens_in: Optional[int]
    tokens_out: Optional[int]
    cost_usd: Optional[float]

The FastAPI handler:
	•	Resolves provider/logical_model (apply defaults if not provided).
	•	Runs the pipeline.
	•	Maps the resulting Pydantic objects into RunResponse.

⸻

11. UI Multi-Model Integration

11.1 Input

In the existing UI:
	•	Replace single model dropdown with a model multi-select:
	•	Each option maps to (provider, logical_model, label), e.g:
	•	“GPT‑5” → ("openai", "gpt5-default")
	•	“Grok 4” → ("xai", "grok4-default")
	•	“Gemini 2.5” → ("google", "gemini25-default")
	•	“DeepSeek R1” → ("deepseek", "deepseek-r1-default")
	•	Context mode selection remains: “Internal knowledge only” → mode="baseline", “Internet search” → mode="web_informed".

11.2 Behavior

On form submit:
	•	Show the existing processing screen (same animation, same styles).
	•	For each selected model:
	•	POST /api/checks/run with:
	•	claim
	•	mode
	•	provider
	•	logical_model
	•	Use Promise.allSettled (or equivalent) in the front-end to collect results.

11.3 Output layout
	•	Replace single result card with a responsive grid:
	•	Desktop: 2 columns (or 3/4 depending on number of models).
	•	Tablet/mobile: 1 card per row.
	•	Each card shows:
	•	Model label (e.g. “GPT‑5 · Internet search”).
	•	combined.prob_true as a large percentage.
	•	combined.label as a verdict string.
	•	Short explanation based on simple_expl:
	•	simple_expl.title as card title.
	•	First paragraph + bullets as summary.
	•	Expandable “Deeper explanation” section:
	•	“Training-only (model prior)” – shows prior metrics and summary.
	•	“Web evidence (recent)” – shows web metrics and highlights.
	•	“How we combine” – explanation derived from combined and SimpleExplV1.

The color scheme, typography, and styling reuse existing classes and CSS.

⸻

12. Test & Evaluation Strategy

This section is designed explicitly so automated agents know what to run after changes.

> 2025-11-13 (Worker-4 / FuchsiaMountain): Added `heretix/tests/test_cli_rich_logging.py`, a mock CLI end-to-end test that prints Rich tables/logs covering inputs, function chain (`heretix.cli.cmd_run → perform_run → run_single_version`), and resulting probabilities. Treat it as the template for additional richly-instrumented tests (API, WEL) in Phase 8.

12.1 Test layout

Recommended structure:

tests/
  unit/
    test_rpl_sample_schema.py
    test_wel_doc_schema.py
    test_blocks_schema.py
    test_simple_expl_schema.py
    test_json_utils.py
    test_combine_probabilities.py
  provider/
    test_rpl_openai_adapter.py
    test_rpl_grok_adapter.py
    test_wel_openai_adapter.py
    test_wel_grok_adapter.py
  integration/
    test_cli_rpl_mock.py
    test_api_run_mock.py
  evals/
    test_evals_smoke.py

And evaluation data/scripts:

cohort/evals/
  claims_calibration.jsonl
scripts/
  run_evals.py
  run_all_evals.sh

12.2 Unit tests

12.2.1 Schema tests
	•	Validate canonical examples for RPLSampleV1, WELDocV1, block models, and SimpleExplV1.
	•	Ensure invalid values (e.g., prob_true > 1, invalid labels, missing fields) cause validation failures.

12.2.2 JSON utils
	•	Test parsing:
	•	Valid JSON string.
	•	JSON within ```json fences.
	•	JSON with leading/trailing commentary.
	•	Verify warning flags (json_repaired_simple, validation_coerced) are set appropriately.

12.2.3 Combination logic
	•	Tests for the combined probability function:
	•	Result always in (0, 1).
	•	For strong evidence, result closer to web-only probability.
	•	For equal prior and web, result equals that probability.

12.2.4 RPL math invariants
	•	Use synthetic logits arrays to test:
	•	Trimmed center behavior.
	•	Clustered bootstrap seeds.
	•	Stability scores across known perturbations.

These tests should not hit external APIs.

12.3 Provider adapter tests (mocked HTTP)

For each adapter:
	•	Mock provider API responses using responses or httpx_mock.
	•	Provide responses with:
	•	Valid JSON in the expected shape.
	•	JSON wrapped in markdown or with extra text.
	•	Assert:
	•	Adapter calls the correct URL/model.
	•	extract_and_validate yields RPLSampleV1 / WELDocV1.
	•	LLMTelemetry is correctly populated.

Mark these tests as unit so they run by default in CI.

12.4 Integration tests

12.4.1 CLI (heretix run)
	•	Use the mock provider (score_claim_mock).
	•	Run a sample config and assert:
	•	Output JSON matches expected top-level keys.
	•	Blocks validate against PriorBlockV1, CombinedBlockV1.
	•	schema_version == "v1".
	•	New: `uv run pytest heretix/tests/test_phase1_rich_logging.py -q` dumps a Rich-formatted execution trace (Worker-1 / 2025-11-13) covering inputs, CLI invocation, and resulting metrics.

12.4.2 API (/api/checks/run)
	•	Use FastAPI’s TestClient.
	•	POST a mock run with:
	•	provider="openai", logical_model="gpt5-default".
	•	mock: true.
	•	Assert:
	•	Status 200.
	•	Response conforms to RunResponse.
	•	Provider and model fields are present.

12.5 Live provider smoke tests (optional / gated)
	•	Marked as @pytest.mark.live.
	•	Only run when API keys are present.
	•	For each provider:
	•	Evaluate a known true claim (e.g. “The Earth orbits the Sun.”).
	•	Assert combined prob_true > 0.8.

These are useful for manual or nightly checks.

12.6 Evals (calibration / correctness)

12.6.1 Eval dataset
cohort/evals/claims_calibration.jsonl:

Each line:

{
  "id": "earth-orbits-sun",
  "claim": "The Earth orbits the Sun.",
  "label": 1.0,
  "category": "astronomy"
}

Include a mix of:
	•	Clearly true (1.0).
	•	Clearly false (0.0).
	•	Ambiguous (0.5 or null if unlabeled).

12.6.2 Eval runner
File: scripts/run_evals.py:
	•	Arguments:
	•	--provider
	•	--logical-model
	•	--mode baseline|web_informed
	•	For each claim:
	•	Call the RPL/WEL pipeline (Python function or API).
	•	Collect combined.prob_true.
	•	Compute metrics:
	•	Brier score.
	•	Expected calibration error (ECE).
	•	Output JSON report (e.g., evals/openai-gpt5-default-baseline.json).

12.6.3 Eval tests
tests/evals/test_evals_smoke.py:
	•	Run run_evals.py in a mode that uses mock provider.
	•	Assert:
	•	The script produces a JSON file.
	•	The file contains expected fields (brier, ece, etc.).

⸻

13. Agent Workflow Recommendations

13.1 Commands

For automated agents (or humans):
	•	Run fast tests (no external APIs):

uv run pytest -q -m "not live and not evals"


	•	Run evals for a provider (if keys set):

uv run python scripts/run_evals.py \
  --provider openai \
  --logical-model gpt5-default \
  --mode baseline


	•	Run all evals (opt-in):

bash scripts/run_all_evals.sh


	•	Pre-deploy verification:
If present, verify-production.sh can be used as a stricter gate.

13.2 Types of changes and what to run
	•	Schema changes (heretix/schemas/...)
	•	Always run:
	•	tests/unit/test_*schema.py
	•	tests/unit/test_json_utils.py
	•	Also run integration tests (tests/integration).
	•	Provider adapter changes
	•	Run:
	•	tests/provider/test_rpl_*_adapter.py
	•	tests/provider/test_wel_*_adapter.py
	•	tests/integration/test_api_run_mock.py
	•	Optionally run scripts/run_evals.py for that provider.
	•	Pipeline math changes
	•	Run:
	•	tests/unit/test_combine_probabilities.py
	•	RPL/WEL unit tests.
	•	Integration tests.
	•	UI changes
	•	Run backend tests as above.
	•	Optional: UI smoke tests (Playwright/Cypress) if configured.

⸻

14. Implementation Phases Summary
	1.	Phase 1 – Canonical Schemas
	•	Add Pydantic models for RPL samples, WEL docs, blocks, explanation.
	•	Wire them into existing pipeline where possible.
	2.	Phase 2 – Capabilities & Prompts
	•	Add provider capability configs (YAML).
	•	Add prompt templates and builder functions.
	3.	Phase 3 – JSON Utils
	•	Implement standardized JSON parsing & validation.
	4.	Phase 4 – Provider Adapters
	•	Wrap GPT‑5 into RPL/WEL/Explanation adapters.
	•	Integrate Grok from existing branch into its own adapters.
	•	Add Gemini/DeepSeek adapters as needed.
	5.	Phase 5 – Pipeline Integration
	•	Swap direct GPT‑5 calls for adapter calls.
	•	Ensure RPL/WEL still produce the same metrics for GPT‑5 as before.
	6.	Phase 6 – DB & API
	•	Extend Check model with provider/logical_model/tokens/cost/schema_version.
	•	Extend RunRequest/RunResponse.
	•	Verify API with integration tests.
	7.	Phase 7 – UI Multi-Model
	•	Add multi-select model input.
	•	Render multiple result cards using the same design.
	•	Preserve color scheme and layout.
	8.	Phase 8 – Tests & Evals
	•	Implement unit, provider, integration, and eval tests.
	•	Integrate test/eval commands into CI.

> Worker-3 (LilacHill, 2025-11-13 17:24 UTC): Owning Phase 8 via BD `Heretix-1bb.17`, `Heretix-2jf.18`, `Heretix-dph`. Delivered the first Rich CLI/API pytest (baseline + web_informed) with DB assertions. Next steps: schema/unit coverage (`heretix/schemas`, `provider/json_utils`), provider adapter mocks (`heretix/tests/test_provider_registry.py` + fixtures), and extended logging for eval datasets.

⸻

This plan should give a clear, stable architecture for multi-model Heretix, while being explicit enough for automated agents (and humans) to modify safely and verify their changes through tests and evals.
