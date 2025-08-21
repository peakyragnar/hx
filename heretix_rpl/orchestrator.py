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
from __future__ import annotations                           # Enable forward type references

from typing import Dict, Any, List, Tuple                    # Type annotations
import time, hashlib, os                                     # System utilities for timestamps, hashing, and env vars
import numpy as np                                           # Numerical computations

from heretix_rpl.rpl_prompts import PARAPHRASES, PROMPT_VERSION  # Paraphrase templates and version info
from heretix_rpl.rpl_eval import call_rpl_once_gpt5, _logit, _sigmoid  # Core evaluation and transform functions
from heretix_rpl.aggregation import aggregate_clustered     # Robust statistical aggregation
from heretix_rpl.seed import make_bootstrap_seed            # Deterministic seed generation
from heretix_rpl.config import load_config                  # Configuration loading
from heretix_rpl.metrics import compute_stability_calibrated, stability_band_from_iqr  # Stability calculations
from heretix_rpl.sampler import rotation_offset, balanced_indices_with_rotation, planned_counts  # Sampling utilities
from heretix_rpl.constants import (                         # Default gate thresholds
    GATE_CI_WIDTH_MAX_DEFAULT,                              # Default CI width threshold
    GATE_STABILITY_MIN_DEFAULT,                             # Default stability minimum
    GATE_IMBALANCE_MAX_DEFAULT,                             # Default imbalance maximum
    GATE_IMBALANCE_WARN_DEFAULT,                            # Default imbalance warning threshold
)


def _stage_digest(claim: str, model: str, K: int, R: int) -> str:
    """Generate short hash for stage identification."""        # Function purpose
    return hashlib.sha256(f"{claim}|{model}|K={K}|R={R}".encode()).hexdigest()[:8]  # Create 8-char hash from stage parameters


def _select_templates_for_stage(claim: str, model: str, T_bank: int, T_stage: int) -> List[int]:
    """Return list of T_stage unique template indices from the rotated bank (deterministic)."""  # Function purpose
    off = rotation_offset(claim, model, PROMPT_VERSION, T_bank)  # Get deterministic rotation offset
    order = list(range(T_bank))                              # Create initial template order
    if T_bank > 1 and off % T_bank != 0:                    # If rotation needed
        rot = off % T_bank                                   # Calculate rotation amount
        order = order[rot:] + order[:rot]                    # Apply rotation to template order
    return order[:max(0, min(T_stage, T_bank))]             # Return first T_stage templates from rotated order


