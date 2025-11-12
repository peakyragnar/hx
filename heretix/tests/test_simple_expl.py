from __future__ import annotations

import pytest
from heretix.simple_expl import compose_simple_expl, compose_baseline_simple_expl, compose_deeper_expl, _sanitize


class TestSanitize:
    """Test the _sanitize function for cleaning bullet text."""

    def test_sanitize_basic_text(self):
        """Should preserve basic text unchanged."""
        assert _sanitize("This is a basic sentence") == "This is a basic sentence."

    def test_sanitize_adds_period(self):
        """Should add period if missing."""
        assert _sanitize("No period at end") == "No period at end."

    def test_sanitize_preserves_ending_punctuation(self):
        """Should keep existing ending punctuation."""
        assert _sanitize("Has period.") == "Has period."
        assert _sanitize("Question?") == "Question?"
        assert _sanitize("Exclamation!") == "Exclamation!"

    def test_sanitize_removes_domain_prefix(self):
        """Should strip leading domain prefixes."""
        assert _sanitize("example.com: Content here") == "Content here."
        assert _sanitize("news.org: News content") == "News content."
        assert _sanitize("site.co.uk: UK content") == "UK content."

    def test_sanitize_removes_brand_colon(self):
        """Should strip leading BrandName: patterns."""
        assert _sanitize("Apple: New product launch") == "New product launch."
        assert _sanitize("Microsoft: Cloud services") == "Cloud services."
        assert _sanitize("Tech Corp: Announcement") == "Announcement."

    def test_sanitize_removes_brand_reporting_verb(self):
        """Should strip BrandName + reporting verb patterns."""
        assert _sanitize("Reuters reports major development") == "major development."
        assert _sanitize("Bloomberg says market changed") == "market changed."
        assert _sanitize("CNN announces breaking news") == "breaking news."
        assert _sanitize("WSJ notes economic shift") == "economic shift."

    def test_sanitize_removes_parenthetical_sources(self):
        """Should remove bracketed/parenthetical source hints at end."""
        assert _sanitize("Content here (example.com)") == "Content here."
        assert _sanitize("More content [news.org]") == "More content."
        assert _sanitize("Text (some.co.uk)") == "Text."

    def test_sanitize_softens_dollar_amounts(self):
        """Should replace dollar amounts with qualitative phrase."""
        assert _sanitize("Cost is $500") == "Cost is a high value."
        assert _sanitize("Price $1,234.56 total") == "Price a high value total."

    def test_sanitize_softens_large_figures(self):
        """Should replace T/B/M/K suffixed numbers."""
        assert _sanitize("Value is 3T dollars") == "Value is a large figure dollars."
        assert _sanitize("Budget 500B approved") == "Budget a large figure approved."
        assert _sanitize("Population 2M people") == "Population a large figure people."

    def test_sanitize_handles_non_string(self):
        """Should return empty string for non-string input."""
        assert _sanitize(None) == ""
        assert _sanitize(123) == ""
        assert _sanitize([]) == ""

    def test_sanitize_handles_empty_string(self):
        """Should return empty string for empty input."""
        assert _sanitize("") == ""
        assert _sanitize("   ") == ""


