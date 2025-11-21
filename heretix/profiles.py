from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Sequence, Tuple


@dataclass(frozen=True)
class RPLProfile:
    """Profile describing an RPL sampling configuration.

    Profiles keep high-level knobs (K, R, T, B, token limits, and an overall
    sample budget) in one place so that both CLI and API callers can reuse
    the same presets without duplicating constants.
    """

    name: str
    K: int
    R: int
    T: int
    B: Optional[int]
    max_output_tokens: int
    # Total sample budget across all selected models. The harness-level
    # planner will keep the aggregate K*R*T per model under this budget.
    total_sample_budget: int
    # Controls how explanations are obtained relative to measurement:
    # - "separate_call": fast JSON-only sampling, then a follow-up explainer call
    # - "inline": probability and explanation gathered in the same call
    # - "none": obtain probabilities only; caller is responsible for narration
    explanation_mode: Literal["separate_call", "inline", "none"]


BIAS_FAST = RPLProfile(
    name="bias_fast",
    K=4,
    R=1,
    T=6,
    # Hot path: use fast/CI-free aggregation; the harness will interpret
    # a non-positive B as "no bootstrap" for this profile.
    B=0,
    max_output_tokens=192,
    total_sample_budget=72,
    explanation_mode="separate_call",
)


RPL_RESEARCH = RPLProfile(
    name="rpl_research",
    K=8,
    R=2,
    T=8,
    B=5000,
    max_output_tokens=1024,
    # Effectively unbounded for research/CLI experiments.
    total_sample_budget=999_999,
    explanation_mode="inline",
)


def derive_sampling_plan(models: Sequence[str], profile: RPLProfile) -> Dict[str, Tuple[int, int, int]]:
    """Return per-model (K, R, T) honoring a shared sample budget.

    The planner keeps profile defaults when within budget; otherwise it scales
    down K first (to preserve template coverage) and only reduces T if the
    budget is still exceeded. We try to keep T >= 5 so that trimmed-center
    behavior remains available whenever the budget allows.
    """

    # Deduplicate while preserving order
    unique_models: list[str] = []
    for raw in models:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text in unique_models:
            continue
        unique_models.append(text)

    if not unique_models:
        return {}

    base_K = int(profile.K)
    base_R = int(profile.R)
    base_T = max(1, int(profile.T))
    budget = int(profile.total_sample_budget)

    def _samples_per_model(k: int, r: int, t: int) -> int:
        return max(1, k) * max(1, r) * max(1, t)

    base_per_model = _samples_per_model(base_K, base_R, base_T)
    total_base = base_per_model * len(unique_models)
    if budget <= 0 or total_base <= budget:
        return {m: (base_K, base_R, base_T) for m in unique_models}

    target_per_model = max(1, budget // len(unique_models))

    # First, try to shrink K while preserving template coverage.
    K_scaled = max(1, min(base_K, target_per_model // max(1, base_R * base_T)))
    T_scaled = base_T
    planned = _samples_per_model(K_scaled, base_R, T_scaled)

    # If we're still over budget, reduce T but avoid dropping below 5 unless necessary.
    if planned > target_per_model:
        preferred_min_T = 5 if base_T >= 5 else 1
        max_T_for_budget = max(1, target_per_model // max(1, K_scaled * base_R))
        if max_T_for_budget >= preferred_min_T:
            T_scaled = min(base_T, max_T_for_budget)
        else:
            T_scaled = max(1, max_T_for_budget)
        planned = _samples_per_model(K_scaled, base_R, T_scaled)

    # Final guard: if rounding leaves us slightly above budget, trim K again.
    if planned > target_per_model and K_scaled > 1:
        K_cap = max(1, target_per_model // max(1, T_scaled * base_R))
        K_scaled = max(1, min(K_scaled, K_cap))

    return {m: (K_scaled, base_R, T_scaled) for m in unique_models}
