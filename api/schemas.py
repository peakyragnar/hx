from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RunRequest(BaseModel):
    claim: str = Field(..., min_length=1, description="The claim to evaluate")
    mode: Optional[str] = Field("baseline", description="Evaluation mode: baseline or web_informed")
    model: Optional[str] = Field(None, description="Override model id")
    prompt_version: Optional[str] = Field(None, description="Override prompt version")
    K: Optional[int] = Field(None, ge=1)
    R: Optional[int] = Field(None, ge=1)
    B: Optional[int] = Field(None, ge=1)
    max_output_tokens: Optional[int] = Field(None, ge=1)
    seed: Optional[int] = None
    no_cache: Optional[bool] = None
    mock: Optional[bool] = Field(None, description="Force mock provider for this run")


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


class PriorBlock(BaseModel):
    p: float
    ci95: List[float]
    stability: Optional[float] = None


class WebCitation(BaseModel):
    url: str
    domain: Optional[str] = None
    quote: Optional[str] = None
    stance: Optional[str] = None
    field: Optional[str] = None
    value: Optional[str] = None
    weight: Optional[float] = None
    published_at: Optional[str] = None


class WebEvidence(BaseModel):
    p: float
    ci95: List[float]
    evidence: Dict[str, float]
    resolved: bool = False
    resolved_truth: Optional[bool] = None
    resolved_reason: Optional[str] = None
    resolved_citations: List[WebCitation] = []
    support: Optional[float] = None
    contradict: Optional[float] = None
    domains: Optional[int] = None


class CombinedResult(BaseModel):
    p: float
    ci95: List[float]
    resolved: bool = False
    resolved_truth: Optional[bool] = None
    resolved_reason: Optional[str] = None
    resolved_citations: List[WebCitation] = []
    support: Optional[float] = None
    contradict: Optional[float] = None
    domains: Optional[int] = None


class WeightInfo(BaseModel):
    w_web: float
    recency: float
    strength: float


class RunResponse(BaseModel):
    execution_id: str
    run_id: str
    claim: Optional[str]
    model: str
    prompt_version: str
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
    prior: Optional[PriorBlock] = None
    web: Optional[WebEvidence] = None
    combined: Optional[CombinedResult] = None
    weights: Optional[WeightInfo] = None
    provenance: Optional[Dict[str, object]] = None


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