class TestComposeSimpleExpl:
    """Tests for the narrative Simple View composer."""

    def test_infrastructure_claim_blends_bar_and_evidence(self):
        replicates = [
            {
                "support_bullets": [
                    "Construction contracts were awarded in March.",
                    "Transmission upgrades break ground this summer.",
                ],
                "oppose_bullets": [
                    "Permits are still pending at the federal level.",
                ],
                "notes": [
                    "State officials warned about grid constraints next year.",
                ],
            }
        ]
        result = compose_simple_expl(
            claim="The US will build 10 new nuclear power plants in 2025",
            combined_p=0.2,
            web_block={},
            replicates=replicates,
        )

        assert len(result["lines"]) == 3
        assert "would need permits" in result["lines"][0]
        assert "grid constraints" in result["lines"][1]
        assert "Construction contracts" in result["lines"][2]
        assert "likely false" in result["summary"]

    def test_progress_signals_surface_when_probability_high(self):
        replicates = [
            {
                "support_bullets": [
                    "Regulators approved the project last quarter.",
                    "Construction is 70% complete with new lines going live this summer.",
                ]
            }
        ]
        result = compose_simple_expl(
            claim="Company X will open five factories in 2025",
            combined_p=0.82,
            web_block={},
            replicates=replicates,
        )

        assert any("approved the project" in line for line in result["lines"])
        assert any("Construction is 70% complete" in line for line in result["lines"])
        assert "likely true" in result["summary"]

    def test_obstacles_surface_when_probability_low(self):
        replicates = [
            {
                "support_bullets": ["Developers announced intent to build."],
                "oppose_bullets": ["No funding has been appropriated."],
            }
        ]
        result = compose_simple_expl(
            claim="The city will complete 1,000 affordable units in 2024",
            combined_p=0.25,
            web_block={},
            replicates=replicates,
        )

        assert any("No funding" in line for line in result["lines"])
        assert "likely false" in result["summary"]

    def test_handles_missing_replicates_with_generic_context(self):
        result = compose_simple_expl(
            claim="Generic claim",
            combined_p=0.5,
            web_block={},
            replicates=None,
        )

        assert len(result["lines"]) == 3
        assert "Taken together" in result["summary"]

    def test_sanitization_applied_to_bullets(self):
        replicates = [
            {
                "support_bullets": [
                    "example.com: BrandName: Contains $500 dollar amount",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.5,
            web_block=None,
            replicates=replicates,
        )

        assert len(result["lines"]) == 3
        assert all("example.com" not in line for line in result["lines"])
        assert all("BrandName" not in line for line in result["lines"])
        assert any("a high value" in line for line in result["lines"])

    def test_limits_lines_to_three(self):
        replicates = [
            {"support_bullets": [f"Line {i}" for i in range(1, 10)]}
        ]
        result = compose_simple_expl(
            claim="Generic claim",
            combined_p=0.5,
            web_block=None,
            replicates=replicates,
        )
        assert len(result["lines"]) == 3

    def test_summary_matches_probability_bucket(self):
        assert "likely true" in compose_simple_expl("Claim", 0.8, {}, [])["summary"]
        assert "likely false" in compose_simple_expl("Claim", 0.2, {}, [])["summary"]
        assert "uncertain" in compose_simple_expl("Claim", 0.5, {}, [])["summary"]


class TestComposeDeeperExpl:
    def test_deeper_payload_shapes(self):
        replicates = [
            {
                "support_bullets": ["Construction is underway."],
                "oppose_bullets": ["Permits still pending."],
            }
        ]
        prior_block = {"p": 0.3, "ci95": [0.2, 0.4], "stability": 0.5}
        web_block = {"p": 0.55, "evidence": {"n_docs": 12, "n_domains": 5, "median_age_days": 30}}
        weights = {"w_web": 0.4, "recency": 0.8, "strength": 0.7}

        result = compose_deeper_expl(
            claim="Claim",
            prior_block=prior_block,
            web_block=web_block,
            combined_p=0.45,
            replicates=replicates,
            weights=weights,
            model_label="GPT-5",
        )

        assert result is not None
        assert "prior" in result and "web" in result and "blend" in result
        assert len(result["prior"]["lines"]) > 0
        assert "Construction is underway." in result["web"]["support_lines"][0]
        assert "Permits still pending." in result["web"]["contrary_lines"][0]
        meta = result["web"]["meta"]
        assert meta["docs"] == 12
        assert meta["domains"] == 5
        assert "web evidence" in result["blend"].lower()


class TestComposeBaselineSimpleExpl:
    def test_model_label_injected(self):
        result = compose_baseline_simple_expl(
            claim="Generic topic analysis",
            prior_p=0.65,
            prior_ci=(0.55, 0.72),
            stability_score=0.3,
            template_count=8,
            imbalance_ratio=1.0,
            model_label="Grok 4",
        )
        assert any("Grok 4" in line for line in result["lines"])
        assert result["lines"][0] != result["lines"][1]
        assert result["lines"][1] != result["lines"][2]

    def test_output_structure(self):
        """Should return dict with expected keys."""
        result = compose_simple_expl(
            claim="Test",
            combined_p=0.5,
            web_block=None,
            replicates=[],
        )

        assert isinstance(result, dict)
        assert "title" in result
        assert "lines" in result
        assert "summary" in result
        assert isinstance(result["title"], str)
        assert isinstance(result["lines"], list)
        assert isinstance(result["summary"], str)
