from __future__ import annotations

from typing import Iterable, Any


def _append_text(target: list[str], items: Iterable[Any]) -> None:
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip().rstrip(".;")
        if not text:
            continue
        if not text.endswith("."):
            text += "."
        target.append(text)
        if len(target) >= 3:
            break


def extract_reasons(payload: dict | None) -> list[str]:
    raw = (payload or {}).get("raw") or {}
    reasons: list[str] = []

    primary = raw.get("reasons") or raw.get("reasoning_bullets") or []
    _append_text(reasons, primary)
    if len(reasons) < 3:
        _append_text(reasons, raw.get("contrary_considerations") or [])
    if len(reasons) < 3:
        _append_text(reasons, raw.get("assumptions") or [])
    if len(reasons) < 3:
        _append_text(reasons, raw.get("uncertainties") or [])
    if len(reasons) < 3:
        _append_text(reasons, raw.get("ambiguity_flags") or [])

    return reasons[:3]


__all__ = ["extract_reasons"]
