"""
Adaptive controller for RPL (Auto-RPL):

Implements templates-first escalation with deterministic, explainable decisions.
Stages:
  1) T=8,  K=8,  R=2
  2) T=16, K=16, R=2
  3) T=16, K=16, R=3

Hard gates (pass required):
  - CI width ≤ 0.20
  - Stability ≥ 0.70   (stability = 1/(1+IQR_logit))
  - Imbalance ≤ 1.50

Warn gate (non-blocking):
  - Imbalance > 1.25 → log warning in decision log

Deterministic rotation + balanced counts ensure near-perfect paraphrase balance.
Samples are reused across stages; escalations add only the necessary deltas.
"""
from __future__ import annotations

from typing import Dict, Any, List, Tuple
import time, hashlib, os
import numpy as np

from heretix_rpl.rpl_prompts import PARAPHRASES, PROMPT_VERSION
from heretix_rpl.rpl_eval import call_rpl_once_gpt5, _logit, _sigmoid
from heretix_rpl.aggregation import aggregate_clustered
from heretix_rpl.seed import make_bootstrap_seed
from heretix_rpl.config import load_config
from heretix_rpl.metrics import compute_stability_calibrated, stability_band_from_iqr
from heretix_rpl.sampler import rotation_offset, balanced_indices_with_rotation, planned_counts
from heretix_rpl.constants import (
    GATE_CI_WIDTH_MAX_DEFAULT,
    GATE_STABILITY_MIN_DEFAULT,
    GATE_IMBALANCE_MAX_DEFAULT,
    GATE_IMBALANCE_WARN_DEFAULT,
)


def _stage_digest(claim: str, model: str, K: int, R: int) -> str:
    return hashlib.sha256(f"{claim}|{model}|K={K}|R={R}".encode()).hexdigest()[:8]


def _select_templates_for_stage(claim: str, model: str, T_bank: int, T_stage: int) -> List[int]:
    """Return list of T_stage unique template indices from the rotated bank (deterministic)."""
    off = rotation_offset(claim, model, PROMPT_VERSION, T_bank)
    order = list(range(T_bank))
    if T_bank > 1 and off % T_bank != 0:
        rot = off % T_bank
        order = order[rot:] + order[:rot]
    return order[:max(0, min(T_stage, T_bank))]


def _aggregate(claim: str, model: str, by_tpl: Dict[str, List[float]], tpl_hashes: List[str]) -> Tuple[float, Tuple[float, float], Dict[str, Any], Dict[str, Any]]:
    """Run robust clustered aggregation with deterministic seed and return stats + diag."""
    cfg = load_config()
    # Seed derivation: use claim, model, prompt_version, K/R implied by by_tpl sizes are for reproducibility
    env_seed = os.getenv("HERETIX_RPL_SEED")
    if env_seed is not None:
        seed_val = int(env_seed)
    else:
        # Harden determinism: sorted unique template hashes for seed derivation
        uniq_tpl_hashes = sorted(set(tpl_hashes))
        seed_val = make_bootstrap_seed(
            claim=claim,
            model=model,
            prompt_version=PROMPT_VERSION,
            k=0,  # k and r are not needed for seed uniqueness since template hashes carry structure
            r=0,
            template_hashes=uniq_tpl_hashes,
            center="trimmed",
            trim=cfg.trim,
            B=cfg.b_clustered,
        )
    rng = np.random.default_rng(seed_val)
    ell_hat, (lo_l, hi_l), diag = aggregate_clustered(by_tpl, B=cfg.b_clustered, rng=rng, center="trimmed", trim=cfg.trim, fixed_m=None)
    p_hat = _sigmoid(ell_hat)
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)
    # Stability on template means (logit space)
    stability_basis = [float(np.mean(v)) for v in by_tpl.values()] if by_tpl else []
    stability, iqr_l = compute_stability_calibrated(stability_basis)
    band = stability_band_from_iqr(iqr_l)
    aggs = {
        "prob_true_rpl": p_hat,
        "ci95": [lo_p, hi_p],
        "ci_width": hi_p - lo_p,
        "paraphrase_iqr_logit": iqr_l,
        "stability_score": stability,
        "stability_band": band,
        "is_stable": (hi_p - lo_p) <= cfg.stability_width,
    }
    agg_info = {
        "method": diag.get("method", "equal_by_template_cluster_bootstrap_trimmed"),
        "B": cfg.b_clustered,
        "center": "trimmed",
        "trim": cfg.trim,
        "min_samples": cfg.min_samples,
        "stability_width": cfg.stability_width,
        "bootstrap_seed": seed_val,
        "n_templates": diag.get("n_templates"),
        "counts_by_template": diag.get("counts_by_template"),
        "imbalance_ratio": diag.get("imbalance_ratio"),
        "template_iqr_logit": diag.get("template_iqr_logit"),
    }
    return ell_hat, (lo_l, hi_l), aggs, agg_info


