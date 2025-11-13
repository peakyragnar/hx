from __future__ import annotations


def infer_provider_from_model(model: str | None) -> str:
    """Best-effort mapping from logical model id to provider id."""

    text = (model or "").strip().lower()
    if not text:
        return "openai"
    if text.startswith("grok") or "grok" in text or text.startswith("xai"):
        return "xai"
    if text.startswith("claude") or "anthropic" in text:
        return "anthropic"
    if "gemini" in text or "google" in text:
        return "google"
    if "deepseek" in text or text.endswith("-r1") or "r1" in text:
        return "deepseek"
    return "openai"


__all__ = ["infer_provider_from_model"]
