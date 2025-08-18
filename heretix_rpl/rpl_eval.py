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

DECODING = {
    "temperature": 0.0,
    "top_p": 1.0,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "max_output_tokens": 640,  # Responses API uses max_output_tokens
}

def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1-1e-6)
    return np.log(p/(1-p))

def _sigmoid(x: float) -> float:
    return float(1/(1+np.exp(-x)))

def call_rpl_once(claim_text: str, paraphrase_prompt: str, model: str, seed: int | None = None):
    # Compose instructions + input
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

def evaluate_rpl(claim_text: str, model: str, k: int = 5, seed: int | None = None):
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