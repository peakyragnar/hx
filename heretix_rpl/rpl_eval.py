import json, time, hashlib
import numpy as np
from openai import OpenAI
from heretix_rpl.rpl_schema import RPL_JSON_SCHEMA
from heretix_rpl.rpl_prompts import SYSTEM_RPL, USER_TEMPLATE, PARAPHRASES, PROMPT_VERSION

client = None

def get_client():
    global client
    if client is None:
        client = OpenAI()
    return client

# GPT-5 requires more tokens for structured outputs
GPT5_DECODING = {
    "max_completion_tokens": 2000,  # GPT-5 needs more tokens
}

# Legacy GPT-4 settings (kept for reference)
DECODING = {
    "temperature": 0.0,
    "top_p": 1.0,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "max_output_tokens": 640,
}

def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1-1e-6)
    return np.log(p/(1-p))

def _sigmoid(x: float) -> float:
    return float(1/(1+np.exp(-x)))

def median_of_means(logits, buckets=5):
    """Robust aggregation using median-of-means in log-odds space."""
    n = len(logits)
    if n < buckets:
        return float(np.mean(logits))
    # Randomly permute and split into buckets
    chunks = np.array_split(np.random.permutation(logits), buckets)
    means = [float(np.mean(c)) for c in chunks]
    return float(np.median(means))

def bootstrap_ci_logits(logits, B=1000, alpha=0.05):
    """Bootstrap confidence intervals in log-odds space."""
    logits = np.array(logits, dtype=float)
    n = len(logits)
    # Bootstrap sampling
    idx = np.random.randint(0, n, size=(B, n))
    means = np.mean(logits[idx], axis=1)
    # Compute percentiles
    lo = np.percentile(means, 100*alpha/2)
    hi = np.percentile(means, 100*(1-alpha/2))
    return float(lo), float(hi)

def compute_stability(logits):
    """Compute stability score based on IQR of logits."""
    iqr_l = float(np.percentile(logits, 75) - np.percentile(logits, 25))
    stability = 1.0 / (1.0 + iqr_l)
    return stability

def call_rpl_once_gpt5(claim_text: str, paraphrase_prompt: str, model: str = "gpt-5"):
    """GPT-5 specific implementation using Chat Completions API."""
    instructions = SYSTEM_RPL
    # Use paraphrase if provided
    if "{CLAIM}" in paraphrase_prompt:
        user_text = paraphrase_prompt.replace("{CLAIM}", claim_text) + "\n\n" + USER_TEMPLATE.replace("{CLAIM}", claim_text)
    else:
        user_text = USER_TEMPLATE.replace("{CLAIM}", claim_text)

    # GPT-5 request - no temperature control, uses max_completion_tokens
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": user_text}
    ]
    
    req = dict(
        model=model,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": RPL_JSON_SCHEMA},
        max_completion_tokens=GPT5_DECODING["max_completion_tokens"]
        # No temperature, top_p, or penalties for GPT-5
    )

    resp = get_client().chat.completions.create(**req)

    # Parse the JSON response
    try:
        if resp.choices[0].message.content:
            obj = json.loads(resp.choices[0].message.content)
        else:
            raise ValueError("Empty response from GPT-5")
    except Exception as e:
        raise ValueError(f"Failed to parse JSON response: {e}")

    return {
        "model": resp.model,
        "raw": obj,
        "meta": {
            "provider_model_id": resp.model,
            "prompt_version": PROMPT_VERSION,
            "finish_reason": resp.choices[0].finish_reason
        }
    }

