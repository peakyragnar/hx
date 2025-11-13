from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional
import os
import json
import yaml

from heretix.provider.utils import infer_provider_from_model


@dataclass
class RunConfig:
    claim: Optional[str] = None
    model: str = "gpt-5"
    provider: Optional[str] = None
    models: Optional[List[str]] = None
    prompt_version: str = "rpl_g5_v2"
    K: int = 8
    R: int = 2
    T: Optional[int] = None  # number of templates to use (defaults to all in YAML)
    B: int = 5000
    seed: Optional[int] = None
    max_output_tokens: int = 1024
    # Prompt character limit (system + schema + user text). Enforced globally.
    max_prompt_chars: Optional[int] = 1200
    no_cache: bool = False
    prompts_file: Optional[str] = None  # explicit path; defaults by prompt_version

    # Derived at runtime; not part of input
    prompt_file_path: Optional[str] = None


@dataclass(frozen=True)
class RuntimeSettings:
    rpl_max_workers: int = int(os.getenv("HERETIX_RPL_CONCURRENCY", "8"))
    l1_ttl_seconds: int = int(os.getenv("HERETIX_L1_TTL", "900"))
    l1_max_items: int = int(os.getenv("HERETIX_L1_MAX", "2048"))
    cache_ttl_seconds: int = int(os.getenv("HERETIX_CACHE_TTL", "0"))
    fast_ci_B: int = int(os.getenv("HERETIX_FAST_B", "1000"))
    final_ci_B: int = int(os.getenv("HERETIX_FINAL_B", "5000"))
    fast_then_final: bool = os.getenv("HERETIX_FAST_FINAL", "1") == "1"
    price_per_1k_prompt: float = float(os.getenv("HERETIX_PRICE_IN", "5.00"))
    price_per_1k_output: float = float(os.getenv("HERETIX_PRICE_OUT", "15.00"))


def load_run_config(path: str | Path) -> RunConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text()) if p.suffix in {".yaml", ".yml"} else json.loads(p.read_text())
    cfg = RunConfig(**data)
    cfg.models = _normalize_models(cfg.models)
    if cfg.models:
        cfg.model = cfg.models[0]
    if not cfg.provider:
        cfg.provider = infer_provider_from_model(cfg.model)
    # Env fallback (config takes precedence)
    if cfg.seed is None and os.getenv("HERETIX_RPL_SEED") is not None:
        try:
            cfg.seed = int(os.getenv("HERETIX_RPL_SEED"))
        except Exception:
            pass
    if os.getenv("HERETIX_RPL_NO_CACHE"):
        cfg.no_cache = True
    if cfg.prompts_file is None:
        # default prompts path by version name
        cfg.prompt_file_path = str(Path(__file__).parent / "prompts" / f"{cfg.prompt_version}.yaml")
    else:
        cfg.prompt_file_path = cfg.prompts_file
    return cfg


def load_runtime_settings() -> RuntimeSettings:
    """Return runtime execution settings (concurrency, cache TTLs, CI budgets)."""
    return RuntimeSettings()


def _normalize_models(raw: Any) -> Optional[List[str]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        return None

    normalized: List[str] = []
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in normalized:
            continue
        normalized.append(text)
    return normalized or None
