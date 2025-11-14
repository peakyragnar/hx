from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Optional

__all__ = [
    "PromptParts",
    "PromptTemplateError",
    "build_rpl_prompt",
    "build_wel_doc_prompt",
    "build_simple_expl_prompt",
]


class PromptTemplateError(RuntimeError):
    """Raised when a requested prompt resource cannot be located."""


@dataclass(frozen=True)
class PromptParts:
    """Container for the system + user prompt pair passed to adapters."""

    system: str
    user: str


_PROVIDER_ALIASES = {
    "": "openai",
    "gpt-5": "openai",
    "openai:gpt-5": "openai",
    "openai": "openai",
    "grok-4": "grok",
    "grok": "grok",
    "xai": "grok",
    "google": "gemini",
    "gemini": "gemini",
    "gemini-1.5": "gemini",
    "deepseek": "deepseek",
    "deepseek-r1": "deepseek",
}


@lru_cache(maxsize=None)
def _load_text(relative_path: str) -> str:
    """Read and cache prompt text from the package resources."""

    base = resources.files("heretix.prompts")
    target = base.joinpath(relative_path)
    if not target.is_file():
        raise PromptTemplateError(f"Missing prompt template: {relative_path}")
    return target.read_text(encoding="utf-8").strip()


def _try_load(relative_path: str) -> Optional[str]:
    try:
        return _load_text(relative_path)
    except PromptTemplateError:
        return None


def _normalize_provider(name: Optional[str]) -> str:
    key = (name or "").strip().lower()
    return _PROVIDER_ALIASES.get(key, key or "openai")


def _compose_system_text(category: str, provider: Optional[str], fallback_variant: Optional[str]) -> str:
    parts: list[str] = []
    shared = _try_load(f"{category}/shared_v1.md")
    if shared:
        parts.append(shared)

    variant = _normalize_provider(provider) if provider else None
    attempted = []
    if variant:
        attempted.append(f"{category}/{variant}_v1.md")
    if fallback_variant:
        attempted.append(f"{category}/{fallback_variant}_v1.md")

    for rel in attempted:
        text = _try_load(rel)
        if text:
            parts.append(text)
            break

    if not parts:
        raise PromptTemplateError(f"No prompt content found for category '{category}'")
    return "\n\n".join(part for part in parts if part).strip()


def _inject_claim(paraphrase: str, claim: str) -> str:
    if "{CLAIM}" in paraphrase:
        return paraphrase.replace("{CLAIM}", claim)
    return paraphrase


def build_rpl_prompt(provider: str, *, claim: str, paraphrase: str) -> PromptParts:
    """Construct the Raw Prior Lens prompt for a provider."""

    system = _compose_system_text("rpl_sample", provider, fallback_variant="openai")
    claim_text = claim.strip()
    para_text = _inject_claim(paraphrase.strip(), claim_text)
    user = (
        f"Claim: {claim_text}\n"
        f"Paraphrase: {para_text}\n"
        "Return JSON that matches the schema described in the system instructions."
    )
    return PromptParts(system=system, user=user)


def build_wel_doc_prompt(
    provider: str,
    *,
    claim: str,
    document: str,
    source: Optional[str] = None,
) -> PromptParts:
    """Construct the WEL document scoring prompt."""

    system = _compose_system_text("wel_doc", provider, fallback_variant="openai")
    parts = [f"Claim: {claim.strip()}", "Document snippet:", document.strip()]
    if source:
        parts.append(f"Source: {source.strip()}")
    parts.append("Return JSON that matches the WELDocV1 schema.")
    user = "\n".join(parts)
    return PromptParts(system=system, user=user)


def build_simple_expl_prompt(
    provider: Optional[str] = None,
    *,
    claim: str,
    context: str,
    style: str = "narrator",
) -> PromptParts:
    """Construct the explanation prompt used to narrate prior + web results."""

    variant = provider or style or "narrator"
    system = _compose_system_text("simple_expl", variant, fallback_variant="narrator")
    user = (
        f"Claim: {claim.strip()}\n"
        "Context summary:\n"
        f"{context.strip()}\n"
        "Return JSON that matches SimpleExplV1 (title, body_paragraphs, bullets)."
    )
    return PromptParts(system=system, user=user)
