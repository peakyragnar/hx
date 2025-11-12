from __future__ import annotations

import re
from dataclasses import dataclass, field
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


@dataclass
class EvidenceSummary:
    progress: List[str] = field(default_factory=list)
    obstacles: List[str] = field(default_factory=list)
    timeline: List[str] = field(default_factory=list)
    authority: List[str] = field(default_factory=list)
    generic_support: List[str] = field(default_factory=list)
    generic_contrary: List[str] = field(default_factory=list)
    support_count: int = 0
    contrary_count: int = 0

    def add_support(self, sentence: str) -> None:
        self.support_count += 1
        self._route_sentence(sentence, is_support=True)

    def add_contrary(self, sentence: str) -> None:
        self.contrary_count += 1
        self._route_sentence(sentence, is_support=False)

    def _route_sentence(self, sentence: str, *, is_support: bool) -> None:
        bucket = _classify_sentence(sentence)
        target_list = None
        if bucket == "progress":
            target_list = self.progress
        elif bucket == "obstacle":
            target_list = self.obstacles
        elif bucket == "timeline":
            target_list = self.timeline
        elif bucket == "authority":
            target_list = self.authority
        elif is_support:
            target_list = self.generic_support
        else:
            target_list = self.generic_contrary

        if sentence and sentence not in target_list:
            target_list.append(sentence)

    def all_sentences(self) -> List[str]:
        ordered = (
            self.progress
            + self.timeline
            + self.authority
            + self.obstacles
            + self.generic_support
            + self.generic_contrary
        )
        # preserve order but drop duplicates
        seen: set[str] = set()
        unique: List[str] = []
        for sentence in ordered:
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(sentence)
        return unique


PROGRESS_PATTERNS = [
    r"\b(began|begin|started|launched|announced|building|constructed|broke ground|approved|funded|contracted)\b",
    r"\b(commissioned|installed|opened|operational|brought online|coming online)\b",
]

OBSTACLE_PATTERNS = [
    r"\b(no plans|paused|canceled|cancelled|delayed|blocked|suspended|not approved)\b",
    r"\b(shortage|lack|insufficient|bottleneck|backlog|over budget|funding gap)\b",
    r"\b(opposition|lawsuit|challenge|denied|rejected)\b",
]

TIMELINE_PATTERNS = [
    r"\b(by|in|before)\s+(20\d{2}|next year|this year|q[1-4]\s*20\d{2}|mid-\d{2}|late\s+\d{2})\b",
    r"\b(deadline|timeline|schedule|expected|target|phase)\b",
]

AUTHORITY_PATTERNS = [
    r"\b(agency|regulator|commission|authority|officials?|governor|congress|parliament|court|nrc|doe|ferc)\b",
    r"\b(white house|administration|cabinet|ministry|secretary|president|prime minister)\b",
]


def _classify_sentence(sentence: str) -> str:
    text = sentence.lower()
    if any(re.search(pattern, text) for pattern in PROGRESS_PATTERNS):
        return "progress"
    if any(re.search(pattern, text) for pattern in OBSTACLE_PATTERNS):
        return "obstacle"
    if any(re.search(pattern, text) for pattern in TIMELINE_PATTERNS):
        return "timeline"
    if any(re.search(pattern, text) for pattern in AUTHORITY_PATTERNS):
        return "authority"
    return "generic"


def summarize_evidence(replicates: Optional[List[Dict[str, Any]]]) -> EvidenceSummary:
    summary = EvidenceSummary()
    seen_sentences: set[str] = set()

    def _ingest(items: List[str], *, is_support: bool) -> None:
        for raw in items:
            sentence = _sanitize(raw)
            if not sentence:
                continue
            key = sentence.lower()
            if key in seen_sentences:
                continue
            seen_sentences.add(key)
            if is_support:
                summary.add_support(sentence)
            else:
                summary.add_contrary(sentence)

    for rep in replicates or []:
        if not isinstance(rep, dict):
            continue
        support_items = rep.get("support_bullets") or []
        oppose_items = rep.get("oppose_bullets") or []
        notes_items = rep.get("notes") or []
        if isinstance(support_items, list):
            _ingest([str(x) for x in support_items], is_support=True)
        else:
            _ingest([str(support_items)], is_support=True)
        if isinstance(oppose_items, list):
            _ingest([str(x) for x in oppose_items], is_support=False)
        else:
            _ingest([str(oppose_items)], is_support=False)
        if isinstance(notes_items, list):
            # notes can contain contextual clues; treat them as whichever direction dominates support
            dominant_support = summary.support_count >= summary.contrary_count
            _ingest([str(x) for x in notes_items], is_support=dominant_support)

    return summary


