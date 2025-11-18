from __future__ import annotations


def infer_provider_from_model(model: str | None) -> str | None:
    """Best-effort mapping from logical model id to provider id."""

    text = (model or "").strip().lower()
    if not text:
        return None
    if text.startswith("grok") or "grok" in text or text.startswith("xai"):
        return "xai"
    if text.startswith("claude") or "anthropic" in text:
        return "anthropic"
    if "gemini" in text or "google" in text:
        return "google"
    if "gpt" in text or "openai" in text or text.startswith("o1"):
        return "openai"
    return None


__all__ = ["infer_provider_from_model"]
