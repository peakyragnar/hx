from __future__ import annotations

from typing import Protocol, Dict, Any, runtime_checkable


@runtime_checkable
class RPLAdapter(Protocol):
    """Protocol for RPL provider adapters.

    Implementations must return a dict with keys:
    - raw: parsed JSON object from provider (schema-conformant or empty dict on failure)
    - meta: provider metadata including provider_model_id, prompt_sha256, response_id, created
    - timing: timing info such as latency_ms
    """

    def score_claim(
        self,
        *,
        claim: str,
        system_text: str,
        user_template: str,
        paraphrase_text: str,
        model: str,
        max_output_tokens: int,
    ) -> Dict[str, Any]:
        ...

