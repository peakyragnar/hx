from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml
import logging
import threading
from pydantic import BaseModel, Field, ValidationError, model_validator


_RATE_LIMIT_CACHE: dict[str, Any] | None = None
_LOGGER = logging.getLogger(__name__)
_RATE_LIMIT_WARNED: set[str] = set()
_CONFIG_LOCK = threading.Lock()
_CAP_LOCK = threading.Lock()
_MAX_PROVIDER_CONFIG_BYTES = 64 * 1024  # 64KiB guardrail for provider settings
_MAX_CAPABILITY_BYTES = 64 * 1024


def _load_yaml_payload(path: Path, *, max_bytes: int) -> Any:
    size = path.stat().st_size if path.exists() else 0
    if size > max_bytes:
        raise ValueError(f"{path} exceeds {max_bytes} byte limit")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_config() -> dict[str, Any]:
    """Load provider configuration from HERETIX_PROVIDER_CONFIG if present."""

    global _RATE_LIMIT_CACHE
    with _CONFIG_LOCK:
        if _RATE_LIMIT_CACHE is not None:
            return _RATE_LIMIT_CACHE

        path = os.getenv("HERETIX_PROVIDER_CONFIG")
        if not path:
            _RATE_LIMIT_CACHE = {}
            return _RATE_LIMIT_CACHE

        p = Path(path)
        if not p.exists():
            _RATE_LIMIT_CACHE = {}
            return _RATE_LIMIT_CACHE
        try:
            data = _load_yaml_payload(p, max_bytes=_MAX_PROVIDER_CONFIG_BYTES) or {}
            if not isinstance(data, dict):
                data = {}
            _RATE_LIMIT_CACHE = data
            return _RATE_LIMIT_CACHE
        except Exception as exc:
            _LOGGER.warning("Failed to load provider config from %s: %s", path, exc)
            _RATE_LIMIT_CACHE = {}
            return _RATE_LIMIT_CACHE


def get_rate_limits(provider: str, model: str | None = None) -> Tuple[float, int]:
    """Return (rps, burst) for a provider/model."""

    cfg = _load_config()

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
        pass

    if provider.lower() == "openai":
        rps_env = os.getenv("HERETIX_OPENAI_RPS")
        burst_env = os.getenv("HERETIX_OPENAI_BURST")
        if rps_env and burst_env:
            try:
                return float(rps_env), int(burst_env)
            except Exception:
                pass

    key = f"{provider}:{model or '*'}"
    if key not in _RATE_LIMIT_WARNED:
        _LOGGER.warning("Falling back to default rate limits for %s (%s)", provider, model or "any")
        _RATE_LIMIT_WARNED.add(key)
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
        legacy = os.getenv("HERETIX_PROVIDER_CONFIG")
        if legacy:
            legacy_path = Path(legacy)
            if legacy_path.is_file():
                return [legacy_path]
    return paths


def load_provider_capabilities(*, refresh: bool = False) -> Dict[str, ProviderCapabilities]:
    """Return ProviderCapabilities records keyed by provider id."""

    global _CAPABILITIES_CACHE
    with _CAP_LOCK:
        if _CAPABILITIES_CACHE is not None and not refresh:
            return _CAPABILITIES_CACHE

        capability_paths = _resolve_capability_paths()
        records: Dict[str, ProviderCapabilities] = {}
        errors: list[str] = []

        for path in capability_paths:
            try:
                raw = _load_yaml_payload(path, max_bytes=_MAX_CAPABILITY_BYTES) or {}
            except FileNotFoundError:
                continue
            except Exception as exc:
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
