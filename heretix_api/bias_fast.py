from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from heretix.bias import run_profiled_models
from heretix.config import RunConfig
from heretix.profiles import BIAS_FAST
from heretix.types import RunResult


def _coerce_models(raw: Iterable[str] | None) -> list[str]:
    """Normalize and deduplicate model names."""
    if not raw:
        return []
    seen = set()
    models: list[str] = []
    for item in raw:
        if item is None:
            continue
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        models.append(name)
    return models


def run_bias_fast(
    *,
    claim: str,
    models: Sequence[str],
    persist_to_sqlite: bool = False,
    mock: bool = False,
    base_config: RunConfig | None = None,
    prompt_root: Path | None = None,
) -> RunResult:
    """Execute a bias_fast harness run across one or more models.

    The harness already writes to SQLite internally; `persist_to_sqlite` is
    surfaced for callers that want to explicitly opt in (CLI) versus treat the
    run as stateless (API). The current harness always writes; future work can
    read this flag to skip persistence once supported.
    """

    models_clean = _coerce_models(models)
    if not models_clean:
        raise ValueError("run_bias_fast requires at least one model")

    cfg = RunConfig() if base_config is None else RunConfig(**{**base_config.__dict__})
    cfg.claim = claim
    cfg.models = list(models_clean)
    if not cfg.model and models_clean:
        cfg.model = models_clean[0]
    cfg.profile = BIAS_FAST.name

    return run_profiled_models(
        claim=claim,
        models=models_clean,
        profile=BIAS_FAST,
        base_config=cfg,
        prompt_root=prompt_root,
        mock=mock,
    )
