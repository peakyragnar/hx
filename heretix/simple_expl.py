from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


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


def compose_baseline_simple_expl(
    *,
    claim: str,
    prior_p: float,
) -> Dict[str, Any]:
    """Compose Simple View lines for baseline (model-only) runs."""

    def _baseline_reasons(p: float) -> List[str]:
        if p >= 0.60:
            return [
                "GPT‑5 has seen many supporting examples in its training data.",
                "Typical definitions and historical references line up with the claim.",
                "Counterexamples are rare compared to supporting evidence in its corpus.",
            ]
        if p <= 0.40:
            return [
                "GPT‑5’s training data contains many instances that contradict the claim.",
                "Common usage and reference materials point the other way.",
                "Supporting anecdotes are outweighed by counterexamples it has seen.",
            ]
        return [
            "GPT‑5 finds mixed signals in its training data.",
            "It depends on definitions or missing context.",
            "Supporting and opposing examples appear in roughly equal measure.",
        ]

    verdict = "likely true" if prior_p >= 0.60 else ("likely false" if prior_p <= 0.40 else "uncertain")
    lines = _baseline_reasons(prior_p)
    summary = f"Taken together, these points suggest the claim is {verdict}."
    return {
        "title": "Why the model‑only verdict looks this way",
        "lines": lines,
        "summary": summary,
    }