def _aggregate(claim: str, model: str, by_tpl: Dict[str, List[float]], tpl_hashes: List[str]) -> Tuple[float, Tuple[float, float], Dict[str, Any], Dict[str, Any]]:
    """Run robust clustered aggregation with deterministic seed and return stats + diag."""  # Function purpose
    cfg = load_config()                                      # Load configuration settings
    # Seed derivation: use claim, model, prompt_version, K/R implied by by_tpl sizes are for reproducibility
    env_seed = os.getenv("HERETIX_RPL_SEED")                 # Check for environment seed override
    if env_seed is not None:                                 # If environment seed provided
        seed_val = int(env_seed)                             # Use environment seed
    else:                                                    # Otherwise generate deterministic seed
        # Harden determinism: sorted unique template hashes for seed derivation
        uniq_tpl_hashes = sorted(set(tpl_hashes))            # Get unique sorted template hashes
        seed_val = make_bootstrap_seed(                      # Generate deterministic seed
            claim=claim,                                     # Include claim in seed
            model=model,                                     # Include model in seed
            prompt_version=PROMPT_VERSION,                   # Include prompt version in seed
            k=0,  # k and r are not needed for seed uniqueness since template hashes carry structure
            r=0,                                             # Template hashes provide structure info
            template_hashes=uniq_tpl_hashes,                 # Include template hashes in seed
            center="trimmed",                                # Include aggregation method in seed
            trim=cfg.trim,                                   # Include trim parameter in seed
            B=cfg.b_clustered,                               # Include bootstrap iterations in seed
        )
    rng = np.random.default_rng(seed_val)                    # Create RNG with deterministic seed
    ell_hat, (lo_l, hi_l), diag = aggregate_clustered(by_tpl, B=cfg.b_clustered, rng=rng, center="trimmed", trim=cfg.trim, fixed_m=None)  # Run clustered aggregation
    p_hat = _sigmoid(ell_hat)                                # Convert logit estimate to probability
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)              # Convert CI bounds to probability space
    # Stability on template means (logit space)
    stability_basis = [float(np.mean(v)) for v in by_tpl.values()] if by_tpl else []  # Calculate per-template means
    stability, iqr_l = compute_stability_calibrated(stability_basis)  # Compute calibrated stability score
    band = stability_band_from_iqr(iqr_l)                    # Get stability band label
    aggs = {                                                 # Build aggregates dictionary
        "prob_true_rpl": p_hat,                              # RPL probability estimate
        "ci95": [lo_p, hi_p],                               # 95% confidence interval
        "ci_width": hi_p - lo_p,                            # CI width
        "paraphrase_iqr_logit": iqr_l,                      # Template IQR in logit space
        "stability_score": stability,                        # Stability score
        "stability_band": band,                              # Stability band label
        "is_stable": (hi_p - lo_p) <= cfg.stability_width,  # Stability flag based on CI width
    }
    agg_info = {                                             # Build aggregation info dictionary
        "method": diag.get("method", "equal_by_template_cluster_bootstrap_trimmed"),  # Aggregation method name
        "B": cfg.b_clustered,                                # Bootstrap iterations
        "center": "trimmed",                                 # Center method
        "trim": cfg.trim,                                    # Trim percentage
        "min_samples": cfg.min_samples,                      # Minimum samples required
        "stability_width": cfg.stability_width,              # Stability width threshold
        "bootstrap_seed": seed_val,                          # Bootstrap seed for reproducibility
        "n_templates": diag.get("n_templates"),              # Number of unique templates
        "counts_by_template": diag.get("counts_by_template"), # Sample counts per template
        "imbalance_ratio": diag.get("imbalance_ratio"),      # Template imbalance ratio
        "template_iqr_logit": diag.get("template_iqr_logit"), # Template IQR in logit space
    }
    return ell_hat, (lo_l, hi_l), aggs, agg_info            # Return estimate, CI bounds, aggregates, and info


