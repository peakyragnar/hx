from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml
import uuid

from .config import RunConfig
from .sampler import rotation_offset, balanced_indices_with_rotation, planned_counts
from .seed import make_bootstrap_seed
from .aggregate import aggregate_clustered
from .metrics import compute_stability_calibrated, stability_band_from_iqr
from .cache import make_cache_key, get_cached_sample
from .storage import _ensure_db, insert_run, insert_samples, insert_execution, insert_execution_samples, insert_prompt
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

    # Compose instruction prefix (system + schema) once
    schema_instructions = (
        "Return ONLY JSON matching this schema: "
        "{ \"prob_true\": 0..1, \"confidence_self\": 0..1, "
        "\"assumptions\": [string], \"reasoning_bullets\": [3-6 strings], "
        "\"contrary_considerations\": [2-4 strings], \"ambiguity_flags\": [string] } "
        "Output the JSON object only."
    )
    full_instructions = system_text + "\n\n" + schema_instructions

    # Compute per-template prompt lengths and enforce cap
    prompt_lengths: Dict[int, int] = {}
    for pidx in tpl_indices:
        paraphrase_text = paraphrases[pidx]
        paraphrased = paraphrase_text.replace("{CLAIM}", cfg.claim)
        user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", cfg.claim)
        plen = len(full_instructions + "\n\n" + user_text)
        prompt_lengths[pidx] = plen
    prompt_char_len_max = max(prompt_lengths.values()) if prompt_lengths else 0
    if cfg.max_prompt_chars is not None and prompt_char_len_max > int(cfg.max_prompt_chars):
        raise ValueError(
            f"Prompt length {prompt_char_len_max} exceeds max_prompt_chars={cfg.max_prompt_chars}. Reduce claim length or template text."
        )

    # sampling loop
    runs: List[Dict[str, Any]] = []
    by_tpl: Dict[str, List[float]] = {}
    all_logits: List[float] = []
    tpl_hashes: List[str] = []
    cache_hits = 0
    attempted = 0
    valid_count = 0

    # Track how many slots we've assigned per template (by prompt hash) to make replicate_idx unique per occurrence
    occ_by_hash: Dict[str, int] = {}

    for k_slot, local_tpl_idx in enumerate(seq):
        pidx = tpl_indices[local_tpl_idx]
        paraphrase_text = paraphrases[pidx]

        # Compose prompt once per slot to compute stable prompt_sha256 for this template
        paraphrased = paraphrase_text.replace("{CLAIM}", cfg.claim)
        user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", cfg.claim)
        prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()

        occ_idx = occ_by_hash.get(prompt_sha256, 0)
        occ_by_hash[prompt_sha256] = occ_idx + 1

        for r in range(cfg.R):
            attempted += 1
            # Make replicate index unique per template across all slots
            replicate_idx_global = int(occ_idx * cfg.R + r)
            provider_mode = "MOCK" if (mock or os.getenv("HERETIX_MOCK")) else "LIVE"
            ckey = make_cache_key(
                claim=cfg.claim,
                model=cfg.model,
                prompt_version=prompt_version_full,
                prompt_sha256=prompt_sha256,
                replicate_idx=replicate_idx_global,
                max_output_tokens=cfg.max_output_tokens,
                provider_mode=provider_mode,
            )

            row = None
            if not cfg.no_cache:
                row = get_cached_sample(ckey)
                if row:
                    cache_hits += 1

            if row is None:
                if provider_mode == "MOCK":
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
                    "replicate_idx": int(replicate_idx_global),
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
    # Seed precedence: config seed > env > derived deterministic
    if cfg.seed is not None:
        seed_val = int(cfg.seed)
    elif os.getenv("HERETIX_RPL_SEED") is not None:
        seed_val = int(os.getenv("HERETIX_RPL_SEED"))
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

    # Derived quality summary (PQS) and gates
    # PQS v1: 0.4*stability + 0.4*(1 - min(width,0.5)/0.5) + 0.2*compliance, scaled to 0..100
    width = float(hi_p - lo_p)
    pqs_val = int(100 * (0.4 * stability + 0.4 * (1 - min(width, 0.5) / 0.5) + 0.2 * rpl_compliance_rate))
    gate_compliance_ok = int(1 if rpl_compliance_rate >= 0.98 else 0)
    gate_stability_ok = int(1 if stability >= 0.25 else 0)
    gate_precision_ok = int(1 if width <= 0.30 else 0)
    pqs_version = "v1"

    # run id
    digest = hashlib.sha256(f"{cfg.claim}|{cfg.model}|{prompt_version_full}|K={cfg.K}|R={cfg.R}".encode("utf-8")).hexdigest()[:12]
    run_id = f"heretix-rpl-{digest}"

    # persist
    conn = _ensure_db()
    # Persist prompt text for provenance (once per version)
    try:
        import json as _json
        yaml_hash_basis = system_text + "\n\n" + user_template + "\n\n" + "\n".join(paraphrases)
        yaml_hash = hashlib.sha256(yaml_hash_basis.encode("utf-8")).hexdigest()
        insert_prompt(
            conn,
            prompt_version=prompt_version_full,
            yaml_hash=yaml_hash,
            system_text=system_text,
            user_template=user_template,
            paraphrases_json=_json.dumps(paraphrases),
            source_path=str(prompt_file),
            created_at=int(time.time()),
            author_note=None,
        )
    except Exception:
        pass
    for it in runs:
        it["row"]["run_id"] = run_id
    insert_samples(conn, [it["row"] for it in runs])
    # execution id for this invocation
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"
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
            "prompt_char_len_max": prompt_char_len_max,
            "pqs": pqs_val,
            "gate_compliance_ok": gate_compliance_ok,
            "gate_stability_ok": gate_stability_ok,
            "gate_precision_ok": gate_precision_ok,
            "pqs_version": pqs_version,
        },
    )

    # Insert immutable execution summary and mapping to used samples (valid only)
    insert_execution(
        conn,
        {
            "execution_id": execution_id,
            "run_id": run_id,
            "created_at": int(time.time()),
            "claim": cfg.claim,
            "model": cfg.model,
            "prompt_version": prompt_version_full,
            "K": cfg.K,
            "R": cfg.R,
            "T": T_stage,
            "B": cfg.B,
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
            "prompt_char_len_max": prompt_char_len_max,
            "pqs": pqs_val,
            "gate_compliance_ok": gate_compliance_ok,
            "gate_stability_ok": gate_stability_ok,
            "gate_precision_ok": gate_precision_ok,
            "pqs_version": pqs_version,
        },
    )
    # Map execution to the exact cached samples used (valid only)
    exec_maps = [
        {"execution_id": execution_id, "cache_key": it["row"]["cache_key"]}
        for it in runs
        if it["row"].get("json_valid")
    ]
    insert_execution_samples(conn, exec_maps)

    return {
        "execution_id": execution_id,
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
            "prompt_char_len_max": prompt_char_len_max,
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
