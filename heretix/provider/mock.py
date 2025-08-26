from __future__ import annotations

import hashlib
import json
import time
from typing import Dict, Any

import numpy as np


def score_claim_mock(
    *,
    claim: str,
    system_text: str,
    user_template: str,
    paraphrase_text: str,
    model: str = "gpt-5",
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    """Deterministic mock provider output for smoke tests (no network).

    Uses a seed derived from (claim|paraphrase_text) to generate a stable
    probability near 0.25 with small, template-specific variation.
    """
    # Compute a deterministic prompt hash and RNG seed
    user_text = f"{paraphrase_text.replace('{CLAIM}', claim)}\n\n" + user_template.replace("{CLAIM}", claim)
    full_instructions = system_text + "\n\n" + "MOCK"
    prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

    # Derive template-local RNG seed
    seed = int(hashlib.sha256((prompt_sha256 + "|" + claim).encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)

    # Generate a mock probability around 0.25 with slight deterministic jitter
    base = 0.25
    jitter = float(rng.normal(0, 0.02))  # small spread
    p = min(max(base + jitter, 0.05), 0.95)

    raw = {
        "prob_true": round(p, 2),
        "confidence_self": 0.6,
        "assumptions": [
            "Assume reasonable scope/definitions",
            "Assume no retrieval used",
        ],
        "reasoning_bullets": [
            "Mock: prior-based estimation only",
            "Mock: paraphrase sensitivity check",
            "Mock: no citations permitted",
        ],
        "contrary_considerations": [
            "Mock: potential wording artifacts",
            "Mock: underspecification risk",
        ],
        "ambiguity_flags": [
            "Mock output",
        ],
    }

    return {
        "raw": raw,
        "meta": {
            "provider_model_id": f"{model}-MOCK",
            "prompt_sha256": prompt_sha256,
            "response_id": f"mock_{prompt_sha256[:12]}",
            "created": float(int(time.time())),
        },
        "timing": {"latency_ms": 5},
    }

