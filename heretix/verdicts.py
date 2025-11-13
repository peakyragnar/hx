"""Shared helpers for verdict labeling and combined block metadata."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

VerdictMeta = Tuple[str, str, str, str]


def classify_probability(prob: float | None) -> VerdictMeta:
    """
    Convert a probability into user-facing verdict metadata.

    Returns (label, shout_label, headline, interpretation).
    """
    value = _safe_float(prob, default=0.5)
    if value >= 0.60:
        return (
            "Likely true",
            "LIKELY TRUE",
            "Why it’s likely true",
            "GPT‑5 leans toward this claim being true based on its training data.",
        )
    if value <= 0.40:
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


def verdict_label(prob: float | None) -> str:
    """Handy alias when only the human-readable label is needed."""
    return classify_probability(prob)[0]


def finalize_combined_block(
    block: Optional[Dict[str, Any]],
    *,
    weight_web: Optional[float] = None,
    fallback_prob: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Normalize a combined verdict block with explicit weighting metadata.

    Ensures the returned dict contains:
      - prob_true / ci_lo / ci_hi (for consumers that prefer flat keys)
      - label (Likely true/false/Uncertain)
      - weight_web / weight_prior (contributions from web vs model prior)
    """
    if block is None:
        return None

    combined = dict(block)
    prob_val = combined.get("p")
    if prob_val is None:
        prob_val = fallback_prob
    prob_val = _safe_float(prob_val, default=0.5)
    combined["p"] = prob_val
    combined["prob_true"] = prob_val

    ci_vals = combined.get("ci95")
    if isinstance(ci_vals, (list, tuple)) and len(ci_vals) >= 2:
        ci_lo = _safe_float(ci_vals[0], default=prob_val)
        ci_hi = _safe_float(ci_vals[1], default=prob_val)
    else:
        ci_lo = _safe_float(combined.get("ci_lo"), default=prob_val)
        ci_hi = _safe_float(combined.get("ci_hi"), default=prob_val)
        combined["ci95"] = [ci_lo, ci_hi]
    combined["ci_lo"] = ci_lo
    combined["ci_hi"] = ci_hi

    combined["label"] = verdict_label(prob_val)

    resolved = bool(combined.get("resolved"))
    if resolved:
        web_weight = 1.0
    else:
        if weight_web is None:
            weight_web = combined.get("weight_web")
        web_weight = _clamp01(weight_web, default=0.0)
    combined["weight_web"] = web_weight
    combined["weight_prior"] = _clamp01(1.0 - web_weight, default=1.0)
    return combined


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = default
    if num != num:  # NaN check
        return default
    return num


def _clamp01(value: Any, default: float = 0.0) -> float:
    base = _safe_float(value, default=default)
    if base < 0.0:
        return 0.0
    if base > 1.0:
        return 1.0
    return base


__all__ = ["classify_probability", "verdict_label", "finalize_combined_block"]
