"""
Compatibility tests for evaluate_rpl_gpt5 with expanded paraphrase bank.

Ensures legacy behavior of cycling first 5 templates is preserved so existing
tests and baselines remain comparable even when PARAPHRASES grows.
"""
import hashlib
from typing import Dict

from heretix_rpl import rpl_eval


def _mock_call(paraphrase_to_hash: Dict[str, str]):
    def _inner(claim_text: str, paraphrase: str, model: str = "gpt-5"):
        # Stable prob derived from paraphrase hash for determinism
        h = paraphrase_to_hash.setdefault(
            paraphrase, hashlib.sha256(paraphrase.encode()).hexdigest()
        )
        prob = ((int(h[:8], 16) % 60) + 20) / 100.0  # 0.20..0.79
        return {
            "model": model,
            "raw": {"prob_true": prob},
            "meta": {"prompt_sha256": h, "provider_model_id": model, "prompt_version": rpl_eval.PROMPT_VERSION},
        }
    return _inner


def test_evaluate_rpl_gpt5_uses_first_5_templates(monkeypatch):
    # Monkeypatch networked call
    cache = {}
    monkeypatch.setattr(rpl_eval, "call_rpl_once_gpt5", _mock_call(cache))
    # Run with K > 5, R = 1 to maximize unique paraphrases
    out = rpl_eval.evaluate_rpl_gpt5("claim", model="gpt-5", K=8, R=1, agg="clustered")
    hashes = [row["meta"]["prompt_sha256"] for row in out["paraphrase_results"]]
    assert len(set(hashes)) <= 5

