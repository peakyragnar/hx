from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_ui_module():
    spec = importlib.util.spec_from_file_location(
        "heretix_ui_serve", Path(__file__).resolve().parents[2] / "ui" / "serve.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


ui = _load_ui_module()


def _make_handler():
    # BaseHTTPRequestHandler expects a socket; we only exercise helper methods, so bypass __init__.
    return ui.Handler.__new__(ui.Handler)


def test_build_card_html_baseline_mode():
    handler = _make_handler()
    run = {
        "combined": {"p": 0.64, "ci_lo": 0.52, "ci_hi": 0.75, "label": "Likely"},
        "aggregates": {
            "prob_true_rpl": 0.64,
            "ci95": [0.52, 0.75],
            "ci_width": 0.23,
            "stability_score": 0.58,
            "stability_band": "medium",
            "rpl_compliance_rate": 0.99,
            "cache_hit_rate": 0.0,
        },
        "prior": {"p": 0.62, "ci95": [0.50, 0.74], "stability": 0.57},
        "simple_expl": {
            "title": "Model prior leans true",
            "summary": "Training data points to mild inflationary pressure.",
            "lines": [
                "Tariffs raise import prices",
                "Downstream businesses pass higher costs",
            ],
            "body_paragraphs": ["Model reasoning favors inflationary effects."],
        },
    }
    meta = {"label": "GPT‑5"}
    card_html = handler._build_card_html(run, meta, "Internal knowledge only", False)

    assert "class=\"result-card\"" in card_html
    assert "GPT‑5 · Internal knowledge only" in card_html
    assert "67.0%" in card_html or "64%" in card_html
    assert "Training-only (model prior)" in card_html
    assert "Copy summary" in card_html


def test_build_card_html_web_mode_resolved():
    handler = _make_handler()
    run = {
        "combined": {"p": 0.58, "ci_lo": 0.44, "ci_hi": 0.70, "label": "Uncertain"},
        "aggregates": {
            "prob_true_rpl": 0.53,
            "ci95": [0.40, 0.66],
            "ci_width": 0.26,
            "stability_score": 0.41,
            "stability_band": "low",
            "rpl_compliance_rate": 1.0,
            "cache_hit_rate": 0.15,
        },
        "prior": {"p": 0.53, "ci95": [0.40, 0.66], "stability": 0.41},
        "simple_expl": {
            "title": "Mixed web signals",
            "summary": "Resolver found conflicting articles.",
            "lines": ["Supply chains absorb some tariff shocks."],
            "body_paragraphs": ["Evidence split between supportive and contradictory sources."],
        },
        "web": {
            "p": 0.58,
            "ci95": [0.44, 0.70],
            "evidence": {
                "n_docs": 6,
                "n_domains": 3,
                "median_age_days": 18,
            },
            "resolved": True,
            "resolved_truth": True,
            "resolved_reason": "Majority of recent sources report minimal inflation.",
        },
        "weights": {"w_web": 0.35, "recency": 0.6, "strength": 0.4},
    }
    meta = {"label": "Grok 4"}
    card_html = handler._build_card_html(run, meta, "Internet search", True)

    assert "Grok" in card_html
    assert "resolved-note" in card_html
    assert "Web evidence (recent)" in card_html
    assert "How we combine" in card_html
    assert "Copy summary" in card_html


def test_build_card_html_handles_bullets_only_simple_expl():
    handler = _make_handler()
    run = {
        "combined": {"p": 0.15, "ci95": [0.1, 0.2], "label": "Likely false"},
        "aggregates": {
            "prob_true_rpl": 0.15,
            "ci95": [0.1, 0.2],
            "ci_width": 0.1,
            "stability_score": 0.8,
            "rpl_compliance_rate": 1.0,
            "cache_hit_rate": 0.5,
        },
        "prior": {"p": 0.12, "ci95": [0.08, 0.18], "stability": 0.76},
        "simple_expl": {
            "title": "Plain-language fallback",
            "body_paragraphs": ["Baseline prior stayed in place."],
            "bullets": ["No web evidence nudged the result.", "Different phrasings still agreed."],
        },
    }
    meta = {"label": "Gemini 2.5"}
    card_html = handler._build_card_html(run, meta, "Internal knowledge only", False)

    assert "Plain-language fallback" in card_html
    assert "No web evidence nudged the result." in card_html
    assert "Copy summary" in card_html
