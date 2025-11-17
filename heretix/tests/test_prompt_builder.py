import pytest

from heretix.prompts.prompt_builder import (
    PromptParts,
    build_rpl_prompt,
    build_simple_expl_prompt,
    build_wel_doc_prompt,
)


def test_build_rpl_prompt_merges_shared_and_provider_text() -> None:
    parts = build_rpl_prompt(
        "openai",
        claim="Tariffs cause inflation",
        paraphrase="Assess {CLAIM} using prior knowledge only.",
    )
    assert isinstance(parts, PromptParts)
    assert "Raw Prior Lens" in parts.system
    assert "Provider notes (OpenAI GPT-5)" in parts.system
    assert "Tariffs cause inflation" in parts.user
    assert "Assess Tariffs cause inflation" in parts.user
    assert parts.user.endswith("schema described in the system instructions.")


def test_build_rpl_prompt_falls_back_to_openai_when_missing() -> None:
    parts = build_rpl_prompt(
        "unknown-provider",
        claim="The moon is made of basalt",
        paraphrase="What is the probability {CLAIM}?",
    )
    assert "Provider notes (OpenAI GPT-5)" in parts.system
    assert "moon is made of basalt" in parts.user


def test_build_wel_doc_prompt_includes_source() -> None:
    parts = build_wel_doc_prompt(
        "grok",
        claim="Tariffs drive inflation",
        document="Analysts found limited pass-through in 2023.",
        source="https://example.test/tariffs",
    )
    assert "Web-Informed Lens" in parts.system
    assert "Provider notes (xAI Grok)" in parts.system
    assert "Document snippet" in parts.user
    assert "https://example.test/tariffs" in parts.user


def test_build_simple_expl_prompt_uses_context_and_style() -> None:
    context = "Prior 0.42, web lens nudged to 0.55 with narrow CI."
    parts = build_simple_expl_prompt(
        claim="Tariffs cause inflation",
        context=context,
    )
    assert "Explanation Lens" in parts.system
    assert "Narrator style" in parts.system
    assert context in parts.user
    assert "SimpleExplV1" in parts.user


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("openai", "Provider notes (OpenAI GPT-5)"),
        ("grok", "Provider notes (xAI Grok)"),
        ("google", "Provider notes (Google Gemini)"),
    ],
)
def test_build_rpl_prompt_includes_provider_specific_text(provider: str, expected: str) -> None:
    parts = build_rpl_prompt(
        provider,
        claim="Tariffs are neutral",
        paraphrase="Estimate P(true) that {CLAIM}",
    )
    assert expected in parts.system
    assert "Estimate P(true)" in parts.user


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("openai", "Provider notes (OpenAI GPT-5)"),
        ("grok", "Provider notes (xAI Grok)"),
        ("google", "Provider notes (Google Gemini)"),
    ],
)
def test_build_wel_doc_prompt_includes_provider_specific_text(provider: str, expected: str) -> None:
    parts = build_wel_doc_prompt(
        provider,
        claim="Claim for WEL doc",
        document="Document body",
        source="https://example.com",
    )
    assert expected in parts.system
    assert "Document snippet" in parts.user


def test_build_simple_expl_prompt_falls_back_to_narrator() -> None:
    parts = build_simple_expl_prompt(
        provider="unknown-provider",
        claim="Fallback claim",
        context="Fallback context summary.",
    )
    assert "Narrator style" in parts.system
    assert "Fallback context summary." in parts.user
