from __future__ import annotations

from typing import Callable, Iterable, Dict

from . import ensure_adapters_loaded

__all__ = ["register_score_fn", "get_score_fn", "get_live_scorer", "list_registered_models"]

_SCORE_REGISTRY: Dict[str, Callable] = {}


def _normalize(name: str) -> str:
    return (name or "").strip().lower()


def register_score_fn(*, aliases: Iterable[str], fn: Callable) -> None:
    """Register a provider adapter function for one or more model aliases.

    Adapter modules call this at import time so new models only need to add a module.
    """

    if not callable(fn):
        raise TypeError("fn must be callable")

    alias_list = [_normalize(alias) for alias in aliases if _normalize(alias)]
    if not alias_list:
        raise ValueError("At least one non-empty alias is required")

    for alias in alias_list:
        existing = _SCORE_REGISTRY.get(alias)
        if existing is not None and existing is not fn:
            raise ValueError(f"Alias '{alias}' already registered to a different adapter")
        _SCORE_REGISTRY[alias] = fn


def get_score_fn(model: str) -> Callable:
    """Return the provider score function for a given model string."""

    ensure_adapters_loaded()
    key = _normalize(model)
    if not key:
        raise ValueError("model must be a non-empty string")
    try:
        return _SCORE_REGISTRY[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"No provider adapter registered for model='{model}'") from exc


def get_live_scorer(model: str) -> Callable:
    """Compatibility shim for existing harness import."""

    return get_score_fn(model)


def list_registered_models() -> list[str]:
    """Return the list of registered model aliases (lowercase)."""

    ensure_adapters_loaded()
    return sorted(_SCORE_REGISTRY.keys())