@dataclass
class ClaimFrame:
    actor: str
    action: str
    timeframe: Optional[str] = None


TIME_PATTERN = re.compile(r"\b(by|in|before)\s+(20\d{2}|next year|this year|q[1-4]\s*20\d{2}|mid-\d{2}|late\s+\d{2})\b", re.IGNORECASE)


def _frame_claim(claim: str) -> ClaimFrame:
    text = (claim or "").strip()
    if not text:
        return ClaimFrame(actor="The model", action="address the claim")

    verb_pattern = re.compile(
        r"^(?P<actor>[A-Z][^,]+?)\s+(?:will|plans to|aims to|expects to|is set to|is going to|intends to)\s+(?P<action>.+)$",
        re.IGNORECASE,
    )
    match = verb_pattern.match(text)
    actor = "The model"
    action = text
    if match:
        actor = match.group("actor").strip()
        action = match.group("action").strip()
    timeframe = None
    time_match = TIME_PATTERN.search(action) or TIME_PATTERN.search(text)
    if time_match:
        timeframe = time_match.group(0).strip()
        if action.lower().startswith(timeframe.lower()):
            action = action[len(timeframe) :].strip()
        else:
            action = TIME_PATTERN.sub("", action).strip()
    action = action or "deliver on this claim"
    return ClaimFrame(actor=actor, action=action, timeframe=timeframe)


def _build_bar_sentence(frame: ClaimFrame) -> str:
    action_lower = frame.action.lower()
    timeframe = f" {frame.timeframe}" if frame.timeframe else ""
    if any(word in action_lower for word in ("build", "construct", "open", "launch", "plant", "factory", "power plant", "reactor")):
        return f"{frame.actor} would need permits, financing, and construction time to {frame.action}{timeframe}."
    if any(word in action_lower for word in ("approve", "pass", "ban", "legalize", "regulate", "act", "bill")):
        return f"{frame.actor} must navigate formal approvals and votes before {frame.action}{timeframe}."
    if any(word in action_lower for word in ("produce", "reach", "hit", "achieve", "increase", "grow")):
        return f"Hitting that mark requires sustained capacity, supply, and demand alignment for {frame.actor}{timeframe}."
    return f"Delivering on this claim demands coordinated resources and follow-through from {frame.actor}{timeframe}."


def _select_context_lines(summary: Optional[EvidenceSummary], verdict: str, max_lines: int = 2) -> List[str]:
    if summary is None:
        return []
    priorities: List[List[str]]
    if verdict == "likely true":
        priorities = [summary.progress, summary.timeline, summary.authority, summary.obstacles, summary.generic_contrary]
    elif verdict == "likely false":
        priorities = [summary.obstacles, summary.timeline, summary.progress, summary.authority, summary.generic_support]
    else:
        priorities = [summary.timeline, summary.progress, summary.obstacles, summary.authority, summary.generic_support]

    chosen: List[str] = []
    for bucket in priorities:
        for sentence in bucket:
            if sentence and sentence not in chosen:
                chosen.append(sentence)
                if len(chosen) >= max_lines:
                    return chosen
    if len(chosen) < max_lines:
        for sentence in summary.all_sentences():
            if sentence not in chosen:
                chosen.append(sentence)
                if len(chosen) >= max_lines:
                    break
    return chosen[:max_lines]


def _fallback_context_lines(frame: ClaimFrame, verdict: str) -> List[str]:
    actor = frame.actor or "The model"
    base = [
        f"Stakeholders will need to align on funding, expertise, and logistics before {frame.action} is realistic.",
        f"Signals so far are mixed, so {actor} has to prove real progress rather than projections.",
        "Independent confirmation remains limited, so the verdict leans on prudence.",
    ]
    if verdict == "likely true":
        base[1] = f"Existing announcements and early work hint that {frame.action} is underway even if it is unfinished."
    elif verdict == "likely false":
        base[1] = f"Missing approvals and public commitments keep {frame.action} in speculation territory for now."
    return base