def auto_rpl(
    claim: str,
    model: str = "gpt-5",
    # start & ceilings
    start_K: int = 8,
    start_R: int = 2,
    max_K: int = 16,
    max_R: int = 3,
    # gates
    ci_width_max: float = GATE_CI_WIDTH_MAX_DEFAULT,
    stability_min: float = GATE_STABILITY_MIN_DEFAULT,
    imbalance_max: float = GATE_IMBALANCE_MAX_DEFAULT,
    imbalance_warn: float = GATE_IMBALANCE_WARN_DEFAULT,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Adaptive controller for RPL. Deterministically escalates K (templates), then R (replicates)."""
    # Validate gate inputs
    if not (0.0 < float(ci_width_max) <= 1.0):
        raise ValueError("ci_width_max must be in (0, 1].")
    if not (0.0 < float(stability_min) <= 1.0):
        raise ValueError("stability_min must be in (0, 1].")
    if not (float(imbalance_max) >= 1.0):
        raise ValueError("imbalance_max must be ≥ 1.0.")
    if not (float(imbalance_warn) >= 1.0):
        raise ValueError("imbalance_warn must be ≥ 1.0.")

    T_bank = len(PARAPHRASES)
    # Stage plan: (K,R) pairs, with T_stage matching K (1 per template) for templates-first policy
    plan: List[Tuple[int, int, int]] = []  # (T_stage, K, R)
    plan.append((8, min(8, T_bank), start_R))
    if T_bank >= 16:
        plan.append((16, min(16, T_bank), start_R))
    else:
        # If bank smaller than 16, keep K at bank size and escalate R only at second stage
        plan.append((T_bank, T_bank, start_R))
    plan.append((min(16, T_bank), min(16, T_bank), max_R))

    stages: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []

    # Cache of collected samples for reuse: by template hash
    runs: List[Dict[str, Any]] = []
    by_tpl: Dict[str, List[float]] = {}
    tpl_hashes: List[str] = []

    for i, (T_stage, K, R) in enumerate(plan, start=1):
        if verbose:
            print(f"[auto] Stage {i}/{len(plan)}: T={T_stage}, K={K}, R={R}", flush=True)
        # Determine unique templates for this stage (deterministic rotation)
        tpl_indices = _select_templates_for_stage(claim, model, T_bank=T_bank, T_stage=T_stage)
        # Balanced order across T_stage for K slots
        off = rotation_offset(claim, model, PROMPT_VERSION, T_stage)
        order = balanced_indices_with_rotation(T_stage, K, off)
        # Map order indices (0..T_stage-1) back to bank indices
        bank_order = [tpl_indices[idx] for idx in order]

        # Planned counts & imbalance (diagnostic)
        planned_c, planned_ratio = planned_counts(order, T_stage)

        # Collect only missing samples for this stage
        # For each planned slot, we want R replicates per template (equal across templates in this plan)
        # Compute target replicate count per template index within this stage
        target_reps = R
        # Build a mapping from bank template index to how many replicates we already have
        have_counts: Dict[str, int] = {}
        for h, vals in by_tpl.items():
            have_counts[h] = len(vals)

        # For each unique template in this stage, ensure we have target_reps replicates
        for bidx in tpl_indices:
            phr = PARAPHRASES[bidx]
            # Generate a provisional prompt hash using a dry-run call of hashing inside call_rpl_once_gpt5 is not possible
            # Instead, we actually make calls and collect; we will count by prompt_sha256 returned.
            # Determine how many more replicates needed by inspecting current by_tpl after calls.
            # We’ll simply iterate replicate slots and guard with counts on returned hash.
            rep = 0
            failures = 0
            max_failures = 5 * target_reps  # guard against provider hiccups
            while rep < target_reps:
                try:
                    out = call_rpl_once_gpt5(claim, phr, model)
                    p = out["raw"]["prob_true"]
                    l = _logit(p)
                    h = out["meta"]["prompt_sha256"]
                    curr = len(by_tpl.get(h, []))
                    if curr < target_reps:
                        runs.append({**out, "paraphrase_idx": bidx, "replicate_idx": curr})
                        by_tpl.setdefault(h, []).append(l)
                        tpl_hashes.append(h)
                        rep = curr + 1
                    else:
                        # Already have enough for this template hash (due to retries); skip counting
                        rep += 1
                except Exception as e:
                    failures += 1
                    if verbose:
                        print(f"[auto] WARN: call failed for template {bidx} (attempt {failures}): {e}", flush=True)
                    if failures >= max_failures:
                        raise

        # After ensuring counts, aggregate for this stage
        ell_hat, (lo_l, hi_l), aggs, agg_info = _aggregate(claim, model, by_tpl, tpl_hashes)

        # Diagnostics from agg_info
        ci_width = float(aggs["ci_width"])
        stability = float(aggs["stability_score"])
        imbalance = float(agg_info.get("imbalance_ratio", 1.0) or 1.0)
        warn_flag = imbalance > imbalance_warn

        stage_id = f"S{i}-{_stage_digest(claim, model, K, R)}"

        # Build stage snapshot
        snapshot = {
            "stage_id": stage_id,
            "K": K,
            "R": R,
            "T": T_stage,
            "p_RPL": aggs["prob_true_rpl"],
            "ci95": aggs["ci95"],
            "ci_width": ci_width,
            "stability_score": stability,
            "stability_band": aggs["stability_band"],
            "imbalance_ratio": imbalance,
            "is_stable": aggs["is_stable"],
            "planned": {
                "offset": off,
                "order": bank_order,
                "counts_by_template_planned": planned_c,
                "imbalance_planned": planned_ratio,
            },
            "raw_run": {
                "run_id": f"rpl-g5-{stage_id}",
                "claim": claim,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "sampling": {"K": K, "R": R, "N": sum(len(v) for v in by_tpl.values())},
                "decoding": {
                    "max_output_tokens": 1024,
                    "reasoning_effort": "minimal",
                    "verbosity": "low",
                },
                "aggregation": agg_info,
                "timestamp": int(time.time()),
                "aggregates": aggs,
                "paraphrase_results": runs,
                "paraphrase_balance": agg_info,
                "raw_logits": [x for vals in by_tpl.values() for x in vals],
            },
        }
        stages.append(snapshot)

        # Gate evaluation
        passes = (ci_width <= ci_width_max) and (stability >= stability_min) and (imbalance <= imbalance_max)
        gate_report = {
            "ci_width": {"value": ci_width, "threshold": ci_width_max, "pass": ci_width <= ci_width_max},
            "stability": {"value": stability, "threshold": stability_min, "pass": stability >= stability_min},
            "imbalance": {"value": imbalance, "threshold": imbalance_max, "pass": imbalance <= imbalance_max},
        }
        if verbose:
            print(f"[auto] Stage {i} metrics: p={aggs['prob_true_rpl']:.3f} width={ci_width:.3f} stability={stability:.3f} imbalance={imbalance:.2f}", flush=True)
        if passes:
            decisions.append({
                "stage_id": stage_id,
                "action": "stop_pass",
                "reason": "Passed quality gates.",
                "gates": gate_report,
                "warning": ("imbalance_warn" if warn_flag else None),
            })
            break
        else:
            if i < len(plan):
                next_T, nextK, nextR = plan[i]
                if verbose:
                    print(f"[auto] Escalating to Stage {i+1}: T={next_T}, K={nextK}, R={nextR}", flush=True)
                decisions.append({
                    "stage_id": stage_id,
                    "action": f"escalate_to_T{next_T}_K{nextK}_R{nextR}",
                    "reason": "; ".join(k for k, v in gate_report.items() if not v["pass"]) or "policy escalation",
                    "gates": gate_report,
                    "warning": ("imbalance_warn" if warn_flag else None),
                })
            else:
                decisions.append({
                    "stage_id": stage_id,
                    "action": "stop_limits",
                    "reason": "Reached maximum stage plan.",
                    "gates": gate_report,
                    "warning": ("imbalance_warn" if warn_flag else None),
                })

    final = stages[-1]
    return {
        "controller": {
            "policy": "templates-first-then-replicates",
            "start": {"K": start_K, "R": start_R},
            "ceilings": {"max_K": max_K, "max_R": max_R},
            "gates": {
                "ci_width_max": ci_width_max,
                "stability_min": stability_min,
                "imbalance_max": imbalance_max,
                "imbalance_warn": imbalance_warn,
            },
            "timestamp": int(time.time()),
        },
        "claim": claim,
        "model": model,
        "final": {
            "stage_id": final["stage_id"],
            "K": final["K"],
            "R": final["R"],
            "p_RPL": final["p_RPL"],
            "ci95": final["ci95"],
            "ci_width": final["ci_width"],
            "stability_score": final["stability_score"],
            "stability_band": final["stability_band"],
            "imbalance_ratio": final["imbalance_ratio"],
            "is_stable": final["is_stable"],
        },
        "stages": stages,
        "decision_log": decisions,
    }
