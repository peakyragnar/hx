from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


_RATE_LIMIT_CACHE: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """Load provider configuration from HERETIX_PROVIDER_CONFIG if present.

    The YAML structure is expected to be:

    openai:
      defaults:
        rps: 2
        burst: 2
      models:
        gpt-5:
          rps: 2
          burst: 2

    Returns an empty dict if the file is not set or cannot be parsed.
    """
    global _RATE_LIMIT_CACHE
    if _RATE_LIMIT_CACHE is not None:
        return _RATE_LIMIT_CACHE

    path = os.getenv("HERETIX_PROVIDER_CONFIG")
    if not path:
        _RATE_LIMIT_CACHE = {}
        return _RATE_LIMIT_CACHE

    try:
        p = Path(path)
        if not p.exists():
            _RATE_LIMIT_CACHE = {}
            return _RATE_LIMIT_CACHE
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                data = {}
            _RATE_LIMIT_CACHE = data
            return _RATE_LIMIT_CACHE
    except Exception:
        # Fail closed to no-config; callers will fall back to env/defaults
        _RATE_LIMIT_CACHE = {}
        return _RATE_LIMIT_CACHE


def get_rate_limits(provider: str, model: str | None = None) -> Tuple[float, int]:
    """Return (rps, burst) for a provider/model.

    Precedence:
    1) HERETIX_PROVIDER_CONFIG YAML → provider.models[model] or provider.defaults
    2) Provider-specific env vars (e.g., HERETIX_OPENAI_RPS/HERETIX_OPENAI_BURST)
    3) Safe defaults (2 rps, burst=2)
    """
    cfg = _load_config()

    # 1) Config file lookup
    try:
        p_cfg = cfg.get(provider, {}) if isinstance(cfg, dict) else {}
        if model:
            models = p_cfg.get("models", {}) or {}
            m_cfg = models.get(model, {}) or {}
            rps = m_cfg.get("rps")
            burst = m_cfg.get("burst")
            if rps is not None and burst is not None:
                return float(rps), int(burst)
        defaults = p_cfg.get("defaults", {}) or {}
        rps = defaults.get("rps")
        burst = defaults.get("burst")
        if rps is not None and burst is not None:
            return float(rps), int(burst)
    except Exception:
        # Fall through to env/defaults
        pass

    # 2) Env vars fallback for known providers
    if provider.lower() == "openai":
        rps_env = os.getenv("HERETIX_OPENAI_RPS")
        burst_env = os.getenv("HERETIX_OPENAI_BURST")
        if rps_env and burst_env:
            try:
                return float(rps_env), int(burst_env)
            except Exception:
                pass

    # 3) Defaults
    return 2.0, 2


PROVIDER_CAPABILITIES_ENV = "HERETIX_PROVIDER_CAPABILITIES_PATH"


class ProviderCapabilities(BaseModel):
    provider: str
    default_model: str
    api_model_map: Dict[str, str]
    supports_json_schema: bool
    supports_json_mode: bool
    supports_tools: bool
    supports_seed: bool
    max_output_tokens: int = Field(gt=0)
    default_temperature: float = 0.0

    @model_validator(mode="after")
    def _ensure_default_model(self) -> "ProviderCapabilities":
        if self.default_model not in self.api_model_map:
            raise ValueError(
                f"default_model '{self.default_model}' missing from api_model_map for provider '{self.provider}'"
            )
        return self


PROVIDERS: Dict[str, ProviderCapabilities] = {}
_CAPABILITIES_CACHE: Dict[str, ProviderCapabilities] | None = None


def _list_yaml_files(directory: Path) -> list[Path]:
    seen: dict[Path, Path] = {}
    for pattern in ("*.yaml", "*.yml"):
        for path in directory.glob(pattern):
            if path.is_file():
                seen.setdefault(path.resolve(), path)
    return sorted(seen.values(), key=lambda p: p.name)


def _resolve_capability_paths() -> list[Path]:
    override = os.getenv(PROVIDER_CAPABILITIES_ENV)
    if override:
        p = Path(override)
        if p.is_dir():
            return _list_yaml_files(p)
        return [p] if p.is_file() else []

    pkg_dir = Path(__file__).resolve().parent
    paths = _list_yaml_files(pkg_dir)
    if not paths:
        # Fall back to legacy single-file config if set.
        legacy = os.getenv("HERETIX_PROVIDER_CONFIG")
        if legacy:
            legacy_path = Path(legacy)
            if legacy_path.is_file():
                return [legacy_path]
    return paths


def load_provider_capabilities(*, refresh: bool = False) -> Dict[str, ProviderCapabilities]:
    """Return ProviderCapabilities records keyed by provider id."""
    global _CAPABILITIES_CACHE
    if _CAPABILITIES_CACHE is not None and not refresh:
        return _CAPABILITIES_CACHE

    capability_paths = _resolve_capability_paths()
    records: Dict[str, ProviderCapabilities] = {}
    errors: list[str] = []

    for path in capability_paths:
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
        except FileNotFoundError:
            continue
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"{path}: {exc}")
            continue

        if not isinstance(raw, dict) or not raw:
            errors.append(f"{path}: empty or invalid capability payload")
            continue

        try:
            caps = ProviderCapabilities.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Invalid provider capability file {path}: {exc}") from exc

        records[caps.provider] = caps

    if not records:
        details = f" ({'; '.join(errors)})" if errors else ""
        raise RuntimeError(
            "Provider capability files not found or empty. "
            "Add config_*.yaml under heretix/provider or set "
            f"{PROVIDER_CAPABILITIES_ENV} to a YAML file/directory{details}."
        )

    PROVIDERS.clear()
    PROVIDERS.update(records)
    _CAPABILITIES_CACHE = records
    return _CAPABILITIES_CACHE


def reset_provider_capabilities_cache() -> None:
    """Testing helper to clear the cached capability records."""
    global _CAPABILITIES_CACHE
    _CAPABILITIES_CACHE = None
