from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from heretix.config import RunConfig
from heretix.provider.factory import get_rpl_adapter
from heretix.pipeline import PipelineOptions, perform_run
from heretix.verdicts import classify_probability

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
    PriorBlock,
    WebEvidence,
    CombinedResult,
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

    cfg = RunConfig(
        claim=claim,
        model=payload.model or settings.rpl_model,
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

    prior_block_model = PriorBlock(**prior_block_payload)
    web_block_model = WebEvidence(**web_block_payload) if web_block_payload else None
    combined_block_model = CombinedResult(**combined_block_payload) if combined_block_payload else None
    weights_model = WeightInfo(**weights_payload) if weights_payload else None
    provenance_payload: dict[str, object] = {
        "rpl": {
            "prompt_version": result.get("prompt_version", cfg.prompt_version),
            "model": result.get("model", cfg.model),
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
        simple_expl=artifacts.simple_expl or None,
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
    if use_mock or not (system_text and user_template and paraphrase_text):
        reasons = fallback_reasons(prob)
    else:
        try:
            adapter = get_rpl_adapter(provider_mode="LIVE", model=cfg.model)
        except Exception as exc:  # pragma: no cover - defensive: registry misconfig
            logging.warning("Explanation adapter unavailable: %s", exc)
            adapter = None

        if adapter is not None:
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
                logging.warning("Explanation adapter call failed: %s", exc)

    if not reasons:
        reasons = fallback_reasons(prob)

    return verdict_label, verdict_text, headline, interpretation, reasons


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
                if not isinstance(item, str):
                    continue
                line = item.strip()
                if not line:
                    continue
                if line[-1] not in ".!?":
                    line += "."
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


def extract_reasons(payload: dict) -> list[str]:
    raw = (payload or {}).get("raw") or {}
    reasons: list[str] = []

    def add_items(items):
        for item in items:
            if not isinstance(item, str):
                continue
            text = item.strip().rstrip(".;")
            if not text:
                continue
            if not text.endswith("."):
                text += "."
            reasons.append(text)
            if len(reasons) >= 3:
                break

    primary = raw.get("reasoning_bullets") or []
    add_items(primary)
    if len(reasons) < 3:
        secondary = raw.get("contrary_considerations") or []
        add_items(secondary)

    if not reasons:
        alt: list[str] = []
        add_items(raw.get("assumptions") or [])
        if len(reasons) < 3:
            add_items(raw.get("ambiguity_flags") or [])

    if not reasons:
        return []
    return reasons[:3]


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
