"""
Core Evaluation Engine for Raw Prior Lens (RPL) Assessment

Main RPL evaluation system supporting GPT-5 (Responses API) and GPT-4 (Chat API).
Handles K×R sampling, API calls, statistical aggregation, and result formatting.
Provides calibrated stability scoring and comprehensive provenance tracking.
"""
import json, time, hashlib, os, logging                     # Standard libraries for data, timing, hashing, environment, logging
import numpy as np                                           # Numerical computations and statistics
from collections import defaultdict                         # Default dictionaries for grouping
from typing import Optional                                  # Type hints
from openai import OpenAI                                   # OpenAI API client
from heretix_rpl.rpl_schema import RPL_JSON_SCHEMA          # JSON schema for structured outputs
from heretix_rpl.rpl_prompts import SYSTEM_RPL, USER_TEMPLATE, PARAPHRASES, PROMPT_VERSION  # Prompt templates
from heretix_rpl.aggregation import aggregate_clustered, aggregate_simple  # Statistical aggregation methods
from heretix_rpl.seed import make_bootstrap_seed            # Deterministic seed generation
from heretix_rpl.config import load_config, RPLConfig        # Configuration management

client = None                                               # Global OpenAI client singleton

# Configure logging for this module
logging.getLogger(__name__).addHandler(logging.NullHandler())

def get_client():                                           # Get or create OpenAI client
    global client                                            # Access global client variable
    if client is None:                                       # Create client if doesn't exist
        client = OpenAI()                                    # Initialize with API key from environment
    return client                                            # Return the client instance

# GPT-5 uses Responses API with different parameters
GPT5_PARAMS = {                                             # Configuration for GPT-5 Responses API
    "max_output_tokens": 1024,                              # Token limit (increased for reasoning models)
    "reasoning_effort": "minimal",                          # Reduce variance and cost
    "verbosity": "low"                                      # Keep outputs terse for JSON parsing
}

# Legacy GPT-4 settings (kept for reference)
DECODING = {                                                # Configuration for legacy Chat API models
    "temperature": 0.0,                                     # Deterministic sampling (no randomness)
    "top_p": 1.0,                                           # Consider all tokens (nucleus sampling disabled)
    "presence_penalty": 0.0,                                # No penalty for token presence
    "frequency_penalty": 0.0,                               # No penalty for token frequency
    "max_output_tokens": 640,                               # Output token limit for legacy models
}

def _logit(p: float) -> float:                               # Convert probability to log-odds
    p = min(max(p, 1e-6), 1-1e-6)                           # Clamp to avoid log(0) or log(inf)
    return np.log(p/(1-p))                                   # Return log-odds transformation

def _sigmoid(x: float) -> float:                            # Convert log-odds back to probability
    """Convert log-odds to probability, with overflow protection."""  # Function purpose
    x = np.clip(x, -709, 709)                                # Prevent exp overflow while preserving precision
    return float(1/(1+np.exp(-x)))                           # Sigmoid function (inverse of logit)

def median_of_means(logits, buckets=5):                     # Robust aggregation using median-of-means
    """Robust aggregation using median-of-means in log-odds space."""  # Function purpose
    n = len(logits)                                          # Number of logit values
    if n < buckets:                                          # Not enough data for bucketing
        return float(np.mean(logits))                        # Fall back to simple mean
    # Randomly permute and split into buckets
    chunks = np.array_split(np.random.permutation(logits), buckets)  # Split into equal chunks
    means = [float(np.mean(c)) for c in chunks]             # Compute mean of each chunk
    return float(np.median(means))                           # Return median of chunk means

def bootstrap_ci_logits(logits, B=1000, alpha=0.05):       # Bootstrap confidence intervals
    """Bootstrap confidence intervals in log-odds space."""   # Function purpose
    logits = np.array(logits, dtype=float)                   # Convert to numpy array
    n = len(logits)                                          # Number of samples
    # Bootstrap sampling
    idx = np.random.randint(0, n, size=(B, n))               # Generate B bootstrap sample indices
    means = np.mean(logits[idx], axis=1)                     # Compute mean for each bootstrap sample
    # Compute percentiles
    lo = np.percentile(means, 100*alpha/2)                   # Lower confidence bound
    hi = np.percentile(means, 100*(1-alpha/2))               # Upper confidence bound
    return float(lo), float(hi)                              # Return confidence interval bounds