def _prior_meta_sentences(prior_p: float, stability_score: float, template_count: Optional[int]) -> List[str]:
    lines: List[str] = []
    if prior_p >= 0.7:
        lines.append("Similar stories in training usually succeed, so the model leans confident before new evidence.")
    elif prior_p <= 0.3:
        lines.append("Most historical references fall apart, so the model starts from a skeptical prior.")
    else:
        lines.append("Training material is split, keeping the prior near the middle until more context arrives.")

    if stability_score >= 0.7:
        lines.append("Different paraphrases agree with each other, suggesting the verdict is steady across wordings.")
    elif stability_score <= 0.4:
        lines.append("Paraphrases disagreed, flagging ambiguity in how the claim can be read.")

    if template_count and len(lines) < 3:
        lines.append(f"{template_count} paraphrases weighed in, so no single wording dominates the prior.")

    return lines[:2]


def compose_simple_expl(
    claim: str,
    combined_p: float,
    web_block: Optional[Dict[str, Any]],
    replicates: Optional[List[Dict[str, Any]]],
    prior_block: Optional[Dict[str, Any]] = None,
    model_label: str = "the model",
    evidence_summary: Optional[EvidenceSummary] = None,
) -> Dict[str, Any]:
    summary = evidence_summary or summarize_evidence(replicates)
    frame = _frame_claim(claim)
    verdict = "likely true" if combined_p >= 0.60 else ("likely false" if combined_p <= 0.40 else "uncertain")

    lines: List[str] = []
    lines.append(_build_bar_sentence(frame))

    context_lines = _select_context_lines(summary, verdict)
    if not context_lines:
        context_lines = _fallback_context_lines(frame, verdict)[:2]
    lines.extend(context_lines)

    if len(lines) < 3:
        remaining = summary.all_sentences() if summary else []
        for sentence in remaining:
            if sentence not in lines:
                lines.append(sentence)
            if len(lines) >= 3:
                break

    if len(lines) < 3:
        for sentence in _fallback_context_lines(frame, verdict):
            if sentence not in lines:
                lines.append(sentence)
            if len(lines) >= 3:
                break

    final_lines = [ln for ln in lines if ln][:3]

    if len(final_lines) < 3 and prior_block:
        try:
            fallback = compose_baseline_simple_expl(
                claim=claim,
                prior_p=float(prior_block.get("p", combined_p)),
                prior_ci=tuple(prior_block.get("ci95", (combined_p, combined_p))),
                stability_score=float(prior_block.get("stability") or 0.0),
                template_count=None,
                imbalance_ratio=None,
                model_label=model_label,
            )
            for candidate in fallback.get("lines", []):
                if candidate not in final_lines:
                    final_lines.append(candidate)
                if len(final_lines) >= 3:
                    break
        except Exception:
            pass
        final_lines = final_lines[:3]

    summary_text = f"Taken together, these points suggest the claim is {verdict}."

    return {
        "title": "Why the web‑informed verdict looks this way",
        "lines": final_lines,
        "summary": summary_text,
    }


def compose_deeper_expl(
    *,
    claim: str,
    prior_block: Optional[Dict[str, Any]],
    web_block: Optional[Dict[str, Any]],
    combined_p: float,
    replicates: Optional[List[Dict[str, Any]]],
    weights: Optional[Dict[str, Any]],
    model_label: str,
    evidence_summary: Optional[EvidenceSummary] = None,
) -> Optional[Dict[str, Any]]:
    if prior_block is None and web_block is None:
        return None

    summary = evidence_summary or summarize_evidence(replicates)
    prior_p = float(prior_block.get("p", combined_p)) if prior_block else combined_p
    prior_ci = tuple(prior_block.get("ci95", (prior_p, prior_p))) if prior_block else (prior_p, prior_p)
    stability_score = float(prior_block.get("stability") or 0.0) if prior_block else 0.0

    baseline = compose_baseline_simple_expl(
        claim=claim,
        prior_p=prior_p,
        prior_ci=prior_ci,
        stability_score=stability_score,
        template_count=None,
        imbalance_ratio=None,
        model_label=model_label,
    )

    support_lines = summary.progress + summary.timeline + summary.authority
    if not support_lines:
        support_lines = summary.generic_support
    support_lines = support_lines[:3]

    contrary_lines = summary.obstacles or summary.generic_contrary
    contrary_lines = contrary_lines[:3]

    evidence_meta: Dict[str, Any] = {}
    if isinstance(web_block, dict):
        evidence = web_block.get("evidence") or {}
        if isinstance(evidence, dict):
            if evidence.get("n_docs") is not None:
                evidence_meta["docs"] = int(evidence.get("n_docs"))
            if evidence.get("n_domains") is not None:
                evidence_meta["domains"] = int(evidence.get("n_domains"))
            if evidence.get("median_age_days") is not None:
                evidence_meta["median_age_days"] = evidence.get("median_age_days")
    evidence_meta["support_snippets"] = summary.support_count
    evidence_meta["contrary_snippets"] = summary.contrary_count

    blend_sentence = _describe_blend(weights, prior_block, web_block, model_label)

    return {
        "prior": {"p": prior_p, "lines": baseline.get("lines", [])[:3]},
        "web": {
            "p": (web_block or {}).get("p"),
            "support_lines": support_lines,
            "contrary_lines": contrary_lines,
            "meta": evidence_meta,
        },
        "blend": blend_sentence,
    }


