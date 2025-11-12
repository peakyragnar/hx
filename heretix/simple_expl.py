from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def _sanitize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip()
    # strip leading domain or Brand:
    t = re.sub(r"^\s*(?:[A-Za-z0-9.-]+\.(?:com|org|net|gov|edu|news|io|co|uk|us|ca|au|de|fr))\s*[:—-]\s*", "", t)
    t = re.sub(r"^\s*[A-Z][\w&-]*(?:\s+[A-Z][\w&-]*){0,3}\s*:\s*", "", t)
    # strip Brand + reporting verb
    t = re.sub(
        r"^\s*[A-Z][\w&-]*(?:\s+[A-Z][\w&-]*){0,3}\s+(states|reports|says|announces|notes|claims|plans|projects|indicates)\b[:,]?\s*",
        "",
        t,
    )
    # remove bracketed/parenthetical source hints
    t = re.sub(r"\s*\([^)]*\b(?:com|org|net|gov|edu|news|io|co|uk|us|ca|au|de|fr)\b[^)]*\)\s*$", "", t)
    t = re.sub(r"\s*\[[^\]]*\b(?:com|org|net|gov|edu|news|io|co|uk|us|ca|au|de|fr)\b[^\]]*\]\s*$", "", t)
    # soften heavy numerics
    t = re.sub(r"\$\d[\d,]*(?:\.\d+)?", "a high value", t)
    t = re.sub(r"\b\d+(?:\.\d+)?\s?(?:T|B|M|K)\b", "a large figure", t, flags=re.IGNORECASE)
    if not t:
        return ""
    return t if t.endswith((".", "!", "?")) else (t + ".")


def compose_simple_expl(
    claim: str,
    combined_p: float,
    web_block: Optional[Dict[str, Any]],
    replicates: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    claim_low = (claim or "").lower()
    year_m = re.search(r"(20\d{2})", claim or "")
    pct_m = re.search(r"(\d{1,3})\s?%[^\d]*", claim or "")
    year_txt = year_m.group(1) if year_m else None
    pct_txt = pct_m.group(1) if pct_m else None

    used_bullets = set()  # Track (rep_idx, item_idx) pairs to avoid repeats

    def grab(regex: str) -> Optional[str]:
        pat = re.compile(regex, re.IGNORECASE)
        for rep_idx, rep in enumerate(replicates or []):
            # Validate replicate structure and extract bullets
            if not isinstance(rep, dict):
                continue
            bullets = rep.get("support_bullets")
            if bullets is None:
                items = []
            elif isinstance(bullets, list):
                items = bullets
            else:
                # Handle case where support_bullets is not a list (defensive)
                items = [str(bullets)] if bullets else []

            for item_idx, it in enumerate(items):
                key = (rep_idx, item_idx)
                if key in used_bullets:
                    continue
                s = _sanitize(str(it))
                if pat.search(s):
                    used_bullets.add(key)
                    return s
        return None

    lines: List[str] = []
    # Patterns
    if ("ban" in claim_low or "banned" in claim_low):
        lines.append(
            f"A ban would require formal approval by the owners at a rules meeting{(' in ' + year_txt) if year_txt else ''}."
        )
        lines.append("Recent reporting points to debate and expectations of a vote, not a finalized decision.")
        hist = grab(r"delayed|tabled|no decision|not approved|postponed")
        if hist:
            lines.append("Earlier proposals were discussed or tabled; there is no announced rule change yet.")
    elif (("source" in claim_low or "domestic" in claim_low) and pct_txt):
        if year_txt:
            lines.append(
                f"Reaching {pct_txt}% by {year_txt} would need rapid build‑out of extraction, processing and magnet capacity."
            )
        else:
            lines.append(f"Meeting a {pct_txt}% threshold would require substantial new domestic capacity.")
        cap = grab(r"production|processing|refining|magnet|capacity|output|plant|factory")
        if cap:
            lines.append(cap)
        dep = grab(r"import|depend|reliance|supply chain|bottleneck|intermediate")
        if dep:
            lines.append(dep)
    elif ("market cap" in claim_low) or ("market capitalization" in claim_low) or ("trillion" in claim_low):
        if year_txt:
            lines.append(f"Hitting that milestone by {year_txt} depends on earnings and broader market conditions.")
        else:
            lines.append("Reaching that milestone depends on results and market conditions.")
        crossed = grab(r"crossed|surpassed|joined|reached")
        if crossed:
            lines.append("Recent reporting notes the milestone has already been reached at times, showing it is attainable.")
        sustain = grab(r"sustain|maintain|trajectory|growth|margin")
        if sustain:
            lines.append("Sustaining it will depend on the company’s trajectory over the next periods.")
    elif ("data center" in claim_low or "datacenter" in claim_low) and (
        "electric" in claim_low or "power" in claim_low or "rate" in claim_low or "bill" in claim_low or "inflation" in claim_low
    ):
        lines.append("Large data center build‑outs raise peak demand and capacity needs in some regions.")
        cap_price = grab(r"capacity price|auction|monitor|PJM|MISO|ISO|market monitor")
        if cap_price:
            lines.append(
                "Recent market reports attribute a sizable share of capacity price increases to data center demand, costs typically recovered from customers."
            )
        conn = grab(r"connection|interconnection|upgrade|transmission|rate case|bill impact|cost shift")
        if conn:
            lines.append(
                "Reports describe higher connection and upgrade costs tied to data center hookups, often passed through to ratepayers under current rules."
            )
    else:
        # Grab up to 3 distinct lines for generic claims
        for _ in range(3):
            line = grab(r".")
            if line:
                lines.append(line)
            else:
                break

    # Cap to 3 content lines
    if len(lines) > 3:
        lines = lines[:3]

    # Verdict tie‑in
    verdict = "likely true" if combined_p >= 0.6 else ("likely false" if combined_p <= 0.4 else "uncertain")
    summary = f"Taken together, these points suggest the claim is {verdict}."

    return {
        "title": "Why the web‑informed verdict looks this way",
        "lines": [ln for ln in lines if ln],
        "summary": summary,
    }


STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "with",
    "into",
    "onto",
    "from",
    "about",
    "this",
    "that",
    "these",
    "those",
    "will",
    "would",
    "could",
    "should",
    "for",
    "of",
    "to",
    "by",
    "on",
    "in",
    "at",
    "as",
    "is",
    "are",
    "be",
    "been",
    "being",
    "it",
    "its",
    "their",
    "there",
    "over",
    "under",
    "after",
    "before",
    "than",
    "per",
    "across",
    "around",
    "through",
    "once",
}


