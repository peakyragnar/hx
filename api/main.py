from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from heretix.config import RunConfig
from heretix.rpl import run_single_version

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
    RunRequest,
    RunResponse,
    SamplingInfo,
)
from heretix.db.models import Check, User
from .usage import ANON_PLAN, get_usage_state, increment_usage
from .billing import create_checkout_session, handle_checkout_completed, handle_subscription_deleted, handle_subscription_updated

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


@app.get("/healthz", tags=["system"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/checks/run", response_model=RunResponse)
def run_check(
    payload: RunRequest,
    session: Session = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> RunResponse:
    claim = payload.claim.strip()
    if not claim:
        raise HTTPException(status_code=422, detail="claim must not be empty")

    usage_state = get_usage_state(session, user)
    if not usage_state.enough_credit:
        reason = "require_subscription" if user else "require_signin"
        raise HTTPException(status_code=402, detail={"reason": reason, "plan": usage_state.plan.name})

    cfg = RunConfig(
        claim=claim,
        model=payload.model or settings.rpl_model,
        prompt_version=payload.prompt_version or settings.rpl_prompt_version,
        K=payload.K or settings.rpl_k,
        R=payload.R or settings.rpl_r,
        B=payload.B or settings.rpl_b,
        max_output_tokens=payload.max_output_tokens or settings.rpl_max_output_tokens,
        no_cache=bool(payload.no_cache) if payload.no_cache is not None else False,
    )
    cfg.seed = payload.seed if payload.seed is not None else cfg.seed

    prompt_file = settings.prompt_file()

    use_mock = payload.mock if payload.mock is not None else settings.allow_mock

    try:
        result = run_single_version(cfg, prompt_file=str(prompt_file), mock=use_mock)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - let FastAPI handle responses
        raise HTTPException(status_code=500, detail=str(exc)) from exc

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

    now = datetime.now(timezone.utc)

    counts_json = json.dumps(aggregation.get("counts_by_template", {}))
    config_json = json.dumps(
        {
            "claim": cfg.claim,
            "model": cfg.model,
            "prompt_version": cfg.prompt_version,
            "K": cfg.K,
            "R": cfg.R,
            "T": sampling.get("T"),
            "B": cfg.B,
            "seed": cfg.seed,
            "max_output_tokens": cfg.max_output_tokens,
            "no_cache": cfg.no_cache,
            "prompt_file": str(prompt_file),
        }
    )

    run_id = result.get("run_id")
    if not run_id:
        raise HTTPException(status_code=500, detail="run_id missing from RPL result")

    claim_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()

    checks_allowed = usage_state.checks_allowed
    used_after = usage_state.checks_used
    remaining_after = max(checks_allowed - used_after, 0) if checks_allowed else None
    aggregates["ci_width"] = ci_width

    check = None
    try:
        existing = session.scalar(select(Check).where(Check.run_id == run_id))
        if existing:
            check = existing
        else:
            check = Check(run_id=run_id, env=settings.app_env)
            session.add(check)

        check.env = settings.app_env
        check.user_id = getattr(user, "id", None)
        check.claim = claim
        check.claim_hash = claim_hash
        check.model = result.get("model", cfg.model)
        check.prompt_version = result.get("prompt_version", cfg.prompt_version)
        check.k = int(cfg.K)
        check.r = int(cfg.R)
        check.t = sampling.get("T")
        check.b = cfg.B
        check.seed = cfg.seed
        bootstrap_seed = aggregation.get("bootstrap_seed")
        check.bootstrap_seed = int(bootstrap_seed) if bootstrap_seed is not None else None
        check.max_output_tokens = cfg.max_output_tokens
        check.prob_true_rpl = float(aggregates.get("prob_true_rpl"))
        check.ci_lo = float(ci95[0]) if ci95[0] is not None else None
        check.ci_hi = float(ci95[1]) if ci95[1] is not None else None
        check.ci_width = ci_width
        check.template_iqr_logit = aggregation.get("template_iqr_logit")
        check.stability_score = stability_score
        check.imbalance_ratio = aggregation.get("imbalance_ratio")
        check.rpl_compliance_rate = rpl_compliance_rate
        check.cache_hit_rate = cache_hit_rate
        check.config_json = config_json
        check.sampler_json = json.dumps({"K": cfg.K, "R": cfg.R, "T": sampling.get("T")})
        check.counts_by_template_json = counts_json
        check.artifact_json_path = None
        check.prompt_char_len_max = aggregation.get("prompt_char_len_max")
        check.pqs = None
        check.gate_compliance_ok = gate_compliance_ok
        check.gate_stability_ok = gate_stability_ok
        check.gate_precision_ok = gate_precision_ok
        check.pqs_version = None
        check.was_cached = cache_hit_rate >= 0.999
        check.provider_model_id = result.get("model", cfg.model)
        check.created_at = now
        check.finished_at = now

        if usage_state.plan == ANON_PLAN:
            used_after = min(usage_state.checks_used + 1, checks_allowed)
        else:
            used_after = increment_usage(session, user, usage_state)
        remaining_after = max(checks_allowed - used_after, 0) if checks_allowed else None

        session.commit()
    except ProgrammingError as exc:
        session.rollback()
        logging.warning("Skipping DB persistence for run %s due to schema mismatch: %s", run_id, exc)
        used_after = usage_state.checks_used
        remaining_after = max(checks_allowed - used_after, 0) if checks_allowed else None

    return RunResponse(
        execution_id=result.get("execution_id"),
        run_id=run_id,
        claim=result.get("claim"),
        model=result.get("model", cfg.model),
        prompt_version=result.get("prompt_version", cfg.prompt_version),
        sampling=SamplingInfo(**sampling),
        aggregation=AggregationInfo(
            method=aggregation.get("method"),
            B=int(aggregation.get("B", cfg.B)),
            center=aggregation.get("center"),
            trim=aggregation.get("trim"),
            bootstrap_seed=bootstrap_seed,
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
    )


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
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    if not user:
        state = get_usage_state(session, None)
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