def _describe_blend(
    weights: Optional[Dict[str, Any]],
    prior_block: Optional[Dict[str, Any]],
    web_block: Optional[Dict[str, Any]],
    model_label: str,
) -> str:
    prior_p = float(prior_block.get("p", 0.0)) if isinstance(prior_block, dict) else 0.0
    web_p = float(web_block.get("p", prior_p)) if isinstance(web_block, dict) and web_block.get("p") is not None else prior_p
    if not weights or "w_web" not in weights:
        return f"We fall back to {model_label}’s training view because web weighting data was unavailable."

    try:
        w = max(0.0, min(1.0, float(weights.get("w_web", 0.0))))
    except (TypeError, ValueError):
        w = 0.0
    weight_pct = int(round(w * 100))
    prior_pct = int(round(prior_p * 100))
    web_pct = int(round(web_p * 100))

    reasons: List[str] = []
    recency = weights.get("recency")
    strength = weights.get("strength")
    if isinstance(recency, (int, float)):
        reasons.append(f"recent sources scored {recency:.2f} on recency")
    if isinstance(strength, (int, float)):
        reasons.append(f"strength scored {strength:.2f}")
    if not reasons:
        reasons.append("web evidence is limited, so the prior still anchors the blend")

    return (
        f"About {weight_pct}% of the verdict comes from web evidence (~{web_pct}%), while the training prior (~{prior_pct}%)"
        f" fills the rest because {', '.join(reasons)}."
    )

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
    model_label: str = "the model",
) -> Dict[str, Any]:
    """Compose Simple View lines for baseline (model-only) runs."""

    claim_low = (claim or "").lower()
    pattern_lines: List[str] = []
    year_m = re.search(r"(20\\d{2})", claim or "")
    pct_m = re.search(r"(\\d{1,3})\\s?%[^\n]*", claim or "")
    year_txt = year_m.group(1) if year_m else None
    pct_txt = pct_m.group(1) if pct_m else None
    label = model_label or "the model"

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
            f"Without agreed criteria, the claim depends on subjective definitions, so {label} stays skeptical.",
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
            f"{label} recalls that demographic swings, migration, and reporting gaps make tidy percentages suspect.",
            "Without archival data, priors view sweeping percentage assertions as more rhetorical than factual.",
        )

    verdict = "likely true" if prior_p >= 0.60 else ("likely false" if prior_p <= 0.40 else "uncertain")
    lines: List[str] = pattern_lines[:3]

    def _generic_lines(direction: str) -> List[str]:
        if direction == "likely true":
            return [
                f"Training data references {topic_phrase} and usually reports outcomes consistent with the claim.",
                f"Historical summaries in the corpus mention similar incentives and mechanisms, so {label} leans toward it being accurate.",
                "Counterexamples exist, but they are outweighed by supporting accounts in its prior knowledge.",
            ]
        if direction == "likely false":
            return [
                f"Many references to {topic_phrase} describe scenarios where the claim breaks down or stays limited.",
                f"Definitions, precedent, and expert commentary in the corpus nudge {label} toward skepticism.",
                "Supporting anecdotes appear, but contradictory evidence dominates the material it has seen.",
            ]
        return [
            f"Examples about {topic_phrase} split between success and failure in {label}’s training data.",
            "Outcomes hinge on missing details or context, so the model keeps the prior near the middle.",
            "Supporting and opposing references appear in roughly equal measure, preventing a decisive verdict.",
        ]

    meta_lines = _prior_meta_sentences(prior_p, stability_score, template_count)

    if not lines:
        lines = _generic_lines(verdict)[:3]
    else:
        lines = lines[:3]

    for meta_line in meta_lines:
        if len(lines) >= 3:
            break
        lines.append(meta_line)

    fallback_reasons = [
        f"{label} compares thousands of historical examples before settling on a prior.",
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
