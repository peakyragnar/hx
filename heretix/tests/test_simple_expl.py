from __future__ import annotations

import pytest
from heretix.simple_expl import compose_simple_expl, _sanitize


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
    """Test the compose_simple_expl function for generating explanations."""

    def test_generic_claim_with_replicates(self):
        """Generic claim should extract up to 3 distinct lines."""
        replicates = [
            {
                "support_bullets": [
                    "First piece of evidence.",
                    "Second piece of evidence.",
                    "Third piece of evidence.",
                ]
            },
            {
                "support_bullets": [
                    "Fourth piece of evidence.",
                    "Fifth piece of evidence.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="The company will expand operations",
            combined_p=0.55,
            web_block=None,
            replicates=replicates,
        )

        assert result["title"] == "Why the web‑informed verdict looks this way"
        assert isinstance(result["lines"], list)
        assert 1 <= len(result["lines"]) <= 3
        assert result["summary"] == "Taken together, these points suggest the claim is uncertain."
        # Should get 3 distinct lines
        assert len(result["lines"]) == 3
        assert result["lines"][0] == "First piece of evidence."
        assert result["lines"][1] == "Second piece of evidence."
        assert result["lines"][2] == "Third piece of evidence."

    def test_generic_claim_fewer_than_3_bullets(self):
        """Should handle when fewer than 3 bullets available."""
        replicates = [
            {
                "support_bullets": [
                    "Only one piece of evidence.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="Some claim",
            combined_p=0.5,
            web_block=None,
            replicates=replicates,
        )

        assert len(result["lines"]) == 1
        assert result["lines"][0] == "Only one piece of evidence."

    def test_ban_claim_pattern(self):
        """Ban claims should use pattern-aware narrative."""
        replicates = [
            {
                "support_bullets": [
                    "Proposal was delayed at the meeting.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="The NFL will ban guardian caps in 2025",
            combined_p=0.25,
            web_block=None,
            replicates=replicates,
        )

        assert len(result["lines"]) == 3
        assert "ban would require formal approval" in result["lines"][0]
        assert "in 2025" in result["lines"][0]
        assert "Recent reporting points to debate" in result["lines"][1]
        assert "Earlier proposals were discussed or tabled" in result["lines"][2]
        assert result["summary"] == "Taken together, these points suggest the claim is likely false."

    def test_domestic_percent_claim_pattern(self):
        """Domestic % claims should use pattern-aware narrative."""
        replicates = [
            {
                "support_bullets": [
                    "Production capacity is limited.",
                    "Import dependency remains high.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="The US will source 50% of rare earth elements domestically by 2026",
            combined_p=0.35,
            web_block=None,
            replicates=replicates,
        )

        assert len(result["lines"]) == 3
        assert "Reaching 50% by 2026" in result["lines"][0]
        assert "Production capacity is limited" in result["lines"][1]
        assert "Import dependency remains high" in result["lines"][2]

    def test_market_cap_claim_pattern(self):
        """Market cap claims should use pattern-aware narrative."""
        replicates = [
            {
                "support_bullets": [
                    "Company crossed the milestone recently.",
                    "Sustaining growth depends on margins.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="Apple will reach $4 trillion market cap by 2025",
            combined_p=0.65,
            web_block=None,
            replicates=replicates,
        )

        assert len(result["lines"]) == 3
        assert "Hitting that milestone by 2025" in result["lines"][0]
        # The pattern produces a standard message when it finds "crossed" in bullets
        assert "milestone has already been reached" in result["lines"][1]
        assert "Sustaining" in result["lines"][2]

    def test_datacenter_electricity_claim_pattern(self):
        """Datacenter electricity claims should use pattern-aware narrative."""
        replicates = [
            {
                "support_bullets": [
                    "Capacity price auctions show increases.",
                    "Interconnection costs are rising.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="Data center electricity demand will raise power bills",
            combined_p=0.7,
            web_block=None,
            replicates=replicates,
        )

        assert len(result["lines"]) == 3
        assert "data center build‑outs" in result["lines"][0]
        assert "capacity price" in result["lines"][1].lower()
        assert "connection" in result["lines"][2].lower()

    def test_verdict_tie_in_likely_true(self):
        """Should produce 'likely true' verdict for p >= 0.6."""
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.75,
            web_block=None,
            replicates=[],
        )
        assert "likely true" in result["summary"]

    def test_verdict_tie_in_likely_false(self):
        """Should produce 'likely false' verdict for p <= 0.4."""
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.25,
            web_block=None,
            replicates=[],
        )
        assert "likely false" in result["summary"]

    def test_verdict_tie_in_uncertain(self):
        """Should produce 'uncertain' verdict for 0.4 < p < 0.6."""
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.5,
            web_block=None,
            replicates=[],
        )
        assert "uncertain" in result["summary"]

    def test_empty_replicates(self):
        """Should handle empty replicates gracefully."""
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.5,
            web_block=None,
            replicates=[],
        )

        assert result["title"] == "Why the web‑informed verdict looks this way"
        assert isinstance(result["lines"], list)
        assert len(result["lines"]) == 0
        assert result["summary"] == "Taken together, these points suggest the claim is uncertain."

    def test_none_replicates(self):
        """Should handle None replicates gracefully."""
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.5,
            web_block=None,
            replicates=None,
        )

        assert result["title"] == "Why the web‑informed verdict looks this way"
        assert isinstance(result["lines"], list)
        assert result["summary"] == "Taken together, these points suggest the claim is uncertain."

    def test_malformed_replicate_missing_bullets(self):
        """Should handle replicates without support_bullets key."""
        replicates = [
            {},  # Missing support_bullets
            {"support_bullets": ["Valid bullet."]},
        ]
        result = compose_simple_expl(
            claim="Test claim",
            combined_p=0.5,
            web_block=None,
            replicates=replicates,
        )

        assert isinstance(result["lines"], list)
        assert len(result["lines"]) == 1
        assert result["lines"][0] == "Valid bullet."

    def test_sanitization_applied_to_bullets(self):
        """Should sanitize bullets during extraction."""
        replicates = [
            {
                "support_bullets": [
                    "example.com: Content with domain prefix",
                    "BrandName: Content with brand prefix",
                    "Contains $500 dollar amount",
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
        assert "example.com" not in result["lines"][0]
        assert "Content with domain prefix" in result["lines"][0]
        assert "BrandName" not in result["lines"][1]
        assert "$500" not in result["lines"][2]
        assert "a high value" in result["lines"][2]

    def test_caps_lines_to_3_max(self):
        """Should cap content lines to 3 maximum."""
        replicates = [
            {
                "support_bullets": [
                    "Line 1",
                    "Line 2",
                    "Line 3",
                    "Line 4",
                    "Line 5",
                    "Line 6",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="Generic claim",
            combined_p=0.5,
            web_block=None,
            replicates=replicates,
        )

        # Should have exactly 3 content lines (capped)
        assert len(result["lines"]) == 3

    def test_stateful_grab_avoids_duplicates(self):
        """Should extract distinct bullets, not duplicates."""
        replicates = [
            {
                "support_bullets": [
                    "First unique bullet.",
                    "Second unique bullet.",
                    "Third unique bullet.",
                ]
            },
        ]
        result = compose_simple_expl(
            claim="Generic claim",
            combined_p=0.5,
            web_block=None,
            replicates=replicates,
        )

        # All lines should be unique
        assert len(result["lines"]) == len(set(result["lines"]))
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
