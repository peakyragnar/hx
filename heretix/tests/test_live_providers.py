from __future__ import annotations

import os
from pathlib import Path

import pytest

from heretix.config import RunConfig
from heretix.rpl import run_single_version

pytestmark = pytest.mark.live

PROMPT_FILE = str(Path(__file__).resolve().parents[1] / "prompts" / "rpl_g5_v2.yaml")
TRUE_CLAIM = "The Earth orbits the Sun."


LIVE_PROVIDERS = [
    ("openai", "gpt-5", "OPENAI_API_KEY"),
    ("xai", "grok-4", "XAI_API_KEY"),
    ("google", "gemini25-default", "GEMINI_API_KEY"),
    ("deepseek", "deepseek-r1", "DEEPSEEK_API_KEY"),
]


@pytest.mark.parametrize("provider,model,env_var", LIVE_PROVIDERS)
def test_true_claim_prob_high(provider: str, model: str, env_var: str) -> None:
    if not os.getenv(env_var):
        pytest.skip(f"{env_var} not configured")

    cfg = RunConfig(
        claim=TRUE_CLAIM,
        model=model,
        provider=provider,
        prompt_version="rpl_g5_v2",
        K=4,
        R=1,
        T=4,
        B=200,
        max_output_tokens=256,
        max_prompt_chars=2000,
    )

    result = run_single_version(cfg, prompt_file=PROMPT_FILE, mock=False)
    combined = result.get("combined") or result.get("prior")
    assert combined is not None
    prob = combined.get("prob_true")
    if prob is None:
        prob = combined.get("p")
    assert prob is not None
    assert prob > 0.8
