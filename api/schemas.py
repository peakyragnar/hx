from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from heretix.schemas import CombinedBlockV1, PriorBlockV1, SimpleExplV1, WebBlockV1


class RunRequest(BaseModel):
    claim: str = Field(..., min_length=1, description="The claim to evaluate")
    mode: str = Field("baseline", description="Evaluation mode (baseline or web_informed)")
    provider: Optional[str] = Field(None, description="Provider id (e.g., openai, xai, google)")
    logical_model: Optional[str] = Field(None, description="Logical model id (e.g., gpt5-default)")
    model: Optional[str] = Field(None, description="Override model id (legacy alias)")
    models: Optional[List[str]] = Field(None, description="List of logical models for bias_fast runs")
    profile: Optional[str] = Field(None, description="Harness profile to apply (e.g., bias_fast)")
    prompt_version: Optional[str] = Field(None, description="Override prompt version")
    K: Optional[int] = Field(None, ge=1)
    R: Optional[int] = Field(None, ge=1)
    B: Optional[int] = Field(None, ge=1)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    seed: Optional[int] = None
    no_cache: Optional[bool] = None
    mock: Optional[bool] = Field(None, description="Force mock provider for this run")
    request_id: Optional[str] = Field(None, description="Client-supplied request grouping id (UUID)")

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: str | None) -> str:
        if value is None or str(value).strip() == "":
            return "baseline"
        normalized = str(value).strip().lower()
        if normalized not in {"baseline", "web_informed"}:
            raise ValueError("mode must be 'baseline' or 'web_informed'")
        return normalized


class AggregationInfo(BaseModel):
    method: Optional[str]
    B: int
    center: Optional[str]
    trim: Optional[float]
    bootstrap_seed: Optional[int]
    n_templates: Optional[int]
    counts_by_template: Dict[str, int]
    imbalance_ratio: Optional[float]
    template_iqr_logit: Optional[float]
    prompt_char_len_max: Optional[int]


class Aggregates(BaseModel):
    prob_true_rpl: float
    ci95: List[float]
    ci_width: float
    stability_score: float
    stability_band: Optional[str]
    is_stable: Optional[bool]
    rpl_compliance_rate: float
    cache_hit_rate: float


class SamplingInfo(BaseModel):
    K: int
    R: int
    T: Optional[int]
    warning_counts: Optional[Dict[str, int]] = None
    warning_total: Optional[int] = None


class WeightInfo(BaseModel):
    w_web: float
    recency: float
    strength: float


class WebReplicate(BaseModel):
    replicate_idx: Optional[int] = None
    p_web: Optional[float] = None
    support_bullets: Optional[List[str]] = None
    oppose_bullets: Optional[List[str]] = None
    notes: Optional[List[str]] = None
    json_valid: Optional[bool] = None


class WebArtifactPointer(BaseModel):
    manifest: str
    replicates_uri: Optional[str] = None
    docs_uri: Optional[str] = None


class BiasModelResult(BaseModel):
    name: str
    p_rpl: float
    label: str
    explanation: str
    extras: Optional[Dict[str, Any]] = None


class BiasRunResponse(BaseModel):
    run_id: str
    profile: str
    claim: str
    models: List[BiasModelResult]
    timings: Optional[Dict[str, float]] = None
    raw: Optional[Dict[str, Any]] = None
    usage_plan: Optional[str] = None
    checks_allowed: Optional[int] = None
    checks_used: Optional[int] = None
    remaining: Optional[int] = None


class RunResponse(BaseModel):
    execution_id: str
    run_id: str
    request_id: Optional[str] = None
    claim: Optional[str]
    model: str
    logical_model: str
    resolved_logical_model: Optional[str] = None
    provider: str
    provider_model_id: Optional[str] = None
    prompt_version: str
    schema_version: str
    sampling: SamplingInfo
    aggregation: AggregationInfo
    aggregates: Aggregates
    mock: bool = False
    usage_plan: Optional[str] = None
    checks_allowed: Optional[int] = None
    checks_used: Optional[int] = None
    remaining: Optional[int] = None
    verdict_label: Optional[str] = None
    verdict_text: Optional[str] = None
    explanation_headline: Optional[str] = None
    explanation_text: Optional[str] = None
    explanation_reasons: Optional[List[str]] = None
    mode: str = "baseline"
    prior: Optional[PriorBlockV1] = None
    web: Optional[WebBlockV1] = None
    combined: Optional[CombinedBlockV1] = None
    weights: Optional[WeightInfo] = None
    provenance: Optional[Dict[str, object]] = None
    web_artifact: Optional[WebArtifactPointer] = None
    wel_replicates: Optional[List[WebReplicate]] = None
    wel_debug_votes: Optional[List[Dict[str, object]]] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    simple_expl: Optional[SimpleExplV1] = None


class MagicLinkPayload(BaseModel):
    email: EmailStr


class MeResponse(BaseModel):
    authenticated: bool
    email: Optional[EmailStr] = None
    plan: Optional[str] = None
    usage_plan: Optional[str] = None
    checks_allowed: Optional[int] = None
    checks_used: Optional[int] = None
    remaining: Optional[int] = None


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(starter|core|pro)$")


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str
