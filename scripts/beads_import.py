#!/usr/bin/env python3
"""
Parse the embedded multi-ai-plan Markdown and populate a 'beads' task database
using the `bd` CLI:
 - For every level-2 Markdown header (lines starting with '## '), create a parent task.
 - For every bullet under that header (until the next '## '), create a child task.

Bullets are lines starting with '-' or '•' (outside code fences). We capture the
first line of each bullet as the task name.

The script handles parsing and subprocess errors gracefully and prints a summary.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
import os
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Embedded plan content (source: user-provided)
# -----------------------------

PLAN = r'''
Here’s a ready-to-drop multi-ai-plan.md for your repo.

# Multi-Model Architecture & Refactor Plan (Heretix / hx)

This document describes how to evolve the current hx / Heretix system from a **GPT‑5-only** implementation into a **multi-model** system supporting GPT‑5, Grok, Gemini, DeepSeek (and future models), while:

- Preserving the existing RPL/WEL math and pipeline.
- Preserving the existing UI look and feel.
- Exposing a **uniform, stable output schema** to the UI and API regardless of provider.
- Adding a **dense unit test and evaluation suite** suitable for automated agent iteration.

The intent is that any engineer or automated agent can safely follow this plan to extend and maintain the system over time.

---

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

```

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

## 5. Provider Capabilities & Config

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

## 6. Prompt Templates

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

## 7. JSON Extraction & Repair

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

## 8. Provider Adapters

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

## 9. Pipeline Integration

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

## 10. Database & API Changes

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

## 11. UI Multi-Model Integration

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

## 12. Test & Evaluation Strategy

This section is designed explicitly so automated agents know what to run after changes.

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

## 13. Agent Workflow Recommendations

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

## 14. Implementation Phases Summary
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

⸻

This plan should give a clear, stable architecture for multi-model Heretix, while being explicit enough for automated agents (and humans) to modify safely and verify their changes through tests and evals.
'''


# -----------------------------
# Parsing and creation logic
# -----------------------------

HEADER_RE = re.compile(r"^##\s+(.*)")
BULLET_RE = re.compile(r"^\s*([\-\u2022])\s+(.*)")  # '-' or '•'
CODE_FENCE_RE = re.compile(r"^```")


@dataclass
class Section:
    title: str
    start: int
    end: int
    bullets: List[str] = field(default_factory=list)


def parse_sections(md: str) -> List[Section]:
    lines = md.splitlines()
    n = len(lines)
    headers: List[Tuple[str, int]] = []
    in_code = False

    # Discover level-2 headers only
    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")
        if CODE_FENCE_RE.match(line.strip()):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADER_RE.match(line)
        if m:
            headers.append((m.group(1).strip(), i))

    sections: List[Section] = []
    for idx, (title, start_idx) in enumerate(headers):
        end_idx = headers[idx + 1][1] if idx + 1 < len(headers) else n
        sections.append(Section(title=title, start=start_idx, end=end_idx))

    # Extract bullets for each section
    for sec in sections:
        in_code = False
        for i in range(sec.start + 1, sec.end):
            line = lines[i]
            if CODE_FENCE_RE.match(line.strip()):
                in_code = not in_code
                continue
            if in_code:
                continue
            m = BULLET_RE.match(line)
            if m:
                text = m.group(2).strip()
                # Skip empty/placeholder bullets
                if text and set(text) != {"-"}:
                    sec.bullets.append(text)
        # Deduplicate consecutive identical bullets (defensive)
        deduped: List[str] = []
        for b in sec.bullets:
            if not deduped or deduped[-1] != b:
                deduped.append(b)
        sec.bullets = deduped

    return sections


def parse_id_from_stdout(stdout: str) -> str:
    s = (stdout or "").strip()
    # Prefer explicit creation lines like: "✓ Created issue: Heretix-5ks"
    # or "Created task: XYZ-123"
    patterns = [
        r"Created\s+issue:\s*(\S+)",
        r"Created\s+task:\s*(\S+)",
        r"Created\s+item:\s*(\S+)",
        r"Issue:\s*(\S+)",
        r"Task:\s*(\S+)",
        r"ID:\s*(\S+)",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if m:
            return m.group(1)

    # Try UUID
    m = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s)
    if m:
        return m.group(0)

    # Try a project-style key like ABC-123 or Name-abc
    m = re.search(r"[A-Za-z]+-[0-9A-Za-z]+", s)
    if m:
        return m.group(0)

    # Fallback: last non-empty line
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines:
        return lines[-1]
    return ""


def bd_create(name: str, parent_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    args = ["bd", "create", name]
    if parent_id:
        args += ["--parent", parent_id]
    try:
        res = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as e:
        return None, f"bd_not_found: {e}"
    except Exception as e:
        return None, f"subprocess_error: {e}"

    if res.returncode != 0:
        return None, f"nonzero_exit({res.returncode}): {res.stderr.strip()}"

    ident = parse_id_from_stdout(res.stdout)
    if not ident:
        return None, f"could_not_parse_id_from_stdout: {res.stdout!r}"
    return ident, None


def main() -> int:
    bd_path = shutil.which("bd")
    quiet = os.getenv("QUIET") is not None
    if not bd_path:
        print("[warn] bd CLI not found in PATH. The script will attempt to run and will likely report bd_not_found for each item.")

    try:
        sections = parse_sections(PLAN)
    except Exception as e:
        print(f"[error] failed_to_parse_plan: {e}")
        return 2

    created_headers: Dict[str, str] = {}
    created_tasks: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    for sec in sections:
        header_name = sec.title
        hid, herr = bd_create(header_name)
        if herr:
            errors.append({"type": "header", "name": header_name, "error": herr})
            if not quiet:
                print(f"[error] header '{header_name}': {herr}")
            continue
        created_headers[header_name] = hid  # type: ignore[arg-type]
        if not quiet:
            print(f"[ok] header created: '{header_name}' -> {hid}")

        for bullet in sec.bullets:
            tid, terr = bd_create(bullet, parent_id=hid)
            if terr:
                errors.append({"type": "task", "parent": header_name, "name": bullet, "error": terr})
                if not quiet:
                    print(f"[error]  task '{bullet}' under '{header_name}': {terr}")
                continue
            created_tasks.append({"parent": header_name, "parent_id": hid, "task": bullet, "id": tid})
            if not quiet:
                print(f"[ok]  task created under '{header_name}': '{bullet}' -> {tid}")

    summary = {
        "headers": len(created_headers),
        "tasks": len(created_tasks),
        "errors": len(errors),
        "bd_available": bool(bd_path),
    }
    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2))

    # Emit a machine-readable artifact to stdout (single line) for callers, if desired
    print("\nRESULT_JSON::" + json.dumps({
        "created_headers": created_headers,
        "created_tasks": created_tasks,
        "errors": errors,
    }))

    # Exit code 0 even with errors, per "handle gracefully" requirement
    return 0


if __name__ == "__main__":
    sys.exit(main())