def call_rpl_once(claim_text: str, paraphrase_prompt: str, model: str, seed: int | None = None):
    """Legacy GPT-4 implementation - kept for compatibility."""
    instructions = SYSTEM_RPL
    # Use paraphrase if provided, otherwise use the template
    if "{CLAIM}" in paraphrase_prompt:
        user_text = paraphrase_prompt.replace("{CLAIM}", claim_text) + "\n\n" + USER_TEMPLATE.replace("{CLAIM}", claim_text)
    else:
        user_text = USER_TEMPLATE.replace("{CLAIM}", claim_text)

    # Build ChatCompletion request with structured outputs
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": user_text}
    ]
    
    req = dict(
        model=model,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": RPL_JSON_SCHEMA},
        temperature=DECODING["temperature"],
        top_p=DECODING["top_p"],
        presence_penalty=DECODING["presence_penalty"],
        frequency_penalty=DECODING["frequency_penalty"],
        max_tokens=DECODING["max_output_tokens"]
    )
    if seed is not None:
        req["seed"] = seed

    resp = get_client().chat.completions.create(**req)

    # Parse the JSON response
    try:
        obj = json.loads(resp.choices[0].message.content)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON response: {e}")

    return {
        "model": resp.model,
        "raw": obj,
        "meta": {
            "provider_model_id": resp.model,
            "prompt_version": PROMPT_VERSION
        }
    }

def evaluate_rpl_gpt5(claim_text: str, model: str = "gpt-5", K: int = 7, R: int = 3):
    """GPT-5 evaluation with K×R sampling and robust aggregation."""
    runs = []
    logits = []
    
    # K paraphrases × R replicates
    for k in range(K):
        phr = PARAPHRASES[k % len(PARAPHRASES)]
        for r in range(R):
            try:
                out = call_rpl_once_gpt5(claim_text, phr, model)
                p = out["raw"]["prob_true"]
                l = _logit(p)
                runs.append({
                    **out,
                    "paraphrase_idx": k,
                    "replicate_idx": r
                })
                logits.append(l)
            except Exception as e:
                print(f"Warning: Failed sample k={k}, r={r}: {e}")
                continue
    
    if len(logits) < 3:
        raise ValueError(f"Too few successful samples: {len(logits)}")
    
    # Robust aggregation
    mom = median_of_means(logits, buckets=min(5, len(logits)))
    p_hat = _sigmoid(mom)
    
    # Confidence intervals
    lo_l, hi_l = bootstrap_ci_logits(logits, B=1000, alpha=0.05)
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)
    
    # Stability score
    stability = compute_stability(logits)
    
    # Stable run id for provenance
    digest = hashlib.sha256(
        f"{claim_text}|{model}|{PROMPT_VERSION}|K={K}|R={R}".encode("utf-8")
    ).hexdigest()[:12]
    
    return {
        "run_id": f"rpl-g5-{digest}",
        "claim": claim_text,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "sampling": {"K": K, "R": R, "N": len(logits)},
        "decoding": {
            "max_completion_tokens": GPT5_DECODING["max_completion_tokens"]
        },
        "timestamp": int(time.time()),
        "aggregates": {
            "prob_true_rpl": p_hat,
            "ci95": [lo_p, hi_p],
            "ci_width": hi_p - lo_p,
            "stability_score": stability,
            "is_stable": (hi_p - lo_p) <= 0.2  # Flag if CI width > 0.2
        },
        "paraphrase_results": runs,
        "raw_logits": logits  # For debugging/analysis
    }

def evaluate_rpl(claim_text: str, model: str, k: int = 5, seed: int | None = None, r: int = 1):
    """Main evaluation function - routes to GPT-5 or legacy based on model."""
    if model.startswith("gpt-5"):
        # Use GPT-5 implementation with K×R sampling
        return evaluate_rpl_gpt5(claim_text, model, K=k, R=r)
    else:
        # Legacy implementation for GPT-4 and others
        runs = []
        for i in range(k):
            runs.append(call_rpl_once(claim_text, PARAPHRASES[i % len(PARAPHRASES)], model, seed))

        probs = [r["raw"]["prob_true"] for r in runs]
        logits = [_logit(p) for p in probs]
        mean_logit = float(np.mean(logits))
        var_logit = float(np.var(logits, ddof=1)) if len(logits) > 1 else 0.0
        p_rpl = _sigmoid(mean_logit)

        # Stable run id for provenance
        digest = hashlib.sha256(
            f"{claim_text}|{model}|{PROMPT_VERSION}|{k}".encode("utf-8")
        ).hexdigest()[:12]

        return {
            "run_id": f"rpl-{digest}",
            "claim": claim_text,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "decoding": DECODING,
            "k": k,
            "timestamp": int(time.time()),
            "paraphrase_results": runs,
            "aggregates": {
                "prob_true_rpl": p_rpl,
                "logit_variance": var_logit
            }
        }