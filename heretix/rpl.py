from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Optional

import numpy as np
import yaml
import uuid
import concurrent.futures as _fut

from .config import RunConfig, load_runtime_settings
from .sampler import rotation_offset, balanced_indices_with_rotation, planned_counts
from .seed import make_bootstrap_seed
from .aggregate import aggregate_clustered
from .metrics import compute_stability_calibrated, stability_band_from_iqr
from .cache import (
    make_cache_key,
    make_run_cache_key,
    sample_cache_get,
    sample_cache_set,
    configure_runtime_caches,
    run_cache_get,
    run_cache_set,
)
from .storage import (
    _ensure_db,
    insert_run,
    insert_samples,
    insert_execution,
    insert_execution_samples,
    insert_prompt,
    update_run_ci,
    update_execution_ci,
)
from .provider.config import load_provider_capabilities
from .provider.factory import get_rpl_adapter
from .provider.schema_text import RPL_SAMPLE_JSON_SCHEMA
from .provider.utils import infer_provider_from_model
from .telemetry import timed, est_tokens, est_cost, log
from .finalizer import kick_off_final_ci
from .constants import SCHEMA_VERSION


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


def _coerce_prob(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        prob = float(value)
    except (TypeError, ValueError):
        return None
    if prob < 0 or prob > 1:
        return None
    return prob


def _extract_prob_true(raw: Any) -> Optional[float]:
    if not isinstance(raw, dict):
        return None
    direct = _coerce_prob(raw.get("prob_true"))
    if direct is not None:
        return direct
    belief = raw.get("belief")
    if isinstance(belief, dict):
        nested = _coerce_prob(belief.get("prob_true"))
        if nested is not None:
            return nested
    return None


def _normalize_provider_id(provider: Optional[str]) -> Optional[str]:
    if provider is None:
        return None
    text = str(provider).strip().lower()
    return text or None


class ProviderResolutionError(ValueError):
    """Raised when a configured provider override cannot be satisfied."""


def _resolve_provider_and_model(provider_hint: Optional[str], logical_model: str) -> tuple[str, str]:
    """Return (provider_id, logical_model) honoring explicit provider overrides."""

    normalized_hint = _normalize_provider_id(provider_hint)
    inferred = infer_provider_from_model(logical_model) or "openai"
    if not normalized_hint:
        return inferred, logical_model
    if normalized_hint == inferred:
        return normalized_hint, logical_model
    try:
        caps = load_provider_capabilities()
    except Exception as exc:
        raise ProviderResolutionError(
            f"Provider override '{provider_hint}' requires provider capability files"
        ) from exc
    record = caps.get(normalized_hint)
    if record is None:
        raise ProviderResolutionError(f"Unknown provider '{provider_hint}'")
    resolved_model = record.default_model
    log.info(
        "provider_override_applied",
        extra={
            "provider": normalized_hint,
            "requested_model": logical_model,
            "resolved_model": resolved_model,
        },
    )
    return normalized_hint, resolved_model


def run_single_version(cfg: RunConfig, *, prompt_file: str, mock: bool = False) -> Dict[str, Any]:
    requested_logical_model = cfg.logical_model or cfg.model
    provider_id, resolved_model = _resolve_provider_and_model(cfg.provider, requested_logical_model)
    cfg.provider = provider_id
    cfg.logical_model = requested_logical_model
    cfg.model = resolved_model
    prompts = _load_prompts(prompt_file)
    prompt_version_full = str(prompts.get("version"))
    system_text = str(prompts.get("system"))
    user_template = str(prompts.get("user_template"))
    paraphrases: List[str] = [str(x) for x in prompts.get("paraphrases", [])]
    if not paraphrases:
        raise ValueError("No paraphrases found in prompt file")

    runtime = load_runtime_settings()
    configure_runtime_caches(
        sample_ttl=runtime.l1_ttl_seconds,
        sample_max=runtime.l1_max_items,
        run_ttl=runtime.cache_ttl_seconds,
        run_max=max(64, runtime.l1_max_items // 2),
    )

    run_start = time.perf_counter()

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
    schema_instructions = RPL_SAMPLE_JSON_SCHEMA
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

    # Decide provider mode and target DB path once per run
    provider_mode = "MOCK" if (mock or os.getenv("HERETIX_MOCK")) else "LIVE"
    adapter = get_rpl_adapter(provider_mode=provider_mode, model=cfg.model)
    db_path = Path("runs/heretix_mock.sqlite") if provider_mode == "MOCK" else Path("runs/heretix.sqlite")

    final_B = max(1, int(cfg.B))
    fast_B = final_B if not runtime.fast_then_final else max(1, min(final_B, runtime.fast_ci_B))

    provider_for_cache = cfg.provider or infer_provider_from_model(cfg.model) or "openai"
    run_cache_key: Optional[str] = None
    if runtime.cache_ttl_seconds > 0:
        if cfg.seed is not None:
            seed_marker = f"cfg:{cfg.seed}"
        else:
            env_seed_override = os.getenv("HERETIX_RPL_SEED")
            seed_marker = f"env:{env_seed_override}" if env_seed_override is not None else "auto"

        run_cache_key = make_run_cache_key(
            claim=cfg.claim,
            model=cfg.model,
            provider=provider_for_cache,
            prompt_version=prompt_version_full,
            K=cfg.K,
            R=cfg.R,
            T=T_stage,
            max_output_tokens=cfg.max_output_tokens,
            provider_mode=provider_mode,
            target_B=final_B,
            seed_marker=seed_marker,
        )

        if not cfg.no_cache:
            cached_run = run_cache_get(
                run_cache_key,
                db_path=db_path,
                ttl_seconds=runtime.cache_ttl_seconds,
            )
           if cached_run:
               cached_run = annotate_cache_hit(cached_run)
               log.info(
                   "run_summary",
                    extra={
                        "claim": (cfg.claim or "")[:80],
                        "run_id": cached_run.get("run_id"),
                        "phase": "cache_hit",
                        "workers": 0,
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "cost_usd": 0.0,
                        "cache_samples": 0,
                        "cache_runs": 1,
                        "ms_total": 0,
                    },
                )
                cached_run["cache_hit"] = True
                return cached_run

    # sampling loop
    runs: List[Dict[str, Any]] = []
    by_tpl: Dict[str, List[float]] = {}
    all_logits: List[float] = []
    tpl_hashes: List[str] = []
    attempted = 0
    valid_count = 0
    sample_cache_hits = 0
    sample_cache_misses = 0
    total_tokens_in = 0
    total_tokens_out = 0
    metrics_lock = threading.Lock()
    warning_counts: Dict[str, int] = {}

    def _record_warnings(labels: Iterable[str]) -> None:
        if not labels:
            return
        with metrics_lock:
            for label in labels:
                warning_counts[label] = warning_counts.get(label, 0) + 1

    def _apply_cached_warnings(row_obj: Dict[str, Any]) -> None:
        raw = row_obj.get("warnings_json")
        if not raw:
            return
        decoded: Any = None
        if isinstance(raw, str):
            raw_str = raw.strip()
            if not raw_str:
                return
            try:
                decoded = json.loads(raw_str)
            except Exception:
                return
        elif isinstance(raw, (list, tuple)):
            decoded = raw
        else:
            return
        labels = [str(item).strip() for item in decoded if isinstance(item, str) and item.strip()]
        if labels:
            _record_warnings(labels)

    # Precompute deterministic work list (one entry per attempt)
    class _Work:
        __slots__ = (
            "pidx",
            "paraphrase_text",
            "prompt_sha256",
            "replicate_idx_global",
            "cache_key",
            "prompt_char_len",
        )

        def __init__(
            self,
            pidx: int,
            paraphrase_text: str,
            prompt_sha256: str,
            rep_idx: int,
            cache_key: str,
            prompt_char_len: int,
        ) -> None:
            self.pidx = pidx
            self.paraphrase_text = paraphrase_text
            self.prompt_sha256 = prompt_sha256
            self.replicate_idx_global = rep_idx
            self.cache_key = cache_key
            self.prompt_char_len = prompt_char_len

    work_items: List[_Work] = []
    occ_by_hash: Dict[str, int] = {}
    for local_tpl_idx in seq:
        pidx = tpl_indices[local_tpl_idx]
        paraphrase_text = paraphrases[pidx]
        paraphrased = paraphrase_text.replace("{CLAIM}", cfg.claim)
        user_text = f"{paraphrased}\n\n" + user_template.replace("{CLAIM}", cfg.claim)
        prompt_sha256 = hashlib.sha256((full_instructions + "\n\n" + user_text).encode("utf-8")).hexdigest()
        occ_idx = occ_by_hash.get(prompt_sha256, 0)
        occ_by_hash[prompt_sha256] = occ_idx + 1
        for r in range(cfg.R):
            rep_idx = int(occ_idx * cfg.R + r)
            ckey = make_cache_key(
                claim=cfg.claim,
                model=cfg.model,
                prompt_version=prompt_version_full,
                prompt_sha256=prompt_sha256,
                replicate_idx=rep_idx,
                max_output_tokens=cfg.max_output_tokens,
                provider_mode=provider_mode,
            )
            work_items.append(_Work(pidx, paraphrase_text, prompt_sha256, rep_idx, ckey, prompt_lengths[pidx]))

    # First, satisfy from cache (main thread) and collect misses
    rows_ready: List[Dict[str, Any]] = []
    misses: List[_Work] = []
    for w in work_items:
        attempted += 1
        row = None
        if not cfg.no_cache:
            row = sample_cache_get(
                w.cache_key,
                db_path=db_path,
                ttl_seconds=runtime.cache_ttl_seconds,
            )
            if row:
                sample_cache_hits += 1
                _apply_cached_warnings(row)
        if row is None:
            if not cfg.no_cache:
                sample_cache_misses += 1
            misses.append(w)
        else:
            rows_ready.append(row)

    # Define a worker to call provider and build a sample row
    def _call_and_build(w: _Work) -> Dict[str, Any]:
        nonlocal total_tokens_in, total_tokens_out

        prompt_tokens_est = est_tokens(w.prompt_char_len)
        with metrics_lock:
            total_tokens_in += prompt_tokens_est

        def _once() -> Dict[str, Any]:
            return adapter.score_claim(
                claim=cfg.claim,
                system_text=system_text,
                user_template=user_template,
                paraphrase_text=w.paraphrase_text,
                model=cfg.model,
                max_output_tokens=cfg.max_output_tokens,
            )

        with timed(
            "provider_call",
            {
                "provider": provider_mode,
                "model": cfg.model,
                "paraphrase_idx": w.pidx,
            },
        ):
            out = _once()
        adapter_warnings = list(out.get("warnings") or [])
        _record_warnings(adapter_warnings)
        raw = out.get("raw", {})
        sample_payload = out.get("sample")
        canonical_payload = sample_payload or raw
        meta = out.get("meta", {})
        timing = out.get("timing", {})

        # Minimal retry: if live and no numeric prob_true or URL leakage, try once more
        def _is_valid_raw(obj: Dict[str, Any]) -> bool:
            try:
                prob_val = _extract_prob_true(obj)
                if prob_val is None:
                    return False
                if _has_citation_or_url(json.dumps(obj)):
                    return False
                return True
            except Exception:
                return False

        if provider_mode != "MOCK" and not _is_valid_raw(canonical_payload):
            # small jitter based on cache key to reduce burst
            try:
                sleep_ms = (int(w.cache_key[:6], 16) % 50) / 1000.0
                time.sleep(0.05 + sleep_ms)
            except Exception:
                time.sleep(0.05)
            out = _once()
            adapter_warnings = list(out.get("warnings") or [])
            _record_warnings(adapter_warnings)
            raw = out.get("raw", {})
            sample_payload = out.get("sample")
            canonical_payload = sample_payload or raw
            meta = out.get("meta", {})
            timing = out.get("timing", {})

        prob_val = _extract_prob_true(canonical_payload)
        prob = float(prob_val) if prob_val is not None else float("nan")
        lgt = _logit(prob) if prob == prob else float("nan")
        json_valid = int(1 if prob_val is not None else 0)
        txt_concat = json.dumps(raw)
        compliant = (json_valid == 1) and (not _has_citation_or_url(txt_concat))
        valid = int(1 if compliant else 0)
        response_chars = len(txt_concat)
        resp_tokens_est = est_tokens(response_chars)
        with metrics_lock:
            total_tokens_out += resp_tokens_est

        row = {
            "run_id": "",
            "cache_key": w.cache_key,
            "prompt_sha256": meta.get("prompt_sha256"),
            "paraphrase_idx": int(w.pidx),
            "replicate_idx": int(w.replicate_idx_global),
            "prob_true": prob if prob == prob else None,
            "logit": lgt if lgt == lgt else None,
            "provider_model_id": meta.get("provider_model_id"),
            "response_id": meta.get("response_id"),
            "created_at": int(time.time()),
            "tokens_out": int(resp_tokens_est),
            "latency_ms": int(timing.get("latency_ms") or 0),
            "json_valid": valid,
            "warnings_json": json.dumps(adapter_warnings) if adapter_warnings else None,
        }
        sample_cache_set(w.cache_key, row)
        return row

    # Dispatch misses with optional concurrency
    max_workers: Optional[int] = runtime.rpl_max_workers if runtime.rpl_max_workers > 1 else None

    if misses:
        if max_workers and max_workers > 1:
            try:
                with timed(
                    "sampling_dispatch",
                    {"workers": max_workers, "misses": len(misses)},
                ):
                    with _fut.ThreadPoolExecutor(max_workers=max_workers) as ex:
                        for row in ex.map(_call_and_build, misses):
                            rows_ready.append(row)
            except Exception as e:
                print(f"[rpl] WARN: concurrency setup failed ({e}); falling back to sequential.")
                with timed(
                    "sampling_dispatch",
                    {"workers": 1, "misses": len(misses)},
                ):
                    for w in misses:
                        rows_ready.append(_call_and_build(w))
        else:
            with timed(
                "sampling_dispatch",
                {"workers": 1, "misses": len(misses)},
            ):
                for w in misses:
                    rows_ready.append(_call_and_build(w))

    # If concurrency was used and many rows are invalid, try a sequential repair pass
    if max_workers and max_workers > 1:
        # Build a map from cache_key to work item for quick lookup
        wmap = {w.cache_key: w for w in work_items}
        repaired: List[Dict[str, Any]] = []
        invalid_before = 0
        for row in rows_ready:
            if row.get("json_valid"):
                repaired.append(row)
                continue
            invalid_before += 1
            w = wmap.get(str(row.get("cache_key")))
            if w is None:
                repaired.append(row)
                continue
            # Sequential retry (one more attempt)
            try:
                repaired_row = _call_and_build(w)
                repaired.append(repaired_row)
            except Exception:
                repaired.append(row)
        rows_ready = repaired
        invalid_after = sum(1 for r in rows_ready if not r.get("json_valid"))
        print(f"[rpl] Concurrency: workers={max_workers} misses={len(misses)} invalid_before={invalid_before} invalid_after={invalid_after}")

    # Build aggregation inputs and runs list from all rows
    for row in rows_ready:
        if row.get("json_valid"):
            valid_count += 1
            l = float(row.get("logit")) if row.get("logit") is not None else _logit(float(row.get("prob_true")))
            h = str(row.get("prompt_sha256"))
            all_logits.append(l)
            tpl_hashes.append(h)
            by_tpl.setdefault(h, []).append(l)
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
    with timed(
        "bootstrap_fast",
        {"B": fast_B, "templates": len(by_tpl)},
    ):
        ell_hat, (lo_l, hi_l), diag = aggregate_clustered(
            by_tpl,
            B=fast_B,
            rng=rng,
            center="trimmed",
            trim=0.2,
            fixed_m=None,
        )
    p_hat = _sigmoid(ell_hat)
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)

    stability_basis = [float(np.mean(v)) for v in by_tpl.values()]
    stability, iqr_l = compute_stability_calibrated(stability_basis)
    band = stability_band_from_iqr(iqr_l)

    counts = diag.get("counts_by_template", {})
    imb = float(diag.get("imbalance_ratio")) if diag.get("imbalance_ratio") is not None else 1.0
    cache_hit_rate = (sample_cache_hits / attempted) if attempted else 0.0
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

    estimated_cost = est_cost(
        total_tokens_in,
        total_tokens_out,
        runtime.price_per_1k_prompt,
        runtime.price_per_1k_output,
    )

    # persist
    conn = _ensure_db(db_path)
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
    warning_total = sum(warning_counts.values())
    warning_counts_export = dict(warning_counts)
    sampler_meta = {
        "T_bank": T_bank,
        "T": T_stage,
        "seq": seq,
        "tpl_indices": tpl_indices,
        "warning_counts": warning_counts_export,
        "warning_total": warning_total,
    }

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
            "provider": provider_id,
            "logical_model": requested_logical_model,
            "prompt_version": prompt_version_full,
            "schema_version": SCHEMA_VERSION,
            "K": cfg.K,
            "R": cfg.R,
            "T": T_stage,
            "B": fast_B,
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
            "sampler_json": json.dumps(sampler_meta),
            "counts_by_template_json": json.dumps(counts),
            "artifact_json_path": None,
            "prompt_char_len_max": prompt_char_len_max,
            "pqs": pqs_val,
            "gate_compliance_ok": gate_compliance_ok,
            "gate_stability_ok": gate_stability_ok,
            "gate_precision_ok": gate_precision_ok,
            "pqs_version": pqs_version,
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "cost_usd": estimated_cost,
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
            "B": fast_B,
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
            "sampler_json": json.dumps(sampler_meta),
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

    provider_model_id = next(
        (it["row"].get("provider_model_id") for it in runs if it["row"].get("provider_model_id")),
        None,
    )

    ci_status = {"phase": "final", "B_used": fast_B, "job_id": None}
    if runtime.fast_then_final and final_B > fast_B:
        ci_status = {"phase": "fast", "B_used": fast_B, "job_id": execution_id}

    sampling_info: Dict[str, Any] = {
        "K": cfg.K,
        "R": cfg.R,
        "T": T_stage,
        "warning_counts": warning_counts_export,
        "warning_total": warning_total,
    }

    run_payload: Dict[str, Any] = {
        "execution_id": execution_id,
        "run_id": run_id,
        "claim": cfg.claim,
        "model": cfg.model,
        "logical_model": requested_logical_model,
        "resolved_logical_model": cfg.model,
        "provider": provider_id,
        "prompt_version": prompt_version_full,
        "sampling": sampling_info,
        "aggregation": {
            "method": diag.get("method"),
            "B": fast_B,
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
        "ci_status": ci_status,
        "provider_model_id": provider_model_id,
        "schema_version": SCHEMA_VERSION,
        "tokens_in": total_tokens_in,
        "tokens_out": total_tokens_out,
        "cost_usd": estimated_cost,
    }
    run_payload["warning_counts"] = warning_counts_export

    if run_cache_key and not cfg.no_cache:
        run_cache_set(
            run_cache_key,
            run_payload,
            db_path=db_path,
            ttl_seconds=runtime.cache_ttl_seconds,
        )

    if runtime.fast_then_final and final_B > fast_B:
        tpl_logits_copy = {k: list(v) for k, v in by_tpl.items()}

        def _update_fn(payload: Dict[str, Any]) -> None:
            conn_local = _ensure_db(db_path)
            update_run_ci(
                conn_local,
                run_id,
                ci_lo=payload["ci95"][0],
                ci_hi=payload["ci95"][1],
                ci_width=payload["ci_width"],
                B=payload["aggregation"]["B"],
            )
            update_execution_ci(
                conn_local,
                execution_id,
                ci_lo=payload["ci95"][0],
                ci_hi=payload["ci95"][1],
                ci_width=payload["ci_width"],
                B=payload["aggregation"]["B"],
            )

        def _run_cache_writer(payload: Dict[str, Any]) -> None:
            if cfg.no_cache:
                return
            if not run_cache_key or runtime.cache_ttl_seconds <= 0:
                return
            final_payload = json.loads(json.dumps(run_payload))
            final_payload["aggregates"]["ci95"] = payload["ci95"]
            final_payload["aggregates"]["ci_width"] = payload["ci_width"]
            final_payload["aggregation"]["B"] = payload["aggregation"]["B"]
            final_payload["aggregation"]["counts_by_template"] = payload["aggregation"].get("counts_by_template", {})
            final_payload["aggregation"]["imbalance_ratio"] = payload["aggregation"].get("imbalance_ratio")
            final_payload["aggregation"]["template_iqr_logit"] = payload["aggregation"].get("template_iqr_logit")
            final_payload["ci_status"] = {
                "phase": "final",
                "B_used": payload["aggregation"]["B"],
                "job_id": execution_id,
            }
            run_cache_set(
                run_cache_key,
                final_payload,
                db_path=db_path,
                ttl_seconds=runtime.cache_ttl_seconds,
            )

        kick_off_final_ci(
            by_template_logits=tpl_logits_copy,
            seed=seed_val,
            final_B=final_B,
            update_fn=_update_fn,
            run_cache_writer=_run_cache_writer,
        )

    total_ms = int((time.perf_counter() - run_start) * 1000)
    log.info(
        "run_summary",
        extra={
            "claim": (cfg.claim or "")[:80],
            "run_id": run_id,
            "phase": run_payload["ci_status"]["phase"],
            "workers": max_workers or 1,
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "cost_usd": round(estimated_cost, 4),
            "cache_samples": sample_cache_hits,
            "cache_misses": sample_cache_misses,
            "cache_runs": 0,
            "ms_total": total_ms,
        },
    )

    return run_payload
