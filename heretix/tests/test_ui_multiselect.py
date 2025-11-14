from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup


HTML_PATH = Path(__file__).resolve().parents[2] / "ui" / "index.html"


def _load_dom() -> tuple[str, BeautifulSoup]:
    text = HTML_PATH.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")
    return text, soup


def test_model_checkboxes_cover_all_providers():
    _, soup = _load_dom()
    inputs = soup.select('input[name="ui_model"]')
    assert len(inputs) == 4, "expected four multi-select checkboxes"
    values = {el.get("value") for el in inputs}
    assert values == {"gpt-5", "grok-4", "gemini-2.5", "deepseek-r1"}
    checked = [el for el in inputs if el.has_attr("checked")]
    assert checked and checked[0]["value"] == "gpt-5"


def test_mode_select_preserves_baseline_and_web_options():
    _, soup = _load_dom()
    select = soup.find("select", attrs={"name": "ui_mode"})
    assert select is not None
    options = {opt.get("value"): (opt.text or "").strip() for opt in select.find_all("option")}
    assert options["prior"].startswith("Internal knowledge")
    assert options["internet-search"].startswith("Internet search")


def test_processing_overlay_and_results_grid_exist():
    _, soup = _load_dom()
    assert soup.find(id="loading-overlay") is not None
    assert soup.find(id="results-card-grid") is not None


def test_model_map_defines_provider_and_logical_model():
    html_text, _ = _load_dom()
    expectations = {
        "gpt-5": {"provider": "openai", "logical": "gpt-5"},
        "grok-4": {"provider": "xai", "logical": "grok-4"},
        "gemini-2.5": {"provider": "google", "logical": "gemini25-default"},
        "deepseek-r1": {"provider": "deepseek", "logical": "deepseek-r1"},
    }
    for code, meta in expectations.items():
        pattern = re.compile(
            rf'"{re.escape(code)}"\s*:\s*\{{[^}}]*provider:\s*"{re.escape(meta["provider"])}"[^}}]*'
            rf'logical_model:\s*"{re.escape(meta["logical"])}"',
            re.DOTALL,
        )
        assert pattern.search(html_text), f"missing provider/logical mapping for {code}"


def test_frontend_posts_required_fields_per_model():
    html_text, _ = _load_dom()
    assert "runModelRequest" in html_text
    assert "claim: claimValue" in html_text
    assert "mode: modeNormalized" in html_text
    assert "logical_model: meta.logical_model" in html_text
    assert "provider: meta.provider" in html_text
    assert "Promise.allSettled" in html_text