def auto_rpl(
    claim: str,                                              # Claim text to evaluate
    model: str = "gpt-5",                                    # Model to use for evaluation
    # start & ceilings
    start_K: int = 8,                                        # Initial number of paraphrase slots
    start_R: int = 2,                                        # Initial replicates per paraphrase
    max_K: int = 16,                                         # Maximum paraphrase slots
    max_R: int = 3,                                          # Maximum replicates per paraphrase
    # gates
    ci_width_max: float = GATE_CI_WIDTH_MAX_DEFAULT,         # Maximum allowed CI width
    stability_min: float = GATE_STABILITY_MIN_DEFAULT,       # Minimum required stability score
    imbalance_max: float = GATE_IMBALANCE_MAX_DEFAULT,       # Maximum allowed template imbalance
    imbalance_warn: float = GATE_IMBALANCE_WARN_DEFAULT,     # Imbalance threshold for warnings
    verbose: bool = False,                                   # Enable verbose logging
) -> Dict[str, Any]:
    """Adaptive controller for RPL. Deterministically escalates K (templates), then R (replicates)."""  # Function purpose
    # Validate gate inputs
    if not (0.0 < float(ci_width_max) <= 1.0):              # Check CI width threshold validity
        raise ValueError("ci_width_max must be in (0, 1].")  # Raise error for invalid CI width
    if not (0.0 < float(stability_min) <= 1.0):             # Check stability threshold validity
        raise ValueError("stability_min must be in (0, 1].") # Raise error for invalid stability
    if not (float(imbalance_max) >= 1.0):                   # Check imbalance threshold validity
        raise ValueError("imbalance_max must be ≥ 1.0.")    # Raise error for invalid imbalance max
    if not (float(imbalance_warn) >= 1.0):                  # Check imbalance warning validity
        raise ValueError("imbalance_warn must be ≥ 1.0.")   # Raise error for invalid imbalance warn

    T_bank = len(PARAPHRASES)                                # Get total number of templates in bank
    # Stage plan: (K,R) pairs, with T_stage matching K (1 per template) for templates-first policy
    plan: List[Tuple[int, int, int]] = []                    # Initialize stage plan list: (T_stage, K, R)
    plan.append((8, min(8, T_bank), start_R))                # Stage 1: 8 templates, 8 slots, start_R replicates
    if T_bank >= 16:                                         # If we have enough templates for stage 2
        plan.append((16, min(16, T_bank), start_R))          # Stage 2: 16 templates, 16 slots, start_R replicates
    else:                                                    # If bank smaller than 16 templates
        # If bank smaller than 16, keep K at bank size and escalate R only at second stage
        plan.append((T_bank, T_bank, start_R))               # Stage 2: use all templates, same replicates
    plan.append((min(16, T_bank), min(16, T_bank), max_R))   # Stage 3: max templates, max replicates

    stages: List[Dict[str, Any]] = []                        # Initialize stages results list
    decisions: List[Dict[str, Any]] = []                     # Initialize decision log list

    # Cache of collected samples for reuse: by template hash
    runs: List[Dict[str, Any]] = []                          # Cache all API calls for reuse
    by_tpl: Dict[str, List[float]] = {}                      # Group logits by template hash
    tpl_hashes: List[str] = []                               # Track template hashes for seed generation

    for i, (T_stage, K, R) in enumerate(plan, start=1):      # Iterate through stage plan
        if verbose:                                          # If verbose logging enabled
            print(f"[auto] Stage {i}/{len(plan)}: T={T_stage}, K={K}, R={R}", flush=True)  # Print stage info
        # Determine unique templates for this stage (deterministic rotation)
        tpl_indices = _select_templates_for_stage(claim, model, T_bank=T_bank, T_stage=T_stage)  # Get template indices for stage
        # Balanced order across T_stage for K slots
        off = rotation_offset(claim, model, PROMPT_VERSION, T_stage)  # Get rotation offset for balance
        order = balanced_indices_with_rotation(T_stage, K, off)      # Get balanced slot order
        # Map order indices (0..T_stage-1) back to bank indices
        bank_order = [tpl_indices[idx] for idx in order]            # Map stage indices to bank indices

        # Planned counts & imbalance (diagnostic)
        planned_c, planned_ratio = planned_counts(order, T_stage)    # Calculate expected template counts

        # Collect only missing samples for this stage
        # For each planned slot, we want R replicates per template (equal across templates in this plan)
        # Compute target replicate count per template index within this stage
        target_reps = R                                      # Target replicates per template
        # Build a mapping from bank template index to how many replicates we already have
        have_counts: Dict[str, int] = {}                     # Track existing replicate counts
        for h, vals in by_tpl.items():                       # Iterate through existing samples
            have_counts[h] = len(vals)                       # Count samples per template hash

        # For each unique template in this stage, ensure we have target_reps replicates
        for bidx in tpl_indices:                             # Iterate through templates for this stage
            phr = PARAPHRASES[bidx]                          # Get paraphrase template text
            # Generate a provisional prompt hash using a dry-run call of hashing inside call_rpl_once_gpt5 is not possible
            # Instead, we actually make calls and collect; we will count by prompt_sha256 returned.
            # Determine how many more replicates needed by inspecting current by_tpl after calls.
            # We'll simply iterate replicate slots and guard with counts on returned hash.
            rep = 0                                          # Initialize replicate counter
            failures = 0                                    # Initialize failure counter
            max_failures = 5 * target_reps                   # Set maximum allowed failures
            while rep < target_reps:                         # Until we have enough replicates
                try:                                         # Attempt API call
                    out = call_rpl_once_gpt5(claim, phr, model)  # Make RPL API call
                    p = out["raw"]["prob_true"]              # Extract probability from response
                    l = _logit(p)                            # Convert to logit
                    h = out["meta"]["prompt_sha256"]         # Get prompt hash for grouping
                    curr = len(by_tpl.get(h, []))            # Check current count for this template
                    if curr < target_reps:                   # If we need more samples for this template
                        runs.append({**out, "paraphrase_idx": bidx, "replicate_idx": curr})  # Add to runs cache
                        by_tpl.setdefault(h, []).append(l)   # Add logit to template group
                        tpl_hashes.append(h)                 # Track template hash
                        rep = curr + 1                       # Update replicate count
                    else:                                    # If we already have enough samples
                        # Already have enough for this template hash (due to retries); skip counting
                        rep += 1                             # Just increment counter
                except Exception as e:                       # If API call fails
                    failures += 1                           # Increment failure count
                    if verbose:                              # If verbose logging enabled
                        print(f"[auto] WARN: call failed for template {bidx} (attempt {failures}): {e}", flush=True)  # Log failure
                    if failures >= max_failures:            # If too many failures
                        raise                                # Re-raise exception

        # After ensuring counts, aggregate for this stage
        ell_hat, (lo_l, hi_l), aggs, agg_info = _aggregate(claim, model, by_tpl, tpl_hashes)  # Run aggregation for current stage

        # Diagnostics from agg_info
        ci_width = float(aggs["ci_width"])                   # Extract CI width for gate evaluation
        stability = float(aggs["stability_score"])          # Extract stability score for gate evaluation
        imbalance = float(agg_info.get("imbalance_ratio", 1.0) or 1.0)  # Extract imbalance ratio for gate evaluation
        warn_flag = imbalance > imbalance_warn               # Check if imbalance exceeds warning threshold

        stage_id = f"S{i}-{_stage_digest(claim, model, K, R)}"  # Generate unique stage identifier

        # Build stage snapshot
        snapshot = {                                         # Create comprehensive stage snapshot
            "stage_id": stage_id,                            # Unique stage identifier
            "K": K,                                          # Number of paraphrase slots used
            "R": R,                                          # Number of replicates per paraphrase
            "T": T_stage,                                    # Number of unique templates used
            "p_RPL": aggs["prob_true_rpl"],                 # RPL probability estimate
            "ci95": aggs["ci95"],                           # 95% confidence interval
            "ci_width": ci_width,                           # CI width for gate evaluation
            "stability_score": stability,                   # Stability score for gate evaluation
            "stability_band": aggs["stability_band"],       # Stability band label
            "imbalance_ratio": imbalance,                   # Template imbalance ratio
            "is_stable": aggs["is_stable"],                 # Stability flag based on CI width
            "planned": {                                    # Planning diagnostics
                "offset": off,                              # Rotation offset used
                "order": bank_order,                        # Template order used
                "counts_by_template_planned": planned_c,    # Expected counts per template
                "imbalance_planned": planned_ratio,         # Expected imbalance ratio
            },
            "raw_run": {                                    # Raw run data for compatibility
                "run_id": f"rpl-g5-{stage_id}",            # Run identifier
                "claim": claim,                             # Original claim text
                "model": model,                             # Model used
                "prompt_version": PROMPT_VERSION,           # Prompt version for provenance
                "sampling": {"K": K, "R": R, "N": sum(len(v) for v in by_tpl.values())},  # Sampling parameters
                "decoding": {                               # Decoding parameters used
                    "max_output_tokens": 1024,              # Maximum output tokens
                    "reasoning_effort": "minimal",          # Reasoning effort level
                    "verbosity": "low",                     # Verbosity level
                },
                "aggregation": agg_info,                    # Aggregation metadata
                "timestamp": int(time.time()),              # Stage completion timestamp
                "aggregates": aggs,                         # Aggregate results
                "paraphrase_results": runs,                 # All API call results
                "paraphrase_balance": agg_info,             # Balance diagnostics
                "raw_logits": [x for vals in by_tpl.values() for x in vals],  # All logit values
            },
        }
        stages.append(snapshot)                             # Add stage to results list

        # Gate evaluation
        passes = (ci_width <= ci_width_max) and (stability >= stability_min) and (imbalance <= imbalance_max)  # Check if all gates pass
        gate_report = {                                      # Build detailed gate report
            "ci_width": {"value": ci_width, "threshold": ci_width_max, "pass": ci_width <= ci_width_max},  # CI width gate
            "stability": {"value": stability, "threshold": stability_min, "pass": stability >= stability_min},  # Stability gate
            "imbalance": {"value": imbalance, "threshold": imbalance_max, "pass": imbalance <= imbalance_max},  # Imbalance gate
        }
        if verbose:                                          # If verbose logging enabled
            print(f"[auto] Stage {i} metrics: p={aggs['prob_true_rpl']:.3f} width={ci_width:.3f} stability={stability:.3f} imbalance={imbalance:.2f}", flush=True)  # Print stage metrics
        if passes:                                           # If all gates pass
            decisions.append({                               # Record successful completion decision
                "stage_id": stage_id,                        # Stage identifier
                "action": "stop_pass",                       # Action taken
                "reason": "Passed quality gates.",          # Reason for stopping
                "gates": gate_report,                        # Gate evaluation details
                "warning": ("imbalance_warn" if warn_flag else None),  # Warning flag if applicable
            })
            break                                            # Exit stage loop early
        else:                                                # If gates fail
            if i < len(plan):                                # If more stages available
                next_T, nextK, nextR = plan[i]               # Get next stage parameters
                if verbose:                                  # If verbose logging enabled
                    print(f"[auto] Escalating to Stage {i+1}: T={next_T}, K={nextK}, R={nextR}", flush=True)  # Print escalation info
                decisions.append({                           # Record escalation decision
                    "stage_id": stage_id,                    # Stage identifier
                    "action": f"escalate_to_T{next_T}_K{nextK}_R{nextR}",  # Action taken
                    "reason": "; ".join(k for k, v in gate_report.items() if not v["pass"]) or "policy escalation",  # Failed gates
                    "gates": gate_report,                    # Gate evaluation details
                    "warning": ("imbalance_warn" if warn_flag else None),  # Warning flag if applicable
                })
            else:                                            # If no more stages available
                decisions.append({                           # Record limit reached decision
                    "stage_id": stage_id,                    # Stage identifier
                    "action": "stop_limits",                 # Action taken
                    "reason": "Reached maximum stage plan.", # Reason for stopping
                    "gates": gate_report,                    # Gate evaluation details
                    "warning": ("imbalance_warn" if warn_flag else None),  # Warning flag if applicable
                })

    final = stages[-1]                                      # Get final stage results
    return {                                                 # Return comprehensive orchestrator results
        "controller": {                                      # Controller metadata
            "policy": "templates-first-then-replicates",     # Escalation policy used
            "start": {"K": start_K, "R": start_R},           # Starting parameters
            "ceilings": {"max_K": max_K, "max_R": max_R},    # Maximum limits
            "gates": {                                       # Gate thresholds used
                "ci_width_max": ci_width_max,                # CI width threshold
                "stability_min": stability_min,              # Stability threshold
                "imbalance_max": imbalance_max,              # Imbalance threshold
                "imbalance_warn": imbalance_warn,            # Imbalance warning threshold
            },
            "timestamp": int(time.time()),                   # Controller completion timestamp
        },
        "claim": claim,                                      # Original claim text
        "model": model,                                      # Model used
        "final": {                                          # Final stage results summary
            "stage_id": final["stage_id"],                   # Final stage identifier
            "K": final["K"],                                # Final paraphrase slots
            "R": final["R"],                                # Final replicates per paraphrase
            "p_RPL": final["p_RPL"],                        # Final RPL probability estimate
            "ci95": final["ci95"],                          # Final confidence interval
            "ci_width": final["ci_width"],                  # Final CI width
            "stability_score": final["stability_score"],    # Final stability score
            "stability_band": final["stability_band"],      # Final stability band
            "imbalance_ratio": final["imbalance_ratio"],    # Final imbalance ratio
            "is_stable": final["is_stable"],                # Final stability flag
        },
        "stages": stages,                                   # All stage snapshots
        "decision_log": decisions,                          # Complete decision log
    }
