from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from heretix.config import RunConfig
from heretix.provider.factory import get_rpl_adapter
from heretix.provider.mock import score_claim_mock
from heretix.provider.utils import infer_provider_from_model
from heretix.explanations import extract_reasons
from heretix.pipeline import PipelineOptions, perform_run
from heretix.constants import SCHEMA_VERSION
from heretix.rpl import ProviderResolutionError
from heretix.schemas import CombinedBlockV1, PriorBlockV1, SimpleExplV1, WebBlockV1, WebEvidenceStats

from .auth import complete_magic_link, get_current_user, handle_magic_link, sign_out
from .config import settings
from .database import get_session
from .schemas import (
    AggregationInfo,
    Aggregates,
    MagicLinkPayload,
    MeResponse,
    CheckoutRequest,
    CheckoutResponse,
    PortalResponse,
    RunRequest,
    RunResponse,
    SamplingInfo,
    WeightInfo,
    WebArtifactPointer,
)
from heretix.db.models import Check, User
from .usage import ANON_PLAN, get_usage_state, increment_usage
from .billing import (
    create_checkout_session,
    create_portal_session,
    handle_checkout_completed,
    handle_subscription_deleted,
    handle_subscription_updated,
)
from heretix_api.routes_checks import evaluate_web_informed

logger = logging.getLogger(__name__)

app = FastAPI(title="Heretix API", version="0.1.0")

allowed_origins = {
    "https://heretix.ai",
    "https://www.heretix.ai",
    "https://heretix-ui.vercel.app",
    "https://heretix-api.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"]
)


ANON_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def ensure_anon_token(request: Request, response: Response) -> str:
    token = request.cookies.get(settings.anon_cookie_name)
    if token:
        return token
    token = secrets.token_urlsafe(32)
    cookie_kwargs = {
        "key": settings.anon_cookie_name,
        "value": token,
        "max_age": ANON_COOKIE_MAX_AGE,
        "httponly": True,
        "samesite": "lax",
        "path": "/",
    }
    if settings.session_cookie_secure:
        cookie_kwargs["secure"] = True
    if settings.session_cookie_domain:
        cookie_kwargs["domain"] = settings.session_cookie_domain
    response.set_cookie(**cookie_kwargs)
    return token


