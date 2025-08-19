import json, time, hashlib
import numpy as np
from collections import defaultdict
from openai import OpenAI
from heretix_rpl.rpl_schema import RPL_JSON_SCHEMA
from heretix_rpl.rpl_prompts import SYSTEM_RPL, USER_TEMPLATE, PARAPHRASES, PROMPT_VERSION
from heretix_rpl.aggregation import aggregate_clustered, aggregate_simple

client = None

def get_client():
    global client
    if client is None:
        client = OpenAI()
    return client

# GPT-5 uses Responses API with different parameters
GPT5_PARAMS = {
    "max_output_tokens": 1024,  # Responses API parameter (increased for reasoning models)
    "reasoning_effort": "minimal",  # Reduce variance and cost
    "verbosity": "low"  # Keep outputs terse for JSON
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
    """
    GPT-5 via Responses API + Structured Outputs (JSON Schema).
    No temperature/top_p/penalties — treat model as stochastic and sample multiple times.
    """
    client = get_client()
    
    # Build a single, clear user message: paraphrase + schema request, with the claim once.
    paraphrased = paraphrase_prompt.replace("{CLAIM}", claim_text)
    user_text = f"{paraphrased}\n\n" + USER_TEMPLATE.replace("{CLAIM}", claim_text)
    
    # Since Responses API doesn't support response_format, embed schema in instructions
    schema_instructions = """
Return ONLY valid JSON with exactly these fields:
{
  "prob_true": number between 0 and 1,
  "confidence_self": number between 0 and 1,
  "assumptions": array of strings,
  "reasoning_bullets": array of 3-6 strings,
  "contrary_considerations": array of 2-4 strings,
  "ambiguity_flags": array of strings
}
Output ONLY the JSON object, no other text."""
    
    full_instructions = SYSTEM_RPL + "\n\n" + schema_instructions
    
    # Create a reproducible prompt hash for provenance
    prompt_sha256 = hashlib.sha256(
        (full_instructions + "\n\n" + user_text).encode("utf-8")
    ).hexdigest()
    
    # Responses API call - no response_format or verbosity (not supported)
    try:
        resp = client.responses.create(
            model=model,                              # e.g., "gpt-5" or "gpt-5-mini"
            instructions=full_instructions,           # system-equivalent with schema embedded
            input=[{
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}]
            }],
            max_output_tokens=1024,                   # Increased for reasoning models
            reasoning={"effort": "minimal"}          # variance/cost control (this DOES work)
        )
    except Exception as e:
        if "reasoning" in str(e):
            # Feature detection: retry without reasoning parameter
            resp = client.responses.create(
                model=model,
                instructions=full_instructions,
                input=[{
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}]
                }],
                max_output_tokens=1024
            )
        else:
            raise
    
    # Extract JSON from Responses API output
    # The response has output[0]=reasoning, output[1]=message with the JSON text
    try:
        # First try the convenient output_text helper
        if hasattr(resp, 'output_text') and resp.output_text:
            obj = json.loads(resp.output_text)
        else:
            # Find the message item (usually at index 1)
            obj = None
            for item in resp.output:
                if item.type == "message" and hasattr(item, 'content'):
                    for content in item.content:
                        if hasattr(content, 'text'):
                            obj = json.loads(content.text)
                            break
                    if obj:
                        break
            
            if obj is None:
                raise ValueError("No message with JSON text found in response")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")
    except Exception as e:
        raise ValueError(f"Failed to extract JSON from Responses API: {e}")
    
    return {
        "model": resp.model,
        "raw": obj,
        "meta": {
            "response_id": resp.id,
            "created": getattr(resp, 'created_at', None),  # Responses API uses created_at
            "provider_model_id": resp.model,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256
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

def evaluate_rpl_gpt5(claim_text: str, model: str = "gpt-5", K: int = 7, R: int = 3, agg: str = "clustered"):
    """GPT-5 evaluation with K×R sampling and robust aggregation."""
    runs = []
    all_logits = []
    by_tpl = defaultdict(list)
    
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
                all_logits.append(l)
                by_tpl[out["meta"]["prompt_sha256"]].append(l)
            except Exception as e:
                print(f"Warning: Failed sample k={k}, r={r}: {e}")
                continue
    
    if len(all_logits) < 3:
        raise ValueError(f"Too few successful samples: {len(all_logits)}")
    
    # Choose aggregator
    if agg == "clustered":
        ell_hat, (lo_l, hi_l), diag = aggregate_clustered(by_tpl, B=2000)
        stability_basis = [float(np.mean(v)) for v in by_tpl.values()]
    else:
        ell_hat, (lo_l, hi_l), diag = aggregate_simple(all_logits, B=1000)
        stability_basis = all_logits
    
    p_hat = _sigmoid(ell_hat)
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)
    
    # Stability score
    iqr_l = float(np.percentile(stability_basis, 75) - np.percentile(stability_basis, 25))
    stability = 1.0 / (1.0 + iqr_l)
    
    # Stable run id for provenance
    digest = hashlib.sha256(
        f"{claim_text}|{model}|{PROMPT_VERSION}|K={K}|R={R}".encode("utf-8")
    ).hexdigest()[:12]
    
    return {
        "run_id": f"rpl-g5-{digest}",
        "claim": claim_text,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "sampling": {"K": K, "R": R, "N": len(all_logits)},
        "decoding": {
            "max_output_tokens": GPT5_PARAMS["max_output_tokens"],
            "reasoning_effort": "minimal",
            "verbosity": "low"
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
        "paraphrase_balance": diag if agg == "clustered" else {"method": "simple_mean"},
        "raw_logits": all_logits  # For debugging/analysis
    }

def evaluate_rpl(claim_text: str, model: str, k: int = 5, seed: int | None = None, r: int = 1, agg: str = "clustered"):
    """Main evaluation function - routes to GPT-5 or legacy based on model."""
    if model.startswith("gpt-5"):
        # Use GPT-5 implementation with K×R sampling
        return evaluate_rpl_gpt5(claim_text, model, K=k, R=r, agg=agg)
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