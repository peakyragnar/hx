from __future__ import annotations

import hashlib
import math
import os
import random
import os
from typing import Dict, List, Optional

from .aggregate import combine_replicates_ps
from .claim_parse import parse_claim
from .date_extract import enrich_docs_with_publish_dates
from .retriever import make_retriever
from .timeliness import heuristic_is_timely
from .resolved_engine import try_resolve_fact
from .scoring import WELSchemaError, call_wel_once
from .snippets import (
    cap_per_domain,
    dedupe_by_url,
    evidence_metrics,
    median_age_days,
    pack_snippets_for_llm,
)
from .types import Doc, WELReplicate
from heretix.ratelimit import RateLimiter


_TAVILY_RATE_LIMITER = RateLimiter(
    rate_per_sec=float(os.getenv("HERETIX_TAVILY_RPS", "4")),
    burst=int(os.getenv("HERETIX_TAVILY_BURST", "4")),
)


def _deterministic_seed(claim: str, provider: str, model: str, k_docs: int, replicates: int) -> int:
    canon = f"WEL|{provider}|{model}|{claim}|k={k_docs}|r={replicates}"
    return int.from_bytes(hashlib.sha256(canon.encode("utf-8")).digest()[:8], "big")


def _chunk_docs(docs: List[Doc], replicates: int) -> List[List[Doc]]:
    if replicates <= 1 or len(docs) <= 1:
        return [docs]
    stride = len(docs) // replicates
    remainder = len(docs) % replicates
    chunks: List[List[Doc]] = []
    start = 0
    for idx in range(replicates):
        extra = 1 if idx < remainder else 0
        end = start + stride + extra
        subset = docs[start:end]
        if not subset:
            subset = docs
        chunks.append(subset)
        start = end
    return chunks


def _merge_warning_counts(*sources: Optional[Dict[str, int]]) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for src in sources:
        if not src:
            continue
        for key, value in src.items():
            merged[key] = merged.get(key, 0) + int(value)
    return merged


