from __future__ import annotations

import time
import uuid
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import concurrent.futures as _fut

from heretix.config import RunConfig
from heretix.profiles import RPLProfile, derive_sampling_plan
from heretix.provider.utils import infer_provider_from_model
from heretix.rpl import run_single_version
from heretix.types import ModelBiasResult, RunResult
from heretix.simple_expl import compose_baseline_simple_expl
from heretix.explanations_llm import generate_simple_expl_llm


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

    overall_start = time.perf_counter()
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
    results_by_model: Dict[str, ModelBiasResult] = {}
    raw_runs: Dict[str, Any] = {}
    expl_blocks: Dict[str, Any] = {}
    timings: Dict[str, float] = {}

    env_workers = os.getenv("HERETIX_BIAS_MODEL_CONCURRENCY")
    try:
        max_workers = int(env_workers) if env_workers is not None else len(plan_models)
    except Exception:
        max_workers = len(plan_models)
    max_workers = max(1, min(max_workers, len(plan_models)))

    def _run_single_model(model: str) -> Tuple[str, ModelBiasResult, Dict[str, Any], Dict[str, float]]:
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
        if profile:
            # Allow slightly larger prompt bodies on profile runs to avoid brittle failures.
            if local_cfg.max_prompt_chars is None or int(local_cfg.max_prompt_chars) < 1400:
                local_cfg.max_prompt_chars = 1400

        prompt_file = _resolve_prompt_file(local_cfg, prompt_root)

        start = time.perf_counter()
        run_payload = run_single_version(local_cfg, prompt_file=str(prompt_file), mock=mock)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        aggregates = run_payload.get("aggregates") or {}
        prob = aggregates.get("prob_true_rpl")
        ci95 = aggregates.get("ci95") or (None, None)
        stability = aggregates.get("stability_score")
        label = _label_from_probability(prob)
        explanation = ""
        explanation_ms: float = 0.0

        extras = {
            "ci95": ci95,
            "stability_score": stability,
            "counts_by_template": (run_payload.get("aggregation") or {}).get("counts_by_template"),
            "warning_counts": run_payload.get("warning_counts"),
        }
        extras = {k: v for k, v in extras.items() if v is not None}
        model_result = ModelBiasResult(
            model=model,
            p_rpl=float(prob) if prob is not None else float("nan"),
            label=label,
            explanation=explanation,
            extras=extras,
        )
        timing_block = {
            f"measurement:{model}": elapsed_ms,
        }
        if explanation_mode != "none":
            timing_block[f"explanation:{model}"] = explanation_ms
        return model, model_result, run_payload, timing_block

    if max_workers > 1:
        with _fut.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_run_single_model, m): m for m in plan_models}
            for fut in _fut.as_completed(futures):
                model, model_result, run_payload, timing_block = fut.result()
                raw_runs[model] = run_payload
                results_by_model[model] = model_result
                timings.update(timing_block)
    else:
        for model in plan_models:
            model, model_result, run_payload, timing_block = _run_single_model(model)
            raw_runs[model] = run_payload
            results_by_model[model] = model_result
            timings.update(timing_block)

    overall_run_id = f"bias-run-{uuid.uuid4().hex[:12]}"
    timings["total_ms"] = (time.perf_counter() - overall_start) * 1000.0

    results: List[ModelBiasResult] = [results_by_model[m] for m in plan_models if m in results_by_model]

    # Build narration tasks from measured runs
    expl_tasks: Dict[str, Any] = {}
    if explanation_mode != "none":
        for model_name in plan_models:
            run_payload = raw_runs.get(model_name, {})
            aggregates = run_payload.get("aggregates") or {}
            expl_tasks[model_name] = {
                "claim": claim,
                "prob": aggregates.get("prob_true_rpl"),
                "ci95": aggregates.get("ci95") or (None, None),
                "stability": aggregates.get("stability_score"),
                "model": model_name,
                "provider": run_payload.get("provider"),
                "label": results_by_model.get(model_name).label if model_name in results_by_model else "uncertain",
            }

    # LLM narration pass (parallel per model). Fallback to deterministic baseline on failure.
    if expl_tasks:
        def _narrate(task_model: str, info: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            try:
                narr = generate_simple_expl_llm(
                    claim=info["claim"],
                    mode="baseline",
                    prior_block={"p": info["prob"], "ci95": info["ci95"], "stability": info["stability"]},
                    combined_block={"p": info["prob"], "ci95": info["ci95"], "stability": info["stability"]},
                    web_block=None,
                    warning_counts=None,
                    sampling={"T": (plan_raw.get(task_model) or (None, None, None))[2]},
                    weights=None,
                    model=task_model,
                    provider=info.get("provider"),
                    max_output_tokens=400,
                )
                block = narr.get("simple_expl")
                if isinstance(block, dict):
                    return task_model, _ensure_simple_expl_complete(
                        block=block,
                        label=str(info.get("label") or "uncertain"),
                        prob=info.get("prob"),
                        ci95=info.get("ci95") or (None, None),
                        stability=info.get("stability"),
                    )
            except Exception:
                pass
            # Fallback deterministic block
            try:
                block = compose_baseline_simple_expl(
                    claim=info["claim"],
                    prior_p=float(info["prob"]) if info["prob"] is not None else 0.0,
                    prior_ci=(info["ci95"][0], info["ci95"][1]) if isinstance(info["ci95"], (list, tuple)) else (None, None),
                    stability_score=info["stability"],
                    template_count=(plan_raw.get(task_model) or (None, None, None))[2] or 0,
                    imbalance_ratio=None,
                )
                return task_model, _ensure_simple_expl_complete(
                    block=block,
                    label=str(info.get("label") or "uncertain"),
                    prob=info.get("prob"),
                    ci95=info.get("ci95") or (None, None),
                    stability=info.get("stability"),
                )
            except Exception:
                return task_model, None

        narrator_workers = min(len(expl_tasks), max_workers or len(expl_tasks))
        with _fut.ThreadPoolExecutor(max_workers=narrator_workers) as ex:
            futures = {ex.submit(_narrate, m, info): m for m, info in expl_tasks.items()}
            for fut in _fut.as_completed(futures):
                model_name, block = fut.result()
                if block:
                    expl_blocks[model_name] = block

    # Ensure every model has a simple_expl block (fallback if narration failed).
    for model_name in plan_models:
        if model_name in expl_blocks:
            continue
        info = expl_tasks.get(model_name, {})
        try:
            run_payload = raw_runs.get(model_name, {})
            aggregates = run_payload.get("aggregates") or {}
            prob_val = aggregates.get("prob_true_rpl")
            ci_val = aggregates.get("ci95") or (None, None)
            stab_val = aggregates.get("stability_score")
            block = compose_baseline_simple_expl(
                claim=info.get("claim", claim),
                prior_p=float(prob_val) if prob_val is not None else 0.0,
                prior_ci=(ci_val[0], ci_val[1]) if isinstance(ci_val, (list, tuple)) else (None, None),
                stability_score=stab_val,
                template_count=(plan_raw.get(model_name) or (None, None, None))[2] or 0,
                imbalance_ratio=(run_payload.get("aggregation") or {}).get("imbalance_ratio"),
            )
            expl_blocks[model_name] = _ensure_simple_expl_complete(
                block=block,
                label=str(info.get("label") or results_by_model.get(model_name, ModelBiasResult(model_name, float("nan"), "uncertain", "", {})).label),
                prob=prob_val,
                ci95=ci_val,
                stability=stab_val,
            )
        except Exception:
            continue

    plan_serializable = {m: {"K": k, "R": r, "T": (None if t is None or t == -1 else t)} for m, (k, r, t) in plan_raw.items()}
    raw_output = {
        "plan": {
            "profile": profile_name,
            "explanation_mode": explanation_mode,
            "total_sample_budget": profile.total_sample_budget if profile else None,
            "models": plan_serializable,
        },
        "runs": raw_runs,
        "simple_expl": expl_blocks,
    }

    if not expl_blocks:
        # Final guard: ensure simple_expl is populated even if narration failed silently.
        for model_name, run_payload in raw_runs.items():
            aggregates = run_payload.get("aggregates") or {}
            prob_val = aggregates.get("prob_true_rpl")
            ci_val = aggregates.get("ci95") or (None, None)
            stab_val = aggregates.get("stability_score")
            try:
                block = compose_baseline_simple_expl(
                    claim=claim,
                    prior_p=float(prob_val) if prob_val is not None else 0.0,
                    prior_ci=(ci_val[0], ci_val[1]) if isinstance(ci_val, (list, tuple)) else (None, None),
                    stability_score=stab_val,
                    template_count=(plan_raw.get(model_name) or (None, None, None))[2] or 0,
                    imbalance_ratio=(run_payload.get("aggregation") or {}).get("imbalance_ratio"),
                )
                expl_blocks[model_name] = _ensure_simple_expl_complete(
                    block=block,
                    label=results_by_model.get(model_name, ModelBiasResult(model_name, float("nan"), "uncertain", "", {})).label,
                    prob=prob_val,
                    ci95=ci_val,
                    stability=stab_val,
                )
            except Exception:
                continue
        raw_output["simple_expl"] = expl_blocks

    return RunResult(
        run_id=overall_run_id,
        claim=claim,
        profile=profile_name,
        models=results,
        raw_rpl_output=raw_output,
        timings=timings,
    )
def _ensure_simple_expl_complete(
    *,
    block: Optional[Dict[str, Any]],
    label: str,
    prob: Optional[float],
    ci95: Tuple[Optional[float], Optional[float]],
    stability: Optional[float],
) -> Dict[str, Any]:
    """Guarantee a simple_expl has title/summary/lines populated."""
    block_normalized: Dict[str, Any] = block if isinstance(block, dict) else {}

    def _safe_pct(value: Optional[float]) -> str:
        try:
            return f"{float(value) * 100:.1f}%"
        except Exception:
            return ""

    title_fallback = f"Why this looks {label.replace('_', ' ').strip() or 'uncertain'}."
    body_paras = block_normalized.get("body_paragraphs") if isinstance(block_normalized.get("body_paragraphs"), list) else []
    first_para = ""
    if body_paras:
        for para in body_paras:
            if isinstance(para, str) and para.strip():
                first_para = para.strip()
                break
    summary_fallback = first_para or "Taken together, these signals support this verdict."
    lines: List[str] = []
    if ci95 and ci95[0] is not None and ci95[1] is not None:
        lines.append(f"CI95 {ci95[0]:.2f}–{ci95[1]:.2f}")
    if stability is not None:
        try:
            lines.append(f"Stability {float(stability):.2f}")
        except Exception:
            pass
    if prob is not None:
        pct = _safe_pct(prob)
        if pct:
            lines.insert(0, f"Model-only probability {pct}")

    title = block_normalized.get("title") or title_fallback
    summary = (block_normalized.get("summary") or "").strip() or summary_fallback
    existing_lines = block_normalized.get("lines")
    if isinstance(existing_lines, (list, tuple)):
        lines = [str(x) for x in existing_lines if str(x).strip()] or lines

    return {
        "title": title,
        "summary": summary,
        "lines": lines[:5],
        "body_paragraphs": block_normalized.get("body_paragraphs"),
        "reasoning": block_normalized.get("reasoning"),
    }
