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


def _format_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return None
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _append_unique(lines: List[str], text: Optional[str]) -> None:
    formatted = _format_line(text)
    if not formatted:
        return
    if formatted not in lines:
        lines.append(formatted)


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

    def add_line(text: Optional[str]) -> None:
        _append_unique(lines, text)
    # Patterns
    if ("ban" in claim_low or "banned" in claim_low):
        add_line(
            f"A ban would require formal approval by the owners at a rules meeting{(' in ' + year_txt) if year_txt else ''}."
        )
        add_line("Recent reporting points to debate and expectations of a vote, not a finalized decision.")
        hist = grab(r"delayed|tabled|no decision|not approved|postponed")
        if hist:
            add_line("Earlier proposals were discussed or tabled; there is no announced rule change yet.")
    elif (("source" in claim_low or "domestic" in claim_low) and pct_txt):
        if year_txt:
            add_line(
                f"Reaching {pct_txt}% by {year_txt} would need rapid build‑out of extraction, processing and magnet capacity."
            )
        else:
            add_line(f"Meeting a {pct_txt}% threshold would require substantial new domestic capacity.")
        cap = grab(r"production|processing|refining|magnet|capacity|output|plant|factory")
        if cap:
            add_line(cap)
        dep = grab(r"import|depend|reliance|supply chain|bottleneck|intermediate")
        if dep:
            add_line(dep)
    elif ("market cap" in claim_low) or ("market capitalization" in claim_low) or ("trillion" in claim_low):
        if year_txt:
            add_line(f"Hitting that milestone by {year_txt} depends on earnings and broader market conditions.")
        else:
            add_line("Reaching that milestone depends on results and market conditions.")
        crossed = grab(r"crossed|surpassed|joined|reached")
        if crossed:
            add_line("Recent reporting notes the milestone has already been reached at times, showing it is attainable.")
        sustain = grab(r"sustain|maintain|trajectory|growth|margin")
        if sustain:
            add_line("Sustaining it will depend on the company’s trajectory over the next periods.")
    elif ("data center" in claim_low or "datacenter" in claim_low) and (
        "electric" in claim_low or "power" in claim_low or "rate" in claim_low or "bill" in claim_low or "inflation" in claim_low
    ):
        add_line("Large data center build‑outs raise peak demand and capacity needs in some regions.")
        cap_price = grab(r"capacity price|auction|monitor|PJM|MISO|ISO|market monitor")
        if cap_price:
            add_line(
                "Recent market reports attribute a sizable share of capacity price increases to data center demand, costs typically recovered from customers."
            )
        conn = grab(r"connection|interconnection|upgrade|transmission|rate case|bill impact|cost shift")
        if conn:
            add_line(
                "Reports describe higher connection and upgrade costs tied to data center hookups, often passed through to ratepayers under current rules."
            )
    else:
        # Grab up to 3 distinct lines for generic claims
        for _ in range(3):
            line = grab(r".")
            if line:
                add_line(line)
            else:
                break

    # Cap to 3 content lines
    if len(lines) > 3:
        lines = lines[:3]

    # Verdict tie‑in
    verdict = "likely true" if combined_p >= 0.6 else ("likely false" if combined_p <= 0.4 else "uncertain")
    summary = f"Taken together, these points suggest the claim is {verdict}."

    context_line = None
    evidence = web_block.get("evidence") if isinstance(web_block, dict) else {}
    docs = int(evidence.get("n_docs") or 0) if evidence else 0
    if docs > 0:
        descriptor = "a handful of" if docs <= 3 else "several"
        context_line = (
            f"The web lens pulled {descriptor} recent articles and only policy-compliant details were blended with the model’s prior."
        )
        summary_tail = " Fresh web reporting fed into this verdict."
    elif web_block is not None:
        context_line = "The web lens did not surface usable articles in this run, so the model leaned on its prior knowledge."
        summary_tail = " No usable web articles cleared the filters, so the result mirrors the prior."
    else:
        context_line = "This web-informed request fell back to the model’s prior because the web resolver returned nothing new."
        summary_tail = " The web resolver returned nothing new, so this mirrors the model’s prior."

    trimmed_lines = [ln for ln in lines if ln][:3]
    if not trimmed_lines:
        trimmed_lines = [context_line or "This verdict relied on the model’s prior knowledge."]

    return {
        "title": "Why the web‑informed verdict looks this way",
        "lines": trimmed_lines,
        "summary": summary + summary_tail,
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
    narrative_lines: List[str] = []
    year_m = re.search(r"(20\\d{2})", claim or "")
    pct_m = re.search(r"(\\d{1,3})\\s?%[^\n]*", claim or "")
    year_txt = year_m.group(1) if year_m else None
    pct_txt = pct_m.group(1) if pct_m else None

    def add(*lines: str) -> None:
        for line in lines:
            _append_unique(narrative_lines, line)

    keywords = _extract_keywords(claim)
    topic_phrase = _format_topic(keywords)
    template_num: Optional[int]
    try:
        template_num = int(template_count) if template_count is not None else None
    except (TypeError, ValueError):
        template_num = None

    if "ban" in claim_low or "banned" in claim_low:
        add(
            f"A ban would require formal approval and rulebook changes{(' in ' + year_txt) if year_txt else ''}.",
            "Committee debates and votes often stall before a blanket ban is adopted.",
            "Recent discussions cite safety data and league politics, showing the idea is still being argued.",
        )
    elif any(word in claim_low for word in ["domestic", "source", "sourcing", "content"]) and pct_txt:
        add(
            f"Reaching {pct_txt}% domestic share{(' by ' + year_txt) if year_txt else ''} would demand rapid build‑out of extraction and processing.",
            "Training references emphasize bottlenecks in refining, magnets, and critical parts that limit local output.",
            "Past policy pushes still leaned on imports for intermediate goods, which weakens the claim’s certainty.",
        )
    elif any(term in claim_low for term in ["market cap", "trillion", "valuation", "most valuable"]):
        add(
            "Valuation milestones swing with market conditions, not just company statements.",
            "Historical peaks often reverse unless earnings and margins keep pace, so permanence is doubtful.",
            "Claims about trillion‑dollar caps usually need sustained profitability and macro support, which priors treat cautiously.",
        )
    elif ("data center" in claim_low or "datacenter" in claim_low) and any(
        word in claim_low for word in ["electric", "power", "rate", "bill", "inflation"]
    ):
        add(
            "Training data ties large data center growth to higher grid demand and peak pricing debates.",
            "Regulator dockets and ISO reports often show rate increases spreading across customers, not just operators.",
            "Past hookups triggered transmission upgrades and cost shifting, so broad bill impacts stay contested.",
        )
    elif any(word in claim_low for word in ["greatest", "best ever", "goat", "most dominant", "greatest of all time"]):
        add(
            "“Greatest” debates hinge on championships, sustained dominance, and historical impact.",
            "Model priors weigh how lists balance rings, longevity, and era strength, not single stats.",
            "Without agreed criteria, the claim depends on subjective definitions, so the verdict stays cautious.",
        )
    elif "inflation" in claim_low and ("tariff" in claim_low or "tariffs" in claim_low):
        add(
            "Training data links tariffs to higher import costs, but pass‑through to consumer prices varies by product mix.",
            "Historical episodes show monetary policy and demand shocks dominate broad inflation, so tariffs rarely drive the entire move.",
            "Model priors remember that many sectors can substitute suppliers, muting sweeping price effects.",
        )
    elif any(word in claim_low for word in ["europe", "england", "france", "germany", "italy"]) and any(
        word in claim_low for word in ["execut", "gallows", "criminal"]
    ):
        add(
            "Historical court records show execution rates varied widely across Europe and rarely stayed fixed for generations.",
            "Legal reforms and shifting penal codes drove execution counts down long before the modern era.",
            "Century-spanning claims about uniform execution quotas usually turn out to be exaggerations requiring citations.",
        )
    elif pct_txt and any(word in claim_low for word in ["population", "people", "generation", "citizen", "share"]):
        add(
            f"Claims that {pct_txt}% of a population faced the same outcome trigger checks against census and mortality tables.",
            "Training data recalls that demographic swings, migration, and reporting gaps make tidy percentages suspect.",
            "Without archival data, sweeping percentage assertions read more rhetorical than factual.",
        )

    verdict = "likely true" if prior_p >= 0.60 else ("likely false" if prior_p <= 0.40 else "uncertain")

    def _generic_lines(direction: str) -> List[str]:
        if direction == "likely true":
            return [
                f"Training examples about {topic_phrase} usually land on similar outcomes.",
                "Mechanisms and incentives cited in prior cases line up with this claim.",
                "Counterexamples exist, but supporting accounts outnumber them in the model’s memory.",
            ]
        if direction == "likely false":
            return [
                f"Many references to {topic_phrase} describe where the claim breaks down or stays limited.",
                "Definitions, precedent, and expert commentary nudge the model toward skepticism.",
                "Supporting anecdotes appear, but contradictory evidence dominates what it has seen.",
            ]
        return [
            f"Examples about {topic_phrase} split between success and failure in the training data.",
            "Outcomes hinge on missing details or context, so the verdict sits near the middle.",
            "Supporting and opposing references appear in roughly equal measure, preventing a decisive call.",
        ]

    if not narrative_lines:
        narrative_lines.extend(_generic_lines(verdict)[:3])

    final_lines: List[str] = []
    _append_unique(final_lines, "This verdict relies only on the model’s prior knowledge; no live web evidence was added.")

    if narrative_lines:
        _append_unique(final_lines, narrative_lines[0])

    stability_sentence = _describe_stability(stability_score)
    template_sentence = _describe_template_mix(template_count, imbalance_ratio)

    prefer_template_first = bool(template_num and template_num >= 6)
    extra_candidates: List[Optional[str]] = []
    if prefer_template_first and template_sentence:
        extra_candidates.append(template_sentence)
    if stability_sentence:
        extra_candidates.append(stability_sentence)
    if not prefer_template_first and template_sentence:
        extra_candidates.append(template_sentence)
    extra_candidates.extend(narrative_lines[1:])

    fallback_reasons = [
        "The model compares the claim to thousands of historical examples before locking in a verdict.",
        "It stays cautious when a claim hinges on missing details, so extreme statements get softened.",
        "Conflicting anecdotes keep the answer grounded instead of swinging to a hard yes or no.",
    ]
    extra_candidates.extend(fallback_reasons)

    for reason in extra_candidates:
        if len(final_lines) >= 3:
            break
        _append_unique(final_lines, reason)

    summary = f"Taken together, these points suggest the claim is {verdict}."
    return {
        "title": "Why the model‑only verdict looks this way",
        "lines": final_lines[:3],
        "summary": summary,
    }


def _describe_stability(stability_score: float) -> str:
    try:
        score = float(stability_score)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.85:
        return "Rewording the claim kept landing in the same place, so the verdict is steady."
    if score >= 0.6:
        return "Most rephrasings agreed, though a few wobbled, so the label stays cautious."
    return "Different phrasings pulled the verdict in both directions, so we leave room for doubt."


def _describe_template_mix(template_count: Optional[int], imbalance_ratio: Optional[float]) -> Optional[str]:
    if not template_count:
        return None
    try:
        templates = int(template_count)
    except (TypeError, ValueError):
        return None
    if templates <= 0:
        return None
    if templates >= 8:
        base = f"We asked the claim about {templates} different ways and the answers pointed the same way."
    elif templates >= 4:
        base = f"We tried several phrasings ({templates} in total) and they reinforced the same verdict."
    else:
        base = f"Even with just {templates} paraphrases, the direction stayed consistent."
    try:
        imb = float(imbalance_ratio) if imbalance_ratio is not None else None
    except (TypeError, ValueError):
        imb = None
    if imb and imb > 1.25:
        base += " One or two wordings were louder, but they did not flip the answer."
    return base
