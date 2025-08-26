from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml

from .config import RunConfig
from .sampler import rotation_offset, balanced_indices_with_rotation, planned_counts
from .seed import make_bootstrap_seed
from .aggregate import aggregate_clustered
from .metrics import compute_stability_calibrated, stability_band_from_iqr
from .cache import make_cache_key, get_cached_sample
from .storage import _ensure_db, insert_run, insert_samples
from .provider.openai_gpt5 import score_claim
from .provider.mock import score_claim_mock


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return float(np.log(p / (1 - p)))


def _sigmoid(x: float) -> float:
    x = float(np.clip(x, -709, 709))
    return float(1 / (1 + np.exp(-x)))


def _load_prompts(path: str) -> Dict[str, Any]:
    doc = yaml.safe_load(Path(path).read_text())
    required = ["version", "system", "user_template", "paraphrases"]
    for k in required:
        if k not in doc:
            raise ValueError(f"Prompt file missing key: {k}")
    return doc


def _has_citation_or_url(text: str) -> bool:
    t = text.lower()
    return ("http://" in t) or ("https://" in t) or ("www." in t)


def run_single_version(cfg: RunConfig, *, prompt_file: str, mock: bool = False) -> Dict[str, Any]:
    prompts = _load_prompts(prompt_file)
    prompt_version_full = str(prompts.get("version"))
    system_text = str(prompts.get("system"))
    user_template = str(prompts.get("user_template"))
    paraphrases: List[str] = [str(x) for x in prompts.get("paraphrases", [])]
    if not paraphrases:
        raise ValueError("No paraphrases found in prompt file")

    T_bank = len(paraphrases)
    T_stage = int(cfg.T) if cfg.T is not None else T_bank
    T_stage = max(1, min(T_stage, T_bank))
    off = rotation_offset(cfg.claim, cfg.model, prompt_version_full, T_bank)
    order = list(range(T_bank))
    if T_bank > 1 and off % T_bank != 0:
        rot = off % T_bank
        order = order[rot:] + order[:rot]
    tpl_indices = order[:T_stage]
    seq = balanced_indices_with_rotation(T_stage, cfg.K, offset=0)  # already rotated via tpl_indices

    # sampling loop
    runs: List[Dict[str, Any]] = []
    by_tpl: Dict[str, List[float]] = {}
    all_logits: List[float] = []
    tpl_hashes: List[str] = []
    cache_hits = 0
    attempted = 0
    valid_count = 0

    for k_slot, local_tpl_idx in enumerate(seq):
        pidx = tpl_indices[local_tpl_idx]
        paraphrase_text = paraphrases[pidx]
        for r in range(cfg.R):
            attempted += 1
            # Compose prompt to compute prompt_sha256 in provider
            # Cache key uses prompt_sha256, not paraphrase index
            # First try cache: we need prompt_sha256; compute from ingredients
            # We deterministically recompute prompt_sha256 same as provider
            paraphrased = paraphrase_text.replace("{CLAIM}", cfg.claim)
            user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", cfg.claim)
            schema_instructions = (
                "Return ONLY valid JSON with exactly these fields:\n"
                "{\n  \"prob_true\": number between 0 and 1,\n  \"confidence_self\": number between 0 and 1,\n  \"assumptions\": array of strings,\n  \"reasoning_bullets\": array of 3-6 strings,\n  \"contrary_considerations\": array of 2-4 strings,\n  \"ambiguity_flags\": array of strings\n}\n"
                "Output ONLY the JSON object, no other text."
            )
            full_instructions = system_text + "\n\n" + schema_instructions
            prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()
            ckey = make_cache_key(
                claim=cfg.claim,
                model=cfg.model,
                prompt_version=prompt_version_full,
                prompt_sha256=prompt_sha256,
                replicate_idx=r,
                max_output_tokens=cfg.max_output_tokens,
            )

            row = None
            if not cfg.no_cache:
                row = get_cached_sample(ckey)
                if row:
                    cache_hits += 1

            if row is None:
                if mock or os.getenv("HERETIX_MOCK"):
                    out = score_claim_mock(
                        claim=cfg.claim,
                        system_text=system_text,
                        user_template=user_template,
                        paraphrase_text=paraphrase_text,
                        model=cfg.model,
                        max_output_tokens=cfg.max_output_tokens,
                    )
                else:
                    out = score_claim(
                        claim=cfg.claim,
                        system_text=system_text,
                        user_template=user_template,
                        paraphrase_text=paraphrase_text,
                        model=cfg.model,
                        max_output_tokens=cfg.max_output_tokens,
                    )
                raw = out.get("raw", {})
                meta = out.get("meta", {})
                timing = out.get("timing", {})
                prob = float(raw.get("prob_true")) if "prob_true" in raw else float("nan")
                lgt = _logit(prob) if prob == prob else float("nan")
                json_valid = int(1 if ("prob_true" in raw and isinstance(raw["prob_true"], (int, float))) else 0)
                # RPL compliance: penalize citations/urls
                # Basic heuristic: if any reasoning or contrary string contains URL-like text
                txt_concat = json.dumps(raw)
                compliant = (json_valid == 1) and (not _has_citation_or_url(txt_concat))
                valid = int(1 if compliant else 0)
                row = {
                    "run_id": "",  # to be filled
                    "cache_key": ckey,
                    "prompt_sha256": meta.get("prompt_sha256"),
                    "paraphrase_idx": int(pidx),
                    "replicate_idx": int(r),
                    "prob_true": prob if prob == prob else None,
                    "logit": lgt if lgt == lgt else None,
                    "provider_model_id": meta.get("provider_model_id"),
                    "response_id": meta.get("response_id"),
                    "created_at": int(time.time()),
                    "tokens_out": None,
                    "latency_ms": int(timing.get("latency_ms") or 0),
                    "json_valid": valid,
                }

            # Only count valid/compliant samples
            if row.get("json_valid"):
                valid_count += 1
                l = float(row.get("logit")) if row.get("logit") is not None else _logit(float(row.get("prob_true")))
                h = str(row.get("prompt_sha256"))
                all_logits.append(l)
                tpl_hashes.append(h)
                by_tpl.setdefault(h, []).append(l)
            # persist sample rows after we have run_id (later)
            runs.append({"row": row, "tpl_hash": row.get("prompt_sha256")})

    if valid_count < 3:
        raise ValueError(f"Too few valid samples: {valid_count} < 3")

    # aggregation
    env_seed = os.getenv("HERETIX_RPL_SEED")
    if env_seed is not None:
        seed_val = int(env_seed)
    else:
        seed_val = make_bootstrap_seed(
            claim=cfg.claim,
            model=cfg.model,
            prompt_version=prompt_version_full,
            k=cfg.K,
            r=cfg.R,
            template_hashes=sorted(set(tpl_hashes)),
            center="trimmed",
            trim=0.2,
            B=cfg.B,
        )
    rng = np.random.default_rng(seed_val)
    ell_hat, (lo_l, hi_l), diag = aggregate_clustered(by_tpl, B=cfg.B, rng=rng, center="trimmed", trim=0.2, fixed_m=None)
    p_hat = _sigmoid(ell_hat)
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)

    stability_basis = [float(np.mean(v)) for v in by_tpl.values()]
    stability, iqr_l = compute_stability_calibrated(stability_basis)
    band = stability_band_from_iqr(iqr_l)

    counts = diag.get("counts_by_template", {})
    imb = float(diag.get("imbalance_ratio")) if diag.get("imbalance_ratio") is not None else 1.0
    cache_hit_rate = (cache_hits / attempted) if attempted else 0.0
    rpl_compliance_rate = (valid_count / attempted) if attempted else 0.0

    # run id
    digest = hashlib.sha256(f"{cfg.claim}|{cfg.model}|{prompt_version_full}|K={cfg.K}|R={cfg.R}".encode("utf-8")).hexdigest()[:12]
    run_id = f"heretix-rpl-{digest}"

    # persist
    conn = _ensure_db()
    for it in runs:
        it["row"]["run_id"] = run_id
    insert_samples(conn, [it["row"] for it in runs])
    insert_run(
        conn,
        {
            "run_id": run_id,
            "created_at": int(time.time()),
            "claim": cfg.claim,
            "model": cfg.model,
            "prompt_version": prompt_version_full,
            "K": cfg.K,
            "R": cfg.R,
            "T": T_stage,
            "B": cfg.B,
            # Store seeds as strings to avoid 64-bit overflow constraints in SQLite INTEGER columns
            "seed": (str(cfg.seed) if cfg.seed is not None else None),
            "bootstrap_seed": str(seed_val),
            "prob_true_rpl": p_hat,
            "ci_lo": lo_p,
            "ci_hi": hi_p,
            "ci_width": (hi_p - lo_p),
            "template_iqr_logit": iqr_l,
            "stability_score": stability,
            "imbalance_ratio": imb,
            "rpl_compliance_rate": rpl_compliance_rate,
            "cache_hit_rate": cache_hit_rate,
            "config_json": json.dumps(cfg.__dict__),
            "sampler_json": json.dumps({"T_bank": T_bank, "T": T_stage, "seq": seq, "tpl_indices": tpl_indices}),
            "counts_by_template_json": json.dumps(counts),
            "artifact_json_path": None,
        },
    )

    return {
        "run_id": run_id,
        "claim": cfg.claim,
        "model": cfg.model,
        "prompt_version": prompt_version_full,
        "sampling": {"K": cfg.K, "R": cfg.R, "T": T_stage},
        "aggregation": {
            "method": diag.get("method"),
            "B": cfg.B,
            "center": "trimmed",
            "trim": 0.2,
            "bootstrap_seed": seed_val,
            "n_templates": diag.get("n_templates"),
            "counts_by_template": counts,
            "imbalance_ratio": imb,
            "template_iqr_logit": iqr_l,
        },
        "aggregates": {
            "prob_true_rpl": p_hat,
            "ci95": [lo_p, hi_p],
            "ci_width": (hi_p - lo_p),
            "stability_score": stability,
            "stability_band": band,
            "is_stable": (hi_p - lo_p) <= 0.20,
            "rpl_compliance_rate": rpl_compliance_rate,
            "cache_hit_rate": cache_hit_rate,
        },
    }