def compute_stability(logits):                              # Compute stability score from logit spread
    """Compute stability score based on IQR of logits (legacy)."""  # Function purpose
    # Legacy function kept for backward compatibility
    # New code should use compute_stability_calibrated from metrics module
    from heretix_rpl.metrics import compute_stability_calibrated
    stability, _ = compute_stability_calibrated(logits)      # Use calibrated version
    return stability                                         # Return stability score (0-1)

def call_rpl_once_gpt5(claim_text: str, paraphrase_prompt: str, model: str = "gpt-5"):  # Single GPT-5 API call
    """                                                      # Function documentation
    GPT-5 via Responses API + Structured Outputs (JSON Schema).
    No temperature/top_p/penalties — treat model as stochastic and sample multiple times.
    """
    client = get_client()                                    # Get OpenAI client instance
    
    # Build a single, clear user message: paraphrase + schema request, with the claim once.
    paraphrased = paraphrase_prompt.replace("{CLAIM}", claim_text)  # Insert claim into paraphrase template
    user_text = f"{paraphrased}\n\n" + USER_TEMPLATE.replace("{CLAIM}", claim_text)  # Combine paraphrase with user template
    
    # Since Responses API doesn't support response_format, embed schema in instructions
    schema_instructions = """                                # JSON schema as text (Responses API workaround)
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
    
    full_instructions = SYSTEM_RPL + "\n\n" + schema_instructions  # Combine system prompt with schema instructions
    
    # Create a reproducible prompt hash for provenance
    prompt_sha256 = hashlib.sha256(                          # Hash the complete prompt for template identification
        (full_instructions + "\n\n" + user_text).encode("utf-8")  # Encode full prompt as bytes
    ).hexdigest()                                            # Get hexadecimal hash string
    
    # Responses API call - no response_format or verbosity (not supported)
    try:                                                     # Try with reasoning parameter first
        resp = client.responses.create(                      # Make Responses API call
            model=model,                                     # Model identifier (e.g., "gpt-5")
            instructions=full_instructions,                  # System prompt with embedded schema
            input=[{                                         # Input message structure
                "role": "user",                              # User role for input
                "content": [{"type": "input_text", "text": user_text}]  # Text content wrapper
            }],
            max_output_tokens=1024,                          # Token limit for response
            reasoning={"effort": "minimal"}                 # Minimize reasoning variance and cost
        )
    except Exception as e:                                   # Handle API parameter errors
        if "reasoning" in str(e):                            # Check if reasoning parameter caused error
            # Feature detection: retry without reasoning parameter
            resp = client.responses.create(                  # Retry without reasoning parameter
                model=model,                                 # Same model
                instructions=full_instructions,              # Same instructions
                input=[{                                     # Same input structure
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}]
                }],
                max_output_tokens=1024                       # Same token limit
            )
        else:                                                # Re-raise other exceptions
            raise
    
    # Extract JSON from Responses API output
    # The response has output[0]=reasoning, output[1]=message with the JSON text
    try:                                                     # Parse response JSON
        # First try the convenient output_text helper
        if hasattr(resp, 'output_text') and resp.output_text:  # Check for output_text helper
            obj = json.loads(resp.output_text)               # Parse JSON from helper
        else:                                                # Manual extraction from response structure
            # Find the message item (usually at index 1)
            obj = None                                       # Initialize result object
            for item in resp.output:                         # Iterate through response output items
                if item.type == "message" and hasattr(item, 'content'):  # Find message item
                    for content in item.content:             # Iterate through content array
                        if hasattr(content, 'text'):         # Find text content
                            obj = json.loads(content.text)   # Parse JSON from text
                            break                            # Exit inner loop
                    if obj:                                  # Exit outer loop if found
                        break
            
            if obj is None:                                  # Check if JSON was found
                raise ValueError("No message with JSON text found in response")  # Raise error if not found
    except json.JSONDecodeError as e:                        # Handle JSON parsing errors
        raise ValueError(f"Invalid JSON in response: {e}")  # Re-raise with context
    except Exception as e:                                   # Handle other extraction errors
        raise ValueError(f"Failed to extract JSON from Responses API: {e}")  # Re-raise with context
    
    return {                                                 # Return structured response
        "model": resp.model,                                    # Model that generated response
        "raw": obj,                                             # Parsed JSON response object
        "meta": {                                               # Metadata for provenance
            "response_id": resp.id,                             # API response identifier
            "created": getattr(resp, 'created_at', None),       # Response timestamp (Responses API format)
            "provider_model_id": resp.model,                   # Provider's model identifier
            "prompt_version": PROMPT_VERSION,                  # Prompt template version used
            "prompt_sha256": prompt_sha256                     # Hash of complete prompt
        }
    }

def call_rpl_once(claim_text: str, paraphrase_prompt: str, model: str, seed: int | None = None):  # Legacy API call
    """Legacy GPT-4 implementation - kept for compatibility."""  # Function purpose
    instructions = SYSTEM_RPL                                # Use system prompt for instructions
    # Use paraphrase if provided, otherwise use the template
    if "{CLAIM}" in paraphrase_prompt:                        # Check if paraphrase template provided
        user_text = paraphrase_prompt.replace("{CLAIM}", claim_text) + "\n\n" + USER_TEMPLATE.replace("{CLAIM}", claim_text)  # Combine paraphrase and template
    else:                                                    # No paraphrase template
        user_text = USER_TEMPLATE.replace("{CLAIM}", claim_text)  # Use base template only

    # Build ChatCompletion request with structured outputs
    messages = [                                             # Chat API message format
        {"role": "system", "content": instructions},         # System instructions
        {"role": "user", "content": user_text}               # User query with claim
    ]
    
    req = dict(                                              # Build request parameters
        model=model,                                         # Model identifier
        messages=messages,                                   # Message history
        response_format={"type": "json_schema", "json_schema": RPL_JSON_SCHEMA},  # Structured output schema
        temperature=DECODING["temperature"],                 # Sampling temperature (0.0 = deterministic)
        top_p=DECODING["top_p"],                             # Nucleus sampling parameter
        presence_penalty=DECODING["presence_penalty"],       # Penalty for token presence
        frequency_penalty=DECODING["frequency_penalty"],     # Penalty for token frequency
        max_tokens=DECODING["max_output_tokens"]             # Output token limit
    )
    if seed is not None:                                     # Add seed if provided
        req["seed"] = seed                                   # Deterministic seed for reproducibility

    resp = get_client().chat.completions.create(**req)       # Make Chat API call

    # Parse the JSON response
    try:                                                     # Parse structured JSON response
        obj = json.loads(resp.choices[0].message.content)    # Extract JSON from first choice
    except Exception as e:                                   # Handle parsing errors
        raise ValueError(f"Failed to parse JSON response: {e}")  # Re-raise with context

    return {                                                 # Return structured response
        "model": resp.model,                                 # Model that generated response
        "raw": obj,                                          # Parsed JSON response object
        "meta": {                                            # Metadata for provenance
            "provider_model_id": resp.model,                # Provider's model identifier
            "prompt_version": PROMPT_VERSION                 # Prompt template version used
        }
    }

def evaluate_rpl_gpt5(claim_text: str, model: str = "gpt-5", K: int = 7, R: int = 3, agg: str = "clustered", config: Optional[RPLConfig] = None):  # GPT-5 evaluation
    """GPT-5 evaluation with K×R sampling and robust aggregation."""  # Function purpose
    if config is None:                                           # Load config if not provided
        config = load_config()                                   # Use environment-driven configuration
    runs = []                                                # Store individual API responses
    all_logits = []                                          # All logit values for simple aggregation
    by_tpl = {}                                              # Logits grouped by template hash
    tpl_hashes = []                                          # List of template hashes for seeding
    
    # K paraphrases × R replicates
    for k in range(K):                                       # Iterate through paraphrase slots
        phr = PARAPHRASES[k % len(PARAPHRASES)]              # Cycle through available paraphrases
        for r in range(R):                                   # Replicates per paraphrase
            try:                                             # Attempt API call
                out = call_rpl_once_gpt5(claim_text, phr, model)  # Single GPT-5 evaluation
                p = out["raw"]["prob_true"]                  # Extract probability from response
                l = _logit(p)                                # Convert to log-odds
                h = out["meta"]["prompt_sha256"]             # Get template hash for clustering
                runs.append({                                # Store complete run data
                    **out,                                   # Include all response data
                    "paraphrase_idx": k,                     # Paraphrase slot index
                    "replicate_idx": r                       # Replicate index within slot
                })
                all_logits.append(l)                         # Add to overall logit list
                tpl_hashes.append(h)                         # Add template hash
                by_tpl.setdefault(h, []).append(l)           # Group logits by template hash
            except Exception as e:                           # Handle API failures
                logging.getLogger(__name__).warning("Failed sample k=%s, r=%s: %s", k, r, e)  # Log warning
                continue                                     # Continue with next sample
    
    if len(all_logits) < config.min_samples:                 # Check minimum sample requirement from config
        raise ValueError(f"Too few successful samples: {len(all_logits)} < {config.min_samples}")  # Raise error if insufficient data
    
    # Decide the bootstrap seed
    env_seed = os.getenv("HERETIX_RPL_SEED")                 # Check for environment override
    if env_seed is not None:                                 # Use environment seed if provided
        seed_val = int(env_seed)                             # Convert to integer
    else:                                                    # Generate deterministic seed
        seed_val = make_bootstrap_seed(                      # Create reproducible seed
            claim=claim_text,                                # Claim text
            model=model,                                     # Model identifier
            prompt_version=PROMPT_VERSION,                   # Prompt version
            k=K, r=R,                                        # Sampling parameters
            template_hashes=tpl_hashes,                      # Template hashes used
            center="trimmed", trim=config.trim, B=config.b_clustered  # Aggregation parameters from config
        )
    rng = np.random.default_rng(seed_val)                    # Initialize random number generator
    
    # Choose aggregator
    if agg == "clustered":                                   # Use robust clustered aggregation
        ell_hat, (lo_l, hi_l), diag = aggregate_clustered(   # Call clustered aggregation
            by_template_logits=by_tpl,                       # Logits grouped by template
            B=config.b_clustered,                            # Bootstrap iterations from config
            rng=rng,                                         # Deterministic RNG
            center="trimmed",                                # Use trimmed mean
            trim=config.trim,                                # Trimming from config
            fixed_m=None                                     # No fixed resample size
        )
        stability_basis = [float(np.mean(v)) for v in by_tpl.values()]  # Template means for stability
    else:                                                    # Use simple aggregation
        ell_hat, (lo_l, hi_l), diag = aggregate_simple(all_logits, B=config.b_simple)  # Call simple aggregation
        stability_basis = all_logits                         # Use all logits for stability
    
    p_hat = _sigmoid(ell_hat)                                # Convert logit estimate to probability
    lo_p, hi_p = _sigmoid(lo_l), _sigmoid(hi_l)              # Convert CI bounds to probabilities
    
    # Stability score using calibrated metrics
    from heretix_rpl.metrics import compute_stability_calibrated, stability_band_from_iqr
    stability, iqr_l = compute_stability_calibrated(stability_basis)  # Get calibrated score and raw IQR
    stability_band = stability_band_from_iqr(iqr_l)          # Get categorical band
    
    # Stable run id for provenance
    digest = hashlib.sha256(                                 # Create reproducible run identifier
        f"{claim_text}|{model}|{PROMPT_VERSION}|K={K}|R={R}".encode("utf-8")  # Hash run parameters
    ).hexdigest()[:12]                                       # Take first 12 characters
    
    # Include aggregation config and seed in output
    aggregation_info = {                                     # Aggregation metadata for reproducibility
        "method": diag.get("method", "equal_by_template_cluster_bootstrap_trimmed"),  # Aggregation method used
        "B": config.b_clustered if agg == "clustered" else config.b_simple,  # Bootstrap iterations from config
        "center": "trimmed" if agg == "clustered" else "mean",  # Center method
        "trim": config.trim if agg == "clustered" else 0.0,  # Trim percentage from config
        "min_samples": config.min_samples,                    # Minimum samples threshold from config
        "stability_width": config.stability_width,            # Stability threshold from config
        "bootstrap_seed": seed_val if agg == "clustered" else None,  # Seed for reproducibility
        "n_templates": diag.get("n_templates"),              # Number of unique templates
        "counts_by_template": diag.get("counts_by_template"), # Samples per template
        "imbalance_ratio": diag.get("imbalance_ratio"),       # Template imbalance ratio
        "template_iqr_logit": diag.get("template_iqr_logit")  # Template spread in logit space
    }
    
    return {                                                 # Return complete evaluation results
        "run_id": f"rpl-g5-{digest}",                          # Unique run identifier
        "claim": claim_text,                                    # Original claim text
        "model": model,                                         # Model used for evaluation
        "prompt_version": PROMPT_VERSION,                      # Prompt template version
        "sampling": {"K": K, "R": R, "N": len(all_logits)},    # Sampling configuration
        "decoding": {                                           # Decoding parameters used
            "max_output_tokens": GPT5_PARAMS["max_output_tokens"],  # Token limit
            "reasoning_effort": "minimal",                      # Reasoning effort level
            "verbosity": "low"                                  # Output verbosity
        },
        "aggregation": aggregation_info,                       # Aggregation method details
        "timestamp": int(time.time()),                         # Unix timestamp
        "aggregates": {                                         # Main results
            "prob_true_rpl": p_hat,                             # Final probability estimate
            "ci95": [lo_p, hi_p],                               # 95% confidence interval
            "ci_width": hi_p - lo_p,                            # Confidence interval width
            "paraphrase_iqr_logit": iqr_l,                      # Raw IQR in logit space (measurement)
            "stability_score": stability,                       # Calibrated stability score (0-1)
            "stability_band": stability_band,                   # Categorical band (high/medium/low)
            "is_stable": (hi_p - lo_p) <= config.stability_width  # Stability flag from config
        },
        "paraphrase_results": runs,                            # Individual API responses
        "paraphrase_balance": diag if agg == "clustered" else {"method": "simple_mean"},  # Balance diagnostics
        "raw_logits": all_logits                               # Raw logit values for analysis
    }

def evaluate_rpl(claim_text: str, model: str, k: int = 5, seed: int | None = None, r: int = 1, agg: str = "clustered"):  # Main evaluation entry point
    """Main evaluation function - routes to GPT-5 or legacy based on model."""  # Function purpose
    if model.startswith("gpt-5"):                            # Check if using GPT-5
        # Use GPT-5 implementation with K×R sampling
        return evaluate_rpl_gpt5(claim_text, model, K=k, R=r, agg=agg)  # Call GPT-5 evaluator
    else:                                                    # Use legacy implementation
        # Legacy implementation for GPT-4 and others
        runs = []                                            # Store API responses
        for i in range(k):                                   # k paraphrases (legacy mode)
            runs.append(call_rpl_once(claim_text, PARAPHRASES[i % len(PARAPHRASES)], model, seed))  # Single API call per paraphrase

        probs = [r["raw"]["prob_true"] for r in runs]           # Extract probabilities from responses
        logits = [_logit(p) for p in probs]                      # Convert to log-odds
        mean_logit = float(np.mean(logits))                      # Mean in logit space
        var_logit = float(np.var(logits, ddof=1)) if len(logits) > 1 else 0.0  # Logit variance (sample)
        p_rpl = _sigmoid(mean_logit)                             # Convert back to probability

        # Stable run id for provenance
        digest = hashlib.sha256(                                 # Create reproducible run ID
            f"{claim_text}|{model}|{PROMPT_VERSION}|{k}".encode("utf-8")  # Hash run parameters
        ).hexdigest()[:12]                                       # Take first 12 characters

        return {                                                 # Return legacy format results
            "run_id": f"rpl-{digest}",                          # Run identifier
            "claim": claim_text,                                # Original claim
            "model": model,                                     # Model identifier
            "prompt_version": PROMPT_VERSION,                  # Prompt version
            "decoding": DECODING,                               # Decoding parameters used
            "k": k,                                             # Number of paraphrases
            "timestamp": int(time.time()),                     # Unix timestamp
            "paraphrase_results": runs,                        # Individual responses
            "aggregates": {                                     # Aggregated results
                "prob_true_rpl": p_rpl,                         # Final probability estimate
                "logit_variance": var_logit                     # Variance in logit space
            }
        }