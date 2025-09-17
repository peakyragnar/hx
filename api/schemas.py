from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RunRequest(BaseModel):
    claim: str = Field(..., min_length=1, description="The claim to evaluate")
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
    plan: str = Field(..., regex="^(starter|core|pro)$")


class CheckoutResponse(BaseModel):
    checkout_url: str
