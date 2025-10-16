from __future__ import annotations

import hashlib
import os
import random
from typing import Dict, List, Optional

from .aggregate import combine_replicates_ps
from .retriever import make_retriever
from .scoring import call_wel_once
from .snippets import (
    cap_per_domain,
    dedupe_by_url,
    evidence_metrics,
    pack_snippets_for_llm,
)
from .types import Doc, WELReplicate


def _deterministic_seed(claim: str, provider: str, model: str, k_docs: int, replicates: int) -> int:
    canon = f"WEL|{provider}|{model}|{claim}|k={k_docs}|r={replicates}"
    return int.from_bytes(hashlib.sha256(canon.encode("utf-8")).digest()[:8], "big")


def _chunk_docs(docs: List[Doc], replicates: int) -> List[List[Doc]]:
    if replicates <= 1 or len(docs) <= 1:
        return [docs]
    stride = max(1, len(docs) // replicates)
    chunks: List[List[Doc]] = []
    for idx in range(replicates):
        start = idx * stride
        end = start + stride
        subset = docs[start:end] or docs
        chunks.append(subset)
    return chunks


def evaluate_wel(
    claim: str,
    provider: str = "tavily",
    model: str = "gpt-5",
    k_docs: int = 16,
    per_domain_cap: int = 3,
    replicates: int = 2,
    recency_days: Optional[int] = 14,
    seed: Optional[int] = None,
) -> Dict[str, object]:
    """
    Retrieve, evaluate, and aggregate web evidence for the supplied claim.
    """
    retriever = make_retriever(provider=provider)
    query = f"Latest reliable reporting about: {claim}"
    fetched = retriever.search(query=query, k=k_docs * 2, recency_days=recency_days)

    docs = cap_per_domain(dedupe_by_url(fetched), max_per_domain=per_domain_cap)[:k_docs]
    if not docs:
        raise RuntimeError("No documents retrieved for Web-Informed evaluation")

    seed_val = seed if seed is not None else _deterministic_seed(claim, provider, model, k_docs, replicates)
    rng = random.Random(seed_val)
    rng.shuffle(docs)
    doc_chunks = _chunk_docs(docs, replicates=replicates)

    replicates_out: List[WELReplicate] = []
    replicate_ps: List[float] = []
    json_valid = 0
    max_chars = int(os.getenv("WEL_MAX_CHARS", "6000"))

    for idx, chunk in enumerate(doc_chunks):
        bundle = pack_snippets_for_llm(claim, chunk, max_chars=max_chars)
        try:
            payload, prompt_hash = call_wel_once(bundle, model=model)
            p = float(payload.get("p_true"))
            support = [str(x) for x in (payload.get("support_bullets") or [])][:4]
            oppose = [str(x) for x in (payload.get("oppose_bullets") or [])][:4]
            notes = [str(x) for x in (payload.get("notes") or [])][:3]
            valid = True
        except Exception as exc:
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
            )
        )

    p_hat, ci95, dispersion = combine_replicates_ps(replicate_ps)
    metrics = {
        **evidence_metrics(docs),
        "dispersion": dispersion,
        "json_valid_rate": json_valid / max(1, len(replicates_out)),
    }

    return {
        "p": p_hat,
        "ci95": ci95,
        "replicates": replicates_out,
        "metrics": metrics,
        "provenance": {
            "provider": provider,
            "model": model,
            "k_docs": k_docs,
            "replicates": len(doc_chunks),
            "recency_days": recency_days,
            "seed": seed_val,
        },
    }