@app.api_route("/healthz", methods=["GET", "HEAD"], tags=["system"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/checks/run", response_model=RunResponse)
def run_check(
    payload: RunRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> RunResponse:
    claim = payload.claim.strip()
    if not claim:
        raise HTTPException(status_code=422, detail="claim must not be empty")

    mode = (payload.mode or "baseline").lower()
    if mode not in {"baseline", "web_informed"}:
        raise HTTPException(status_code=400, detail="mode must be 'baseline' or 'web_informed'")

    anon_token: str | None = None
    if not user:
        anon_token = ensure_anon_token(request, response)

    usage_state = get_usage_state(session, user, anon_token=anon_token)
    if not usage_state.enough_credit:
        reason = "require_subscription" if user else "require_signin"
        raise HTTPException(status_code=402, detail={"reason": reason, "plan": usage_state.plan.name})

    logical_model = payload.logical_model or payload.model or settings.rpl_model
    requested_provider = getattr(payload, "provider", None)
    default_provider = getattr(settings, "rpl_provider", None)
    inferred_provider = infer_provider_from_model(logical_model)
    if requested_provider:
        provider = requested_provider
    elif inferred_provider:
        provider = inferred_provider
    elif default_provider:
        provider = default_provider
    else:
        provider = "openai"

    cfg = RunConfig(
        claim=claim,
        model=logical_model,
        logical_model=logical_model,
        provider=provider,
        prompt_version=payload.prompt_version or settings.rpl_prompt_version,
        K=payload.K or settings.rpl_k,
        R=payload.R or settings.rpl_r,
        B=payload.B or settings.rpl_b,
        max_output_tokens=payload.max_output_tokens or settings.rpl_max_output_tokens,
        max_prompt_chars=settings.rpl_max_prompt_chars,
        no_cache=bool(payload.no_cache) if payload.no_cache is not None else False,
    )
    cfg.seed = payload.seed if payload.seed is not None else cfg.seed

    use_mock = payload.mock if payload.mock is not None else settings.allow_mock

    prompt_root = Path(settings.prompts_dir) if settings.prompts_dir else None
    pipeline_options = PipelineOptions(
        app_env=settings.app_env,
        wel_provider=settings.wel_provider,
        wel_model=settings.wel_model,
        wel_docs=settings.wel_docs,
        wel_replicates=settings.wel_replicates,
        wel_per_domain_cap=settings.wel_per_domain_cap,
        wel_recency_days=settings.wel_recency_days,
        prompt_root=prompt_root,
    )

    try:
        artifacts = perform_run(
            session=session,
            cfg=cfg,
            mode=mode,
            options=pipeline_options,
            use_mock=use_mock,
            user_id=getattr(user, "id", None),
            anon_token=anon_token,
        )
        result = artifacts.result
    except HTTPException:
        raise
    except ProviderResolutionError as exc:
        logger.warning("Invalid provider override for claim %s: %s", claim, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        logger.exception("run_check failed for claim %s", claim)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception:
        logger.exception("Unexpected run failure for claim %s", claim)
        raise HTTPException(status_code=500, detail="internal server error")

    aggregation = result.get("aggregation", {})
    aggregates = dict(result.get("aggregates", {}))
    sampling = dict(result.get("sampling", {}))

    ci95 = aggregates.get("ci95", [None, None])
    rpl_compliance_rate = float(aggregates.get("rpl_compliance_rate", 0.0))
    cache_hit_rate = float(aggregates.get("cache_hit_rate", 0.0))
    ci_width = float(aggregates.get("ci_width", (ci95[1] or 0.0) - (ci95[0] or 0.0)))
    stability_score = float(aggregates.get("stability_score", 0.0))

    gate_compliance_ok = rpl_compliance_rate >= 0.98
    gate_stability_ok = stability_score >= 0.25
    gate_precision_ok = ci_width <= 0.30

    prior_p = float(aggregates.get("prob_true_rpl") or 0.0)
    prior_ci = [
        float(ci95[0]) if ci95 and ci95[0] is not None else 0.0,
        float(ci95[1]) if ci95 and ci95[1] is not None else 0.0,
    ]

    prior_block_payload = artifacts.prior_block
    web_block_payload = artifacts.web_block
    combined_block_payload = artifacts.combined_block
    weights_payload = artifacts.weights
    wel_provenance = artifacts.wel_provenance

    run_id = result.get("run_id")
    if not run_id:
        raise HTTPException(status_code=500, detail="run_id missing from RPL result")

    bootstrap_seed_val = aggregation.get("bootstrap_seed")
    explanation_prob = combined_block_payload["p"] if combined_block_payload else prior_p

    verdict_label, verdict_text, explanation_headline, explanation_text, explanation_reasons = build_explanation(
        claim=claim,
        prob=explanation_prob,
        cfg=cfg,
        prompt_file=artifacts.prompt_file,
        use_mock=use_mock,
        max_output_tokens=cfg.max_output_tokens,
    )

    if mode == "web_informed" and web_block_payload:
        explanation_headline, explanation_text, explanation_reasons = build_web_explanation(
            prior_block=prior_block_payload,
            combined_block=combined_block_payload,
            web_block=web_block_payload,
            weights=weights_payload,
            wel_replicates=artifacts.wel_replicates,
        )

    checks_allowed = usage_state.checks_allowed
    used_after = usage_state.checks_used
    remaining_after = max(checks_allowed - used_after, 0) if checks_allowed else None

    check = artifacts.check
    check.gate_compliance_ok = gate_compliance_ok
    check.gate_stability_ok = gate_stability_ok
    check.gate_precision_ok = gate_precision_ok

    try:
        used_after = increment_usage(session, user, usage_state)
        remaining_after = max(checks_allowed - used_after, 0) if checks_allowed else None
        session.commit()
    except ProgrammingError as exc:
        session.rollback()
        logging.warning("Skipping DB persistence for run %s due to schema mismatch: %s", run_id, exc)
        try:
            refreshed_state = get_usage_state(session, user, anon_token=anon_token)
            used_after = increment_usage(session, user, refreshed_state)
            remaining_after = (
                max(refreshed_state.checks_allowed - used_after, 0)
                if refreshed_state.checks_allowed
                else None
            )
            session.commit()
        except Exception:  # pragma: no cover - best-effort fallback when schema is stale
            session.rollback()
            used_after = usage_state.checks_used
            remaining_after = max(checks_allowed - used_after, 0) if checks_allowed else None
    except Exception:
        session.rollback()
        raise

    provider_id = result.get("provider") or cfg.provider or infer_provider_from_model(cfg.model) or "openai"
    logical_model_requested = result.get("logical_model", cfg.logical_model or cfg.model)
    logical_model_resolved = result.get("resolved_logical_model", result.get("model", cfg.model))
    provider_model_id = result.get("provider_model_id")
    schema_version = result.get("schema_version", SCHEMA_VERSION)
    tokens_in = result.get("tokens_in")
    tokens_out = result.get("tokens_out")
    cost_usd = result.get("cost_usd")

    prior_block_model = _build_prior_block_v1(prior_block_payload, rpl_compliance_rate)
    web_block_model = _build_web_block_v1(web_block_payload, weights_payload)
    combined_block_model = _build_combined_block_v1(combined_block_payload)
    weights_model = WeightInfo(**weights_payload) if weights_payload else None
    provenance_payload: dict[str, object] = {
        "rpl": {
            "prompt_version": result.get("prompt_version", cfg.prompt_version),
            "model": logical_model_resolved,
            "logical_model": logical_model_requested,
            "provider": provider_id,
            "provider_model_id": provider_model_id,
            "schema_version": schema_version,
        }
    }
    if wel_provenance:
        provenance_payload["wel"] = wel_provenance

    web_artifact_pointer: WebArtifactPointer | None = None
    if artifacts.artifact_manifest_uri:
        web_artifact_pointer = WebArtifactPointer(
            manifest=artifacts.artifact_manifest_uri,
            replicates_uri=artifacts.artifact_replicates_uri,
            docs_uri=artifacts.artifact_docs_uri,
        )

    simple_expl_model = _build_simple_expl_v1(artifacts.simple_expl)

    return RunResponse(
        execution_id=result.get("execution_id"),
        run_id=run_id,
        claim=result.get("claim"),
        model=result.get("model", cfg.model),
        logical_model=logical_model_requested,
        resolved_logical_model=logical_model_resolved,
        provider=provider_id,
        provider_model_id=provider_model_id,
        prompt_version=result.get("prompt_version", cfg.prompt_version),
        schema_version=schema_version,
        sampling=SamplingInfo(**sampling),
        aggregation=AggregationInfo(
            method=aggregation.get("method"),
            B=int(aggregation.get("B", cfg.B)),
            center=aggregation.get("center"),
            trim=aggregation.get("trim"),
            bootstrap_seed=int(bootstrap_seed_val) if bootstrap_seed_val is not None else None,
            n_templates=aggregation.get("n_templates"),
            counts_by_template=aggregation.get("counts_by_template", {}),
            imbalance_ratio=aggregation.get("imbalance_ratio"),
            template_iqr_logit=aggregation.get("template_iqr_logit"),
            prompt_char_len_max=aggregation.get("prompt_char_len_max"),
        ),
        aggregates=Aggregates(**aggregates),
        mock=use_mock,
        usage_plan=usage_state.plan.name,
        checks_allowed=checks_allowed,
        checks_used=used_after,
        remaining=remaining_after,
        verdict_label=verdict_label,
        verdict_text=verdict_text,
        explanation_headline=explanation_headline,
        explanation_text=explanation_text,
        explanation_reasons=explanation_reasons,
        mode=mode,
        prior=prior_block_model,
        web=web_block_model,
        combined=combined_block_model,
        weights=weights_model,
        provenance=provenance_payload,
        web_artifact=web_artifact_pointer,
        wel_replicates=artifacts.wel_replicates or None,
        wel_debug_votes=artifacts.wel_debug_votes or None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        simple_expl=simple_expl_model,
    )


def _build_prior_block_v1(payload: Dict[str, object], compliance_rate: float) -> PriorBlockV1:
    ci_vals = payload.get("ci95") or [payload.get("p", 0.0), payload.get("p", 0.0)]
    ci_lo = float(ci_vals[0]) if len(ci_vals) >= 1 and ci_vals[0] is not None else float(payload.get("p", 0.0))
    ci_hi = float(ci_vals[1]) if len(ci_vals) >= 2 and ci_vals[1] is not None else float(payload.get("p", 0.0))
    prob_true = float(payload.get("p", 0.0))
    width = max(0.0, ci_hi - ci_lo)
    stability = float(payload.get("stability", 0.0))
    compliance = max(0.0, min(1.0, float(compliance_rate)))
    return PriorBlockV1(
        prob_true=prob_true,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        width=width,
        stability=stability,
        compliance_rate=compliance,
    )


def _coerce_non_negative_int(value: object) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _coerce_non_negative_float(value: object) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _sanitize_citations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple, set)):
        return []
    cleaned: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            citation: dict[str, object] = {}
            url = item.get("url")
            domain = item.get("domain")
            quote = item.get("quote")
            stance = item.get("stance")
            field = item.get("field")
            val = item.get("value")
            weight = item.get("weight")
            published_at = item.get("published_at")
            if isinstance(url, str) and url.strip():
                citation["url"] = url.strip()
            if isinstance(domain, str) and domain.strip():
                citation["domain"] = domain.strip()
            if isinstance(quote, str) and quote.strip():
                citation["quote"] = quote.strip()
            if isinstance(stance, str) and stance.strip():
                citation["stance"] = stance.strip()
            if isinstance(field, str) and field.strip():
                citation["field"] = field.strip()
            if val is not None:
                citation["value"] = val
            if isinstance(weight, (int, float)):
                citation["weight"] = float(weight)
            if isinstance(published_at, str) and published_at.strip():
                citation["published_at"] = published_at.strip()
            if citation:
                cleaned.append(citation)
        elif isinstance(item, str):
            stripped = item.strip()
            if stripped:
                cleaned.append({"url": stripped})
    return cleaned


def _build_web_block_v1(payload: Optional[Dict[str, object]], weights: Optional[Dict[str, float]]) -> Optional[WebBlockV1]:
    if not payload:
        return None
    ci_vals = payload.get("ci95") or [payload.get("p", 0.0), payload.get("p", 0.0)]
    ci_lo = float(ci_vals[0]) if len(ci_vals) >= 1 and ci_vals[0] is not None else float(payload.get("p", 0.0))
    ci_hi = float(ci_vals[1]) if len(ci_vals) >= 2 and ci_vals[1] is not None else float(payload.get("p", 0.0))
    prob_true = float(payload.get("p", 0.0))
    strength_val = (weights or {}).get("strength")
    evidence_strength = _evidence_strength_label(strength_val)
    resolved_flag = payload.get("resolved")
    if isinstance(resolved_flag, bool):
        resolved_bool = resolved_flag
    elif resolved_flag is None:
        resolved_bool = None
    else:
        resolved_bool = None
    resolved_truth_val = payload.get("resolved_truth")
    resolved_truth = resolved_truth_val if isinstance(resolved_truth_val, bool) else None
    resolved_reason_raw = payload.get("resolved_reason")
    resolved_reason = None
    if isinstance(resolved_reason_raw, str):
        resolved_reason = resolved_reason_raw.strip() or None
    resolved_citations = _sanitize_citations(payload.get("resolved_citations"))
    raw_evidence = payload.get("evidence")
    evidence_payload = raw_evidence if isinstance(raw_evidence, dict) else {}
    evidence_model = None
    if evidence_payload:
        evidence_model = WebEvidenceStats(
            n_docs=_coerce_non_negative_int(evidence_payload.get("n_docs")),
            n_domains=_coerce_non_negative_int(evidence_payload.get("n_domains")),
            median_age_days=_coerce_non_negative_float(evidence_payload.get("median_age_days")),
        )
    return WebBlockV1(
        prob_true=prob_true,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        evidence_strength=evidence_strength,
        resolved=resolved_bool,
        resolved_truth=resolved_truth,
        resolved_reason=resolved_reason,
        resolved_citations=resolved_citations,
        support=_coerce_non_negative_float(payload.get("support")),
        contradict=_coerce_non_negative_float(payload.get("contradict")),
        domains=_coerce_non_negative_int(payload.get("domains")),
        evidence=evidence_model,
        resolved_debug_votes=payload.get("resolved_debug_votes"),
    )


def _build_combined_block_v1(payload: Optional[Dict[str, object]]) -> Optional[CombinedBlockV1]:
    if not payload:
        return None
    prob_true = float(payload.get("p", 0.0))
    ci_vals = payload.get("ci95")
    if isinstance(ci_vals, (list, tuple)) and len(ci_vals) >= 2:
        ci_lo = float(ci_vals[0])
        ci_hi = float(ci_vals[1])
    else:
        ci_lo = float(payload.get("ci_lo", prob_true))
        ci_hi = float(payload.get("ci_hi", prob_true))
    label = str(payload.get("label", "Uncertain"))
    weight_prior = float(payload.get("weight_prior", 1.0))
    weight_web = float(payload.get("weight_web", 0.0))
    resolved_flag = payload.get("resolved")
    if isinstance(resolved_flag, bool):
        resolved_bool = resolved_flag
    elif resolved_flag is None:
        resolved_bool = None
    else:
        resolved_bool = None
    resolved_truth_val = payload.get("resolved_truth")
    resolved_truth = resolved_truth_val if isinstance(resolved_truth_val, bool) else None
    raw_reason = payload.get("resolved_reason")
    resolved_reason = None
    if isinstance(raw_reason, str):
        resolved_reason = raw_reason.strip() or None
    resolved_citations = _sanitize_citations(payload.get("resolved_citations"))
    support_value = _coerce_non_negative_float(payload.get("support"))
    contradict_value = _coerce_non_negative_float(payload.get("contradict"))
    domains_value = _coerce_non_negative_int(payload.get("domains"))
    return CombinedBlockV1(
        prob_true=prob_true,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        ci95=[ci_lo, ci_hi],
        label=label,
        weight_prior=weight_prior,
        weight_web=weight_web,
        resolved=resolved_bool,
        resolved_truth=resolved_truth,
        resolved_reason=resolved_reason,
        resolved_citations=resolved_citations,
        support=support_value,
        contradict=contradict_value,
        domains=domains_value,
    )


def _build_simple_expl_v1(simple_block: Optional[Dict[str, object]]) -> Optional[SimpleExplV1]:
    if not simple_block:
        return None
    title = str(simple_block.get("title") or "Why this verdict looks this way").strip()
    body_paragraphs_raw = simple_block.get("body_paragraphs")
    bullets_raw = simple_block.get("bullets")
    if isinstance(body_paragraphs_raw, list) and isinstance(bullets_raw, list):
        body_paragraphs = [str(p).strip() for p in body_paragraphs_raw if str(p).strip()]
        bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]
        if not body_paragraphs:
            body_paragraphs = ["Explanation not available."]
        return SimpleExplV1(title=title, body_paragraphs=body_paragraphs, bullets=bullets)

    summary = str(simple_block.get("summary") or "The model provided no additional explanation.").strip()
    body_paragraphs = [summary] if summary else ["Explanation not available."]
    raw_lines = simple_block.get("lines") or []
    bullets = [str(line).strip() for line in raw_lines if str(line).strip()]
    if not bullets:
        bullets = ["No supporting bullets were generated."]
    return SimpleExplV1(title=title, body_paragraphs=body_paragraphs, bullets=bullets)


def _evidence_strength_label(value: Optional[float]) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.66:
        return "strong"
    if score >= 0.33:
        return "moderate"
    return "weak"
@app.post(
    "/api/auth/magic-links",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def request_magic_link(payload: MagicLinkPayload, session: Session = Depends(get_session)) -> Response:
    handle_magic_link(payload.email, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/auth/callback")
def magic_link_callback(token: str, session: Session = Depends(get_session)):
    return complete_magic_link(token, session)


@app.post(
    "/api/auth/signout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def auth_signout(request: Request, session: Session = Depends(get_session)) -> Response:
    return sign_out(request, session)


@app.get("/api/me", response_model=MeResponse)
def read_me(
    request: Request,
    response: Response,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    if not user:
        anon_token = ensure_anon_token(request, response)
        state = get_usage_state(session, None, anon_token=anon_token)
        return MeResponse(
            authenticated=False,
            usage_plan=state.plan.name,
            checks_allowed=state.checks_allowed,
            checks_used=state.checks_used,
            remaining=state.remaining,
        )
    state = get_usage_state(session, user)
    return MeResponse(
        authenticated=True,
        email=user.email,
        plan=getattr(user, "plan", None) or state.plan.name,
        usage_plan=state.plan.name,
        checks_allowed=state.checks_allowed,
        checks_used=state.checks_used,
        remaining=state.remaining,
    )


@app.post("/api/billing/checkout", response_model=CheckoutResponse)
def create_checkout(
    payload: CheckoutRequest,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> CheckoutResponse:
    if not user:
        raise HTTPException(status_code=401, detail="Sign-in required")
    url = create_checkout_session(session, user, payload.plan)
    return CheckoutResponse(checkout_url=url)


@app.post("/api/billing/portal", response_model=PortalResponse)
def create_portal(
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> PortalResponse:
    if not user:
        raise HTTPException(status_code=401, detail="Sign-in required")
    url = create_portal_session(session, user)
    return PortalResponse(portal_url=url)


@app.post(
    "/api/stripe/webhook",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def stripe_webhook(request: Request, session: Session = Depends(get_session)) -> Response:
    if not settings.stripe_webhook_secret or not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe integration not configured")
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    import stripe

    try:
        event = stripe.Webhook.construct_event(
            payload=payload.decode("utf-8"),
            sig_header=signature,
            secret=settings.stripe_webhook_secret,
        )
    except Exception as exc:  # pragma: no cover - signature failures
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    event_type = event.get("type")
    data_obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        handle_checkout_completed(session, data_obj)
    elif event_type == "customer.subscription.updated":
        handle_subscription_updated(session, data_obj)
    elif event_type in {"customer.subscription.deleted", "customer.subscription.cancelled"}:
        handle_subscription_deleted(session, data_obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def build_explanation(
    *,
    claim: str,
    prob: float | None,
    cfg: RunConfig,
    prompt_file: str | Path,
    use_mock: bool,
    max_output_tokens: int | None,
) -> tuple[str, str, str, str, list[str]]:
    verdict_label, verdict_text, headline, interpretation = classify_probability(prob)
    system_text, user_template, paraphrases = load_prompt_components(prompt_file)
    paraphrase_text = paraphrases[0] if paraphrases else "Without retrieval, estimate P(true) for: {CLAIM}"
    tokens = max_output_tokens or cfg.max_output_tokens or settings.rpl_max_output_tokens

    reasons: list[str] = []
    if use_mock:
        reasons = fallback_reasons(prob)
    elif system_text and user_template and paraphrase_text:
        adapter = get_rpl_adapter(provider_mode="MOCK" if use_mock else "LIVE", model=cfg.model)
        try:
            out = adapter.score_claim(
                claim=claim,
                system_text=system_text,
                user_template=user_template,
                paraphrase_text=paraphrase_text,
                model=cfg.model,
                max_output_tokens=tokens,
            )
            reasons = extract_reasons(out)
        except Exception as exc:  # pragma: no cover - best-effort explanation
            logging.warning("Explanation provider call failed: %s", exc)

    if not reasons:
        reasons = fallback_reasons(prob)

    return verdict_label, verdict_text, headline, interpretation, reasons


def _normalize_reason_line(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parsed = value
        text = ""
        for key in ("reason", "text", "message", "summary", "content"):
            candidate = parsed.get(key)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate.strip()
                break
        if not text:
            text = json.dumps(parsed, ensure_ascii=False)
    elif isinstance(value, (list, tuple, set)):
        parts = [_normalize_reason_line(item) for item in value]
        text = " ".join(part for part in parts if part).strip()
    else:
        text = str(value).strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                for key in ("reason", "text", "message", "summary", "content"):
                    candidate = parsed.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        text = candidate.strip()
                        break
    if not text:
        return ""
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1].strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def build_web_explanation(
    *,
    prior_block: dict[str, object],
    combined_block: dict[str, object] | None,
    web_block: dict[str, object],
    weights: dict[str, object] | None,
    wel_replicates: list[dict[str, object]] | None,
) -> tuple[str, str, list[str]]:
    def _fmt_percent(val: float | None) -> str:
        if val is None:
            return "--"
        return f"{val * 100:.1f}%"

    combined_percent = _fmt_percent((combined_block or {}).get("p") if combined_block else None)
    prior_percent = _fmt_percent(prior_block.get("p"))
    web_percent = _fmt_percent(web_block.get("p"))
    metrics = web_block.get("evidence", {}) or {}
    n_docs = int(metrics.get("n_docs") or 0)
    n_domains = int(metrics.get("n_domains") or 0)
    median_age = metrics.get("median_age_days")
    weight_val = (weights or {}).get("w_web")

    headline = "Why the web-informed verdict looks this way"
    summary_text = (
        f"Combining GPT-5’s prior ({prior_percent}) with web evidence ({web_percent}) "
        f"yields {combined_percent}."
    )

    reason_lines: list[str] = [
        (
            f"Web evidence across {n_docs} document{'s' if n_docs != 1 else ''} "
            f"from {n_domains} domain{'s' if n_domains != 1 else ''} moved GPT-5’s prior from "
            f"{prior_percent} to {combined_percent}."
        )
    ]

    if isinstance(median_age, (int, float)) and median_age == median_age:
        reason_lines.append(
            f"Median publish date was about {int(round(median_age))} day"
            f"{'s' if abs(int(round(median_age))) != 1 else ''} ago, so fresher coverage could tighten the estimate."
        )

    if isinstance(weight_val, (int, float)):
        reason_lines.append(
            f"Web weighting was {weight_val:.2f}, balancing new evidence against the original prior."
        )

    seen_lines: set[str] = set(reason_lines)
    for replica in wel_replicates or []:
        for key in ("support_bullets", "oppose_bullets", "notes"):
            for item in (replica.get(key) or []):
                line = _normalize_reason_line(item)
                if not line:
                    continue
                if line not in seen_lines:
                    seen_lines.add(line)
                    reason_lines.append(line)
                if len(reason_lines) >= 6:
                    break
            if len(reason_lines) >= 6:
                break
        if len(reason_lines) >= 6:
            break

    return headline, summary_text, reason_lines


def load_prompt_components(prompt_file: str | Path) -> tuple[str, str, list[str]]:
    try:
        text = Path(prompt_file).read_text(encoding="utf-8")
        doc = yaml.safe_load(text) or {}
    except Exception:
        doc = {}
    system_text = str(doc.get("system") or "")
    user_template = str(doc.get("user_template") or "")
    paraphrases = [str(x) for x in (doc.get("paraphrases") or [])]
    return system_text, user_template, paraphrases


def fallback_reasons(prob: float | None) -> list[str]:
    probability = prob if isinstance(prob, (int, float)) else 0.5
    if probability >= 0.60:
        return [
            "GPT‑5 has seen many supporting examples in its training data.",
            "Typical definitions and historical references line up with the claim.",
            "Counterexamples are rare compared to supporting evidence in its corpus.",
        ]
    if probability <= 0.40:
        return [
            "GPT‑5’s training data contains many instances that contradict the claim.",
            "Common usage and reference materials point the other way.",
            "Supporting anecdotes are outweighed by counterexamples it has seen.",
        ]
    return [
        "GPT‑5 finds mixed signals in its training data.",
        "It depends on definitions or missing context.",
        "Supporting and opposing examples appear in roughly equal measure.",
    ]


def classify_probability(prob: float | None) -> tuple[str, str, str, str]:
    probability = prob if isinstance(prob, (int, float)) else 0.5
    if probability >= 0.60:
        return (
            "Likely true",
            "LIKELY TRUE",
            "Why it’s likely true",
            "GPT‑5 leans toward this claim being true based on its training data.",
        )
    if probability <= 0.40:
        return (
            "Likely false",
            "LIKELY FALSE",
            "Why it’s likely false",
            "GPT‑5 leans toward this claim being false based on its training data.",
        )
    return (
        "Uncertain",
        "UNCERTAIN",
        "Why it’s uncertain",
        "GPT‑5 did not express a strong prior either way; responses were mixed.",
    )
