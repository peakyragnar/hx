from __future__ import annotations

import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from heretix.config import RunConfig
from heretix.profiles import RPLProfile, derive_sampling_plan
from heretix.provider.utils import infer_provider_from_model
from heretix.rpl import run_single_version
from heretix.types import ModelBiasResult, RunResult


def _normalize_models(values: Sequence[str]) -> List[str]:
    """Deduplicate and normalize model names."""
    normalized: List[str] = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text in normalized:
            continue
        normalized.append(text)
    return normalized


def _resolve_prompt_file(cfg: RunConfig, prompt_root: Optional[Path] = None) -> Path:
    """Return the prompt file path for a run configuration."""
    if cfg.prompts_file:
        return Path(cfg.prompts_file)
    base = prompt_root if prompt_root else Path(__file__).resolve().parent / "prompts"
    path = base / f"{cfg.prompt_version}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path


def _label_from_probability(prob: Optional[float]) -> str:
    """Map an RPL probability into a coarse sentiment label."""
    if prob is None:
        return "uncertain"
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return "uncertain"
    if p >= 0.55:
        return "leans_true"
    if p <= 0.45:
        return "leans_false"
    return "uncertain"


def _short_explanation(
    model: str,
    prob: Optional[float],
    ci95: Tuple[Optional[float], Optional[float]],
    stability: Optional[float],
    profile_name: Optional[str],
) -> str:
    """Compose a short, deterministic explanation without extra model calls."""
    pieces: List[str] = []
    if prob is None:
        return f"No probability returned for {model}."
    try:
        p_pct = int(round(max(0.0, min(1.0, float(prob))) * 100))
    except Exception:
        p_pct = None
    if p_pct is not None:
        pieces.append(f"{model} leans {p_pct}% true")
    ci_lo, ci_hi = (ci95 or (None, None))[:2]
    try:
        if ci_lo is not None and ci_hi is not None:
            pieces.append(f"CI95 {float(ci_lo):.2f}–{float(ci_hi):.2f}")
    except Exception:
        pass
    if stability is not None:
        try:
            pieces.append(f"stability {float(stability):.2f}")
        except Exception:
            pass
    if profile_name:
        pieces.append(f"profile {profile_name}")
    return "; ".join(pieces) if pieces else f"{model} returned no summary."


def _generate_explanation(
    *,
    model: str,
    claim: str,
    prob: Optional[float],
    ci95: Tuple[Optional[float], Optional[float]],
    stability: Optional[float],
    profile_name: Optional[str],
) -> str:
    """Placeholder explainer step (deterministic, no extra provider calls)."""
    # We keep the explainer separate so a future change can swap in an
    # LLM-based explanation without touching the measurement path.
    return _short_explanation(model, prob, ci95, stability, profile_name)


def run_profiled_models(
    *,
    claim: str,
    models: Sequence[str],
    profile: Optional[RPLProfile] = None,
    base_config: Optional[RunConfig] = None,
    prompt_root: Optional[Path] = None,
    mock: bool = False,
) -> RunResult:
    """Run one or more models using a profile-aware sampling plan."""

    models_clean = _normalize_models(models)
    if not models_clean:
        raise ValueError("No models provided for profile-aware run")

    cfg_template = replace(base_config) if base_config is not None else RunConfig()
    cfg_template.claim = claim

    if profile:
        plan_raw = derive_sampling_plan(models_clean, profile)
        profile_name = profile.name
        explanation_mode = profile.explanation_mode
        B_value = profile.B
        max_tokens = profile.max_output_tokens
    else:
        # Fall back to an even plan based on the template config.
        profile_name = "custom"
        explanation_mode = "inline"
        B_value = cfg_template.B
        max_tokens = cfg_template.max_output_tokens
        fallback_T = cfg_template.T if cfg_template.T is not None else -1
        plan_raw = {m: (cfg_template.K, cfg_template.R, fallback_T) for m in models_clean}

    plan_models = list(plan_raw.keys())
    results: List[ModelBiasResult] = []
    raw_runs: Dict[str, Any] = {}
    timings: Dict[str, float] = {}

    for model in plan_models:
        k_plan, r_plan, t_plan = plan_raw.get(model, (cfg_template.K, cfg_template.R, cfg_template.T or -1))

        local_cfg = RunConfig(**{**cfg_template.__dict__})
        local_cfg.model = model
        local_cfg.logical_model = model
        if not local_cfg.provider_locked:
            local_cfg.provider = infer_provider_from_model(model) or local_cfg.provider or "openai"
        local_cfg.K = int(k_plan)
        local_cfg.R = int(r_plan)
        local_cfg.T = None if t_plan is None or int(t_plan) < 1 else int(t_plan)
        if B_value is not None:
            local_cfg.B = int(B_value)
        local_cfg.max_output_tokens = int(max_tokens)

        prompt_file = _resolve_prompt_file(local_cfg, prompt_root)

        start = time.perf_counter()
        run_payload = run_single_version(local_cfg, prompt_file=str(prompt_file), mock=mock)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        timings[f"measurement:{model}"] = elapsed_ms

        aggregates = run_payload.get("aggregates") or {}
        prob = aggregates.get("prob_true_rpl")
        ci95 = aggregates.get("ci95") or (None, None)
        stability = aggregates.get("stability_score")
        label = _label_from_probability(prob)
        explanation = ""
        if explanation_mode != "none":
            explain_start = time.perf_counter()
            explanation = _generate_explanation(
                model=model,
                claim=claim,
                prob=prob,
                ci95=ci95,
                stability=stability,
                profile_name=profile_name,
            )
            timings[f"explanation:{model}"] = (time.perf_counter() - explain_start) * 1000.0

        extras = {
            "ci95": ci95,
            "stability_score": stability,
            "counts_by_template": (run_payload.get("aggregation") or {}).get("counts_by_template"),
            "warning_counts": run_payload.get("warning_counts"),
        }
        extras = {k: v for k, v in extras.items() if v is not None}
        results.append(
            ModelBiasResult(
                model=model,
                p_rpl=float(prob) if prob is not None else float("nan"),
                label=label,
                explanation=explanation,
                extras=extras,
            )
        )
        raw_runs[model] = run_payload

    overall_run_id = f"bias-run-{uuid.uuid4().hex[:12]}"
    timings["total_ms"] = sum(timings.values())

    plan_serializable = {m: {"K": k, "R": r, "T": (None if t is None or t == -1 else t)} for m, (k, r, t) in plan_raw.items()}
    raw_output = {
        "plan": {
            "profile": profile_name,
            "explanation_mode": explanation_mode,
            "total_sample_budget": profile.total_sample_budget if profile else None,
            "models": plan_serializable,
        },
        "runs": raw_runs,
    }

    return RunResult(
        run_id=overall_run_id,
        claim=claim,
        profile=profile_name,
        models=results,
        raw_rpl_output=raw_output,
        timings=timings,
    )