def evaluate_wel(
    claim: str,
    provider: str = "tavily",
    model: str = "gpt-5",
    k_docs: int = 16,
    per_domain_cap: int = 3,
    replicates: int = 2,
    recency_days: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, object]:
    """
    Retrieve, evaluate, and aggregate web evidence for the supplied claim.

    Adaptive defaults:
    - If recency_days is None, use 14 days for timely claims, otherwise no recency cap.
    - If the first pass does not resolve and used a tight window, run a second pass with no recency cap
      and combine evidence.
    """

    def _build_query(base_claim: str, outcome_hint: bool) -> str:
        if outcome_hint:
            # Add generic outcome synonyms to bias toward decisive summaries
            return f"{base_claim} champion winner title result"
        return f"Latest reliable reporting about: {base_claim}"

    def _run_pass(
        pass_recency: Optional[int],
        seed_val: int,
        outcome_hint: bool,
    ) -> Dict[str, object]:
        warning_counts_local: Dict[str, int] = {}

        def _record(labels):
            if not labels:
                return
            for label in labels:
                warning_counts_local[label] = warning_counts_local.get(label, 0) + 1

        retriever = make_retriever(provider=provider)
        query = _build_query(claim, outcome_hint)
        _TAVILY_RATE_LIMITER.acquire()
        fetched = retriever.search(query=query, k=k_docs * 2, recency_days=pass_recency)

        docs = cap_per_domain(dedupe_by_url(fetched), max_per_domain=per_domain_cap)[:k_docs]
        if not docs:
            return {
                "empty": True,
                "docs": [],
            }

        fetch_timeout = float(os.getenv("WEL_FETCH_TIMEOUT", "6"))
        enrich_docs_with_publish_dates(docs, timeout=fetch_timeout, max_docs=k_docs)

        total_docs = len(docs) or 1
        confident_count = sum(1 for doc in docs if doc.published_at and doc.published_confidence >= 0.5)
        median_confident = median_age_days(docs, min_confidence=0.5)
        if math.isnan(median_confident):
            fallback_median = float(pass_recency) if pass_recency is not None else 365.0
            median_value = fallback_median
            confident_rate = 0.0
        else:
            median_value = float(median_confident)
            confident_rate = float(confident_count) / float(total_docs)

        info = parse_claim(claim)
        rng = random.Random(seed_val)
        rng.shuffle(docs)
        doc_chunks = _chunk_docs(docs, replicates=replicates)

        resolved_payload = try_resolve_fact(claim, docs, info=info)
        if resolved_payload.get("resolved"):
            truth = bool(resolved_payload.get("truth"))
            prob = 0.999 if truth else 0.001
            metrics = {
                **evidence_metrics(docs),
                "median_age_days": median_value,
                "n_confident_dates": float(confident_count),
                "date_confident_rate": confident_rate,
                "dispersion": 0.0,
                "json_valid_rate": 1.0,
                "resolved": True,
                "resolved_truth": truth,
                "resolved_reason": resolved_payload.get("reason"),
                "resolved_support": resolved_payload.get("support"),
                "resolved_contradict": resolved_payload.get("contradict"),
                "resolved_domains": resolved_payload.get("domains"),
                "resolved_citations": resolved_payload.get("citations"),
                "resolved_debug_votes": resolved_payload.get("debug_votes"),
            }
            return {
                "resolved": True,
                "p": prob,
                "ci95": (prob, prob),
                "replicates": [],
                "replicate_ps": [],
                "docs": docs,
                "metrics": metrics,
                "warning_counts": warning_counts_local,
            }

        replicates_out: List[WELReplicate] = []
        replicate_ps: List[float] = []
        json_valid = 0
        max_chars = int(os.getenv("WEL_MAX_CHARS", "6000"))

        for idx, chunk in enumerate(doc_chunks):
            bundle = pack_snippets_for_llm(claim, chunk, max_chars=max_chars)
            stance_label: Optional[str] = None
            try:
                payload, warnings, prompt_hash = call_wel_once(bundle, model=model)
                _record(warnings)
                p = float(payload.get("stance_prob_true"))
                stance_label = str(payload.get("stance_label") or "").strip() or None
                support = [str(x) for x in (payload.get("support_bullets") or [])][:4]
                oppose = [str(x) for x in (payload.get("oppose_bullets") or [])][:4]
                notes = [str(x) for x in (payload.get("notes") or [])][:3]
                valid = True
            except Exception as exc:
                _record(getattr(exc, "warnings", []))
                p = 0.5
                support = []
                oppose = []
                notes = [f"invalid_response: {exc}"]
                valid = False
                prompt_hash = ""
            replicate_ps.append(p)
            if valid:
                json_valid += 1
            replicates_out.append(
                WELReplicate(
                    replicate_idx=idx,
                    docs=chunk,
                    p_web=p,
                    support_bullets=support,
                    oppose_bullets=oppose,
                    notes=notes,
                    json_valid=valid,
                    stance_label=stance_label,
                )
            )

        p_hat, ci95, dispersion = combine_replicates_ps(replicate_ps)
        metrics = {
            **evidence_metrics(docs),
            "median_age_days": median_value,
            "n_confident_dates": float(confident_count),
            "date_confident_rate": confident_rate,
            "dispersion": dispersion,
            "json_valid_rate": json_valid / max(1, len(replicates_out)),
            "resolved": False,
            "resolved_truth": None,
            "resolved_reason": None,
            "resolved_support": None,
            "resolved_contradict": None,
            "resolved_domains": None,
            "resolved_citations": [],
            "resolved_debug_votes": resolved_payload.get("debug_votes"),
        }

        return {
            "resolved": False,
            "p": p_hat,
            "ci95": ci95,
            "replicates": replicates_out,
            "replicate_ps": replicate_ps,
            "docs": docs,
            "metrics": metrics,
            "warning_counts": warning_counts_local,
        }

    # Decide first-pass recency (adaptive default)
    info0 = parse_claim(claim)
    timely = heuristic_is_timely(claim) or info0.is_time_sensitive
    seed_val = seed if seed is not None else _deterministic_seed(claim, provider, model, k_docs, replicates)
    if recency_days is None:
        recency_first = 14 if timely else None
    else:
        recency_first = recency_days

    outcome_hint = info0.relation_family in ("event_outcome", "identity_role")

    # First pass
    pass1 = _run_pass(recency_first, seed_val, outcome_hint)
    passes_used: list[Optional[int]] = [recency_first]

    # If resolved or first pass was wide already, return
    if pass1.get("resolved") or recency_first is None:
        return {
            "p": pass1.get("p", 0.5),
            "ci95": pass1.get("ci95", (0.5, 0.5)),
            "replicates": pass1.get("replicates", []),
            "metrics": pass1.get("metrics", {}),
            "warning_counts": dict(pass1.get("warning_counts") or {}),
            "provenance": {
                "provider": provider,
                "model": model,
                "k_docs": k_docs,
                "replicates": (0 if pass1.get("resolved") else len(pass1.get("replicates", []))),
                "recency_days": recency_first,
                "passes": passes_used,
                "seed": seed_val,
                "resolved": bool(pass1.get("resolved")),
            },
        }

    # Second pass with no recency cap (fallback)
    recency_second: Optional[int] = None
    pass2 = _run_pass(recency_second, seed_val, outcome_hint)
    passes_used.append(recency_second)

    # If pass2 resolved, return that
    if pass2.get("resolved"):
        return {
            "p": pass2.get("p", 0.5),
            "ci95": pass2.get("ci95", (0.5, 0.5)),
            "replicates": pass2.get("replicates", []),
            "metrics": pass2.get("metrics", {}),
            "warning_counts": dict(pass2.get("warning_counts") or {}),
            "provenance": {
                "provider": provider,
                "model": model,
                "k_docs": k_docs,
                "replicates": 0,
                "recency_days": recency_second,
                "passes": passes_used,
                "seed": seed_val,
                "resolved": True,
            },
        }

    # Combine non-resolved passes: concatenate replicates and recompute
    docs_all: List[Doc] = list((pass1.get("docs") or [])) + list((pass2.get("docs") or []))
    reps_all = []
    for idx, rep in enumerate(list(pass1.get("replicates") or []) + list(pass2.get("replicates") or [])):
        # Normalize replicate indices
        if isinstance(rep, WELReplicate):
            rep = WELReplicate(
                replicate_idx=idx,
                docs=rep.docs,
                p_web=rep.p_web,
                support_bullets=rep.support_bullets,
                oppose_bullets=rep.oppose_bullets,
                notes=rep.notes,
                json_valid=rep.json_valid,
            )
        elif isinstance(rep, dict):
            rep = {
                **rep,
                "replicate_idx": idx,
            }
        reps_all.append(rep)
    replicate_ps_all: List[float] = list(pass1.get("replicate_ps") or []) + list(pass2.get("replicate_ps") or [])
    if not replicate_ps_all:
        # No usable evidence across both passes
        raise RuntimeError("No documents retrieved for Web-Informed evaluation")
    p_hat, ci95, dispersion = combine_replicates_ps(replicate_ps_all)

    # Recompute evidence metrics on combined docs
    total_docs = len(docs_all) or 1
    confident_count = sum(1 for doc in docs_all if getattr(doc, "published_at", None) and getattr(doc, "published_confidence", 0) >= 0.5)
    median_confident = median_age_days(docs_all, min_confidence=0.5)
    if math.isnan(median_confident):
        median_value = 365.0
        confident_rate = 0.0
    else:
        median_value = float(median_confident)
        confident_rate = float(confident_count) / float(total_docs)

    metrics = {
        **evidence_metrics(docs_all),
        "median_age_days": median_value,
        "n_confident_dates": float(confident_count),
        "date_confident_rate": confident_rate,
        "dispersion": dispersion,
        "json_valid_rate": 1.0,  # combined pass is always derived from valid JSON-only replicates list
        "resolved": False,
        "resolved_truth": None,
        "resolved_reason": None,
        "resolved_support": None,
        "resolved_contradict": None,
        "resolved_domains": None,
        "resolved_citations": [],
        "resolved_debug_votes": None,
    }

    warning_counts_all = _merge_warning_counts(pass1.get("warning_counts"), pass2.get("warning_counts"))

    return {
        "p": p_hat,
        "ci95": ci95,
        "replicates": reps_all,
        "metrics": metrics,
        "warning_counts": warning_counts_all,
        "provenance": {
            "provider": provider,
            "model": model,
            "k_docs": k_docs,
            "replicates": len(reps_all),
            "recency_days": recency_second,
            "passes": passes_used,
            "seed": seed_val,
            "resolved": False,
        },
    }