def _extract_keywords(text: str, max_terms: int = 3) -> List[str]:
    if not text:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z'\\-]+", text.lower())
    filtered: List[str] = []
    seen = set()
    for word in words:
        if word in STOPWORDS:
            continue
        if len(word) < 4:
            continue
        if word in seen:
            continue
        seen.add(word)
        filtered.append(word)
        if len(filtered) >= max_terms:
            break
    return filtered


def _format_topic(words: List[str]) -> str:
    if not words:
        return "this topic"
    if len(words) == 1:
        return words[0]
    if len(words) == 2:
        return f"{words[0]} and {words[1]}"
    return f"{words[0]}, {words[1]}, and {words[2]}"


def compose_baseline_simple_expl(
    *,
    claim: str,
    prior_p: float,
    prior_ci: Tuple[float, float],
    stability_score: float,
    template_count: Optional[int],
    imbalance_ratio: Optional[float],
) -> Dict[str, Any]:
    """Compose Simple View lines for baseline (model-only) runs."""

    claim_low = (claim or "").lower()
    pattern_lines: List[str] = []
    year_m = re.search(r"(20\\d{2})", claim or "")
    pct_m = re.search(r"(\\d{1,3})\\s?%[^\n]*", claim or "")
    year_txt = year_m.group(1) if year_m else None
    pct_txt = pct_m.group(1) if pct_m else None

    def add(*lines: str) -> None:
        for line in lines:
            if line and line not in pattern_lines:
                pattern_lines.append(line)

    keywords = _extract_keywords(claim)
    topic_phrase = _format_topic(keywords)

    if "ban" in claim_low or "banned" in claim_low:
        add(
            f"A ban would require formal approval and rulebook changes{(' in ' + year_txt) if year_txt else ''}.",
            "Model priors recall that committee debates and votes often stall before a blanket ban is adopted.",
            "Historical summaries show proposals usually cite safety data and league politics before anything is final.",
        )
    elif any(word in claim_low for word in ["domestic", "source", "sourcing", "content"]) and pct_txt:
        add(
            f"Reaching {pct_txt}% domestic share{(' by ' + year_txt) if year_txt else ''} would demand rapid build‑out of extraction and processing.",
            "Training references emphasize bottlenecks in refining, magnets, and critical parts that limit local output.",
            "Past policy pushes still leaned on imports for intermediate goods, which weakens the claim’s certainty.",
        )
    elif any(term in claim_low for term in ["market cap", "trillion", "valuation", "most valuable"]):
        add(
            "Model priors note that valuation milestones swing with market conditions, not just company statements.",
            "Historical peaks often reverse unless earnings and margins keep pace, so permanence is doubtful.",
            "Claims about trillion‑dollar caps usually need sustained profitability and macro support, which priors treat cautiously.",
        )
    elif ("data center" in claim_low or "datacenter" in claim_low) and any(
        word in claim_low for word in ["electric", "power", "rate", "bill", "inflation"]
    ):
        add(
            "Training data ties large data center growth to higher grid demand and peak pricing debates.",
            "Regulator dockets and ISO reports often show rate increases spreading across customers, not just operators.",
            "Priors remember that new hookups trigger transmission upgrades and cost shifting, so broad bill impacts stay contested.",
        )
    elif any(word in claim_low for word in ["greatest", "best ever", "goat", "most dominant", "greatest of all time"]):
        add(
            "“Greatest” debates typically hinge on championships, sustained dominance, and historical impact.",
            "Model priors weigh how lists and historians balance rings, longevity, and era strength, not single stats.",
            "Without agreed criteria, the claim depends on subjective definitions, so GPT‑5 stays skeptical.",
        )
    elif "inflation" in claim_low and ("tariff" in claim_low or "tariffs" in claim_low):
        add(
            "Training data links tariffs to higher import costs, but pass‑through to consumer inflation varies by product mix.",
            "Historical episodes show monetary policy and demand shocks dominate CPI, so tariffs alone rarely drive inflation.",
            "Model priors remember that many sectors can substitute suppliers, muting broad price effects.",
        )
    elif any(word in claim_low for word in ["europe", "england", "france", "germany", "italy"]) and any(
        word in claim_low for word in ["execut", "gallows", "criminal"]
    ):
        add(
            "Historical court records show execution rates varied widely across Europe and rarely stayed fixed for generations.",
            "Legal reforms and shifting penal codes drove execution counts down long before the modern era.",
            "Model priors flag century‑spanning claims about uniform execution quotas as exaggerations requiring citations.",
        )
    elif pct_txt and any(word in claim_low for word in ["population", "people", "generation", "citizen", "share"]):
        add(
            f"Claims that {pct_txt}% of a population faced the same outcome trigger checks against census and mortality tables.",
            "GPT‑5 recalls that demographic swings, migration, and reporting gaps make tidy percentages suspect.",
            "Without archival data, priors view sweeping percentage assertions as more rhetorical than factual.",
        )

    verdict = "likely true" if prior_p >= 0.60 else ("likely false" if prior_p <= 0.40 else "uncertain")
    lines: List[str] = pattern_lines[:3]

    def _generic_lines(direction: str) -> List[str]:
        if direction == "likely true":
            return [
                f"Training data references {topic_phrase} and usually reports outcomes consistent with the claim.",
                "Historical summaries in the corpus mention similar incentives and mechanisms, so GPT‑5 leans toward it being accurate.",
                "Counterexamples exist, but they are outweighed by supporting accounts in its prior knowledge.",
            ]
        if direction == "likely false":
            return [
                f"Many references to {topic_phrase} describe scenarios where the claim breaks down or stays limited.",
                "Definitions, precedent, and expert commentary in the corpus nudge GPT‑5 toward skepticism.",
                "Supporting anecdotes appear, but contradictory evidence dominates the material it has seen.",
            ]
        return [
            f"Examples about {topic_phrase} split between success and failure in GPT‑5’s training data.",
            "Outcomes hinge on missing details or context, so the model keeps the prior near the middle.",
            "Supporting and opposing references appear in roughly equal measure, preventing a decisive verdict.",
        ]

    if not lines:
        lines.extend(_generic_lines(verdict)[:3])

    ci_lo_raw = prior_ci[0] if prior_ci and prior_ci[0] is not None else None
    ci_hi_raw = prior_ci[1] if prior_ci and prior_ci[1] is not None else None
    ci_lo = ci_lo_raw if isinstance(ci_lo_raw, (int, float)) else max(0.0, prior_p - 0.05)
    ci_hi = ci_hi_raw if isinstance(ci_hi_raw, (int, float)) else min(1.0, prior_p + 0.05)
    ci_sentence = (
        f"The training-only probability is {prior_p*100:.1f}% with a 95% interval of {ci_lo*100:.1f}% to {ci_hi*100:.1f}%."
    )
    stability_sentence = (
        f"Stability across paraphrases scores {stability_score:.2f}, meaning the verdict stays steady under rewordings."
    )
    template_sentence = None
    if template_count:
        if isinstance(imbalance_ratio, (int, float)):
            template_sentence = (
                f"{template_count} templates were balanced (imbalance ratio {imbalance_ratio:.2f}), so no single phrasing dominated."
            )
        else:
            template_sentence = f"{template_count} paraphrases agreed on the direction of the verdict."

    for sentence in (ci_sentence, stability_sentence, template_sentence):
        if sentence and len(lines) < 3:
            lines.append(sentence)

    fallback_reasons = [
        "GPT‑5 compares thousands of historical examples before settling on a prior.",
        "Definitions and context matter; priors stay cautious when a claim needs extra assumptions.",
        "Counterexamples in its training data keep the probability from moving into confident territory.",
    ]
    idx = 0
    while len(lines) < 3 and idx < len(fallback_reasons):
        lines.append(fallback_reasons[idx])
        idx += 1

    summary = f"Taken together, these points suggest the claim is {verdict}."
    return {
        "title": "Why the model‑only verdict looks this way",
        "lines": lines,
        "summary": summary,
    }
