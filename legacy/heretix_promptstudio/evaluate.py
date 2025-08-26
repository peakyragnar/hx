"""
Standalone evaluator for Prompt Studio that calls GPT-5 via the Responses API
and uses production aggregation. Matches production behavior: embed schema in
instructions, feature-detect reasoning effort, aggregate in logit space, and
compute cluster bootstrap CIs with deterministic seeds.
"""

import json
import hashlib
import time
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import numpy as np
import yaml

# Import production components
from heretix_rpl.aggregation import aggregate_clustered
from heretix_rpl.seed import make_bootstrap_seed
from heretix_rpl.rpl_prompts import PARAPHRASES, USER_TEMPLATE, PROMPT_VERSION
from heretix_rpl.rpl_schema import RPL_JSON_SCHEMA
from heretix_rpl.config import load_config

# Import OpenAI client (reuse production approach)
from openai import OpenAI


class StandaloneEvaluator:
    """Evaluator for testing SYSTEM_RPL variants with production parity."""
    
    def __init__(self, system_prompt: str, session_seed: Optional[int] = None):
        """
        Initialize evaluator with custom system prompt.
        
        Args:
            system_prompt: The SYSTEM_RPL variant to test
            session_seed: Fixed seed for reproducibility within session
        """
        self.system_prompt = system_prompt
        self.paraphrases = PARAPHRASES  # Use production paraphrases
        self.user_template = USER_TEMPLATE  # Use production user template
        self.session_seed = session_seed
        self.client = OpenAI()  # Will use OPENAI_API_KEY from environment
        self.config = load_config()  # Load production config for parameters
        
        # Track provider model for drift detection
        self.provider_model_id = None
        
    def evaluate_claim(
        self,
        claim: str,
        K: int = 8,
        R: int = 2,
        model: str = "gpt-5"
    ) -> Dict[str, Any]:
        """
        Evaluate a single claim with K×R sampling.
        
        Args:
            claim: The claim to evaluate
            K: Number of paraphrase slots
            R: Replicates per paraphrase
            model: Model to use
            
        Returns:
            Full evaluation result with aggregated metrics
        """
        T = len(self.paraphrases)
        
        # Deterministic balanced sampling with rotation
        offset = self._compute_rotation_offset(claim, model, T)
        template_order = self._balanced_indices_with_rotation(T, K, offset)
        
        # Collect samples
        samples = []
        by_template = defaultdict(list)  # For aggregation
        template_hashes = []
        
        for k_idx in range(K):
            template_idx = template_order[k_idx]
            paraphrase = self.paraphrases[template_idx]
            
            # Compute prompt hash (full instructions + user text), matching production
            paraphrased = paraphrase.replace("{CLAIM}", claim)
            user_text_hash = f"{paraphrased}\n\n{self.user_template.replace('{CLAIM}', claim)}"
            schema_instructions_hash = (
                "Return ONLY valid JSON with exactly these fields:\n"
                "{\n"
                "  \"prob_true\": number between 0 and 1,\n"
                "  \"confidence_self\": number between 0 and 1,\n"
                "  \"assumptions\": array of strings,\n"
                "  \"reasoning_bullets\": array of 3-6 strings,\n"
                "  \"contrary_considerations\": array of 2-4 strings,\n"
                "  \"ambiguity_flags\": array of strings\n"
                "}\n"
            )
            full_system_hash = self.system_prompt + "\n\n" + schema_instructions_hash
            prompt_hash = hashlib.sha256((full_system_hash + "\n\n" + user_text_hash).encode()).hexdigest()
            
            for r_idx in range(R):
                # Call GPT-5
                response = self._call_gpt5(claim, paraphrase, model)
                
                if response:
                    samples.append({
                        "paraphrase_idx": k_idx,
                        "template_idx": template_idx,
                        "replicate_idx": r_idx,
                        "raw": response["parsed"],
                        "raw_text": response.get("raw_text"),
                        "meta": {
                            "prompt_sha256": prompt_hash,
                            "provider_model_id": response.get("provider_model_id"),
                            "response_id": response.get("response_id"),
                            "created": response.get("created", time.time())
                        }
                    })
                    
                    # Store for aggregation
                    prob_true = response["parsed"].get("prob_true", 0.5)
                    logit = self._logit(prob_true)
                    by_template[prompt_hash].append(logit)
                    template_hashes.append(prompt_hash)
                    
                    # Track provider model
                    if self.provider_model_id is None:
                        self.provider_model_id = response.get("provider_model_id")
                    elif self.provider_model_id != response.get("provider_model_id"):
                        print(f"WARNING: Provider model changed mid-evaluation!")
        
        # Aggregate using production method
        aggregates, agg_info = self._aggregate_results(claim, model, by_template, template_hashes, K, R)
        
        # Build result
        result = {
            "claim": claim,
            "model": model,
            "sampling": {"K": K, "R": R, "N": len(samples), "T": T},
            "samples": samples,
            "aggregates": aggregates,
            "aggregation": agg_info,
            "provider_model_id": self.provider_model_id,
            "timestamp": int(time.time())
        }
        
        return result
    
    def _call_gpt5(self, claim: str, paraphrase: str, model: str) -> Optional[Dict[str, Any]]:
        """
        Call GPT-5 (Responses API) with the test system prompt.
        Returns parsed response or None if failed/invalid.
        """
        # Build user message
        paraphrased = paraphrase.replace("{CLAIM}", claim)
        user_text = f"{paraphrased}\n\n{self.user_template.replace('{CLAIM}', claim)}"

        # Embed schema in system instructions (Responses API)
        schema_instructions = (
            "Return ONLY valid JSON with exactly these fields:\n"
            "{\n"
            "  \"prob_true\": number between 0 and 1,\n"
            "  \"confidence_self\": number between 0 and 1,\n"
            "  \"assumptions\": array of strings,\n"
            "  \"reasoning_bullets\": array of 3-6 strings,\n"
            "  \"contrary_considerations\": array of 2-4 strings,\n"
            "  \"ambiguity_flags\": array of strings\n"
            "}\n"
            "Output ONLY the JSON object, no other text."
        )
        full_system = self.system_prompt + "\n\n" + schema_instructions

        try:
            # Try with reasoning parameter first
            try:
                resp = self.client.responses.create(
                    model=model,
                    instructions=full_system,
                    input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
                    max_output_tokens=1024,
                    reasoning={"effort": "minimal"}
                )
            except Exception as e:
                if "reasoning" in str(e):
                    # Retry without reasoning field
                    resp = self.client.responses.create(
                        model=model,
                        instructions=full_system,
                        input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
                        max_output_tokens=1024
                    )
                else:
                    raise

            # Extract text from response
            raw_text = None
            if hasattr(resp, "output_text") and resp.output_text:
                raw_text = resp.output_text
            else:
                parts = []
                for item in getattr(resp, "output", []) or []:
                    try:
                        content = item.get("content") if isinstance(item, dict) else None
                        if content and isinstance(content, list):
                            txt = content[0].get("text")
                            if txt:
                                parts.append(txt)
                    except Exception:
                        continue
                raw_text = "\n".join(parts) if parts else None

            if not raw_text:
                return None

            # Parse JSON strictly: exactly one object, no extra prose
            json_str, json_only_ok = self._extract_single_json_object(raw_text)
            if not json_str or not json_only_ok:
                return None

            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                return None

            if "prob_true" not in parsed:
                return None

            return {
                "parsed": parsed,
                "raw_text": raw_text,
                "provider_model_id": getattr(resp, "model", model),
                "response_id": getattr(resp, "id", None),
                "created": getattr(resp, "created", time.time())
            }
        except Exception as e:
            print(f"API call failed: {e}")
            return None
    
    def _compute_rotation_offset(self, claim: str, model: str, T: int) -> int:
        """Compute deterministic rotation offset for balanced sampling."""
        # Use production PROMPT_VERSION for consistency
        seed_str = f"{claim}|{model}|{PROMPT_VERSION}"
        seed_bytes = hashlib.sha256(seed_str.encode()).digest()
        return int.from_bytes(seed_bytes[:8], 'big') % T
    
    def _balanced_indices_with_rotation(self, T: int, K: int, offset: int) -> List[int]:
        """Generate balanced template indices with rotation."""
        # Start with range(T)
        order = list(range(T))
        
        # Apply rotation
        if T > 1 and offset % T != 0:
            rot = offset % T
            order = order[rot:] + order[:rot]
        
        # Distribute K slots as evenly as possible
        base = K // T
        rem = K % T
        
        result = []
        for t_idx in range(T):
            count = base + (1 if t_idx < rem else 0)
            result.extend([order[t_idx]] * count)
        
        return result[:K]
    
    def _logit(self, p: float) -> float:
        """Convert probability to log-odds."""
        p = min(max(p, 1e-6), 1-1e-6)
        return np.log(p/(1-p))
    
    def _sigmoid(self, x: float) -> float:
        """Convert log-odds to probability."""
        x = np.clip(x, -709, 709)
        return float(1/(1+np.exp(-x)))
    
    def _aggregate_results(
        self,
        claim: str,
        model: str,
        by_template: Dict[str, List[float]],
        template_hashes: List[str],
        K: int,
        R: int
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Aggregate results using production method.
        
        Returns (aggregates, aggregation_info).
        """
        # Use session seed if available, otherwise generate deterministic seed
        if self.session_seed:
            seed_val = self.session_seed
        else:
            env_seed = os.getenv("HERETIX_RPL_SEED")
            if env_seed:
                seed_val = int(env_seed)
            else:
                uniq_hashes = sorted(set(template_hashes))
                seed_val = make_bootstrap_seed(
                    claim=claim,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    k=K, r=R,
                    template_hashes=uniq_hashes,
                    center="trimmed",
                    trim=self.config.trim,
                    B=self.config.b_clustered
                )
        
        # Create RNG
        rng = np.random.default_rng(seed_val)
        
        # Call production aggregation
        ell_hat, (lo_l, hi_l), diag = aggregate_clustered(
            by_template,
            B=self.config.b_clustered,
            rng=rng,
            center="trimmed",
            trim=self.config.trim,
            fixed_m=None
        )
        
        # Convert to probability
        p_hat = self._sigmoid(ell_hat)
        lo_p, hi_p = self._sigmoid(lo_l), self._sigmoid(hi_l)
        
        # Compute stability
        from heretix_rpl.metrics import compute_stability_calibrated, stability_band_from_iqr
        
        template_means = [float(np.mean(v)) for v in by_template.values()] if by_template else []
        stability, iqr_l = compute_stability_calibrated(template_means)
        band = stability_band_from_iqr(iqr_l)
        
        aggregates = {
            "prob_true_rpl": p_hat,
            "ci95": [lo_p, hi_p],
            "ci_width": hi_p - lo_p,
            "paraphrase_iqr_logit": iqr_l,
            "stability_score": stability,
            "stability_band": band,
            "is_stable": (hi_p - lo_p) <= self.config.stability_width
        }
        
        agg_info = {
            "method": diag.get("method", "equal_by_template_cluster_bootstrap_trimmed"),
            "B": self.config.b_clustered,
            "center": "trimmed",
            "trim": self.config.trim,
            "bootstrap_seed": seed_val,
            "n_templates": len(by_template),
            "counts_by_template": {k: len(v) for k, v in by_template.items()},
            "imbalance_ratio": diag.get("imbalance_ratio", 1.0),
            "template_iqr_logit": iqr_l
        }
        
        return aggregates, agg_info

    def _extract_single_json_object(self, text: str) -> Tuple[Optional[str], bool]:
        """Extract exactly one top-level JSON object and verify JSON-only output.

        Returns (json_str, json_only_ok). json_only_ok is True only when there is
        no non-whitespace outside the JSON object.
        """
        if text is None:
            return None, False
        s = text.strip()
        start = s.find('{')
        if start == -1:
            return None, False
        depth = 0
        end = -1
        for i, ch in enumerate(s[start:], start=start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            return None, False
        json_str = s[start:end+1]
        before = s[:start].strip()
        after = s[end+1:].strip()
        json_only_ok = (before == "" and after == "")
        return json_str, json_only_ok


def evaluate_benchmark(
    candidate_id: str,
    bench_path: Path,
    session_dir: Path,
    K: int = 8,
    R: int = 2,
    quick: bool = False
) -> Dict[str, Any]:
    """
    Evaluate a candidate on a full benchmark.
    
    Args:
        candidate_id: Candidate to evaluate
        bench_path: Path to benchmark YAML
        session_dir: Session directory
        K: Paraphrase slots
        R: Replicates
        quick: Use quick mode (K=5, R=1)
        
    Returns:
        Benchmark results with per-claim and aggregate metrics
    """
    if quick:
        K, R = 5, 1
    
    # Load candidate prompt
    candidate_dir = session_dir / candidate_id
    if not (candidate_dir / "prompt.txt").exists():
        raise ValueError(f"Candidate {candidate_id} prompt not found")
    
    prompt = (candidate_dir / "prompt.txt").read_text()
    
    # Load benchmark
    with open(bench_path) as f:
        bench_data = yaml.safe_load(f)
    
    claims = bench_data.get("claims", [])
    
    # Get session seed if available
    config_file = session_dir / "config.json"
    session_seed = None
    if config_file.exists():
        config = json.loads(config_file.read_text())
        session_seed = config.get("seed")
    
    # Create evaluator
    evaluator = StandaloneEvaluator(prompt, session_seed=session_seed)
    
    # Evaluate each claim
    results = []
    for claim_data in claims:
        claim_text = claim_data["claim"]
        tags = claim_data.get("tags", [])
        
        # Handle invariance pairs
        if "invariance_context" in claim_data:
            # Prepend irrelevant context
            claim_text = claim_data["invariance_context"] + " " + claim_text
        
        print(f"Evaluating: {claim_text[:50]}...")
        
        result = evaluator.evaluate_claim(claim_text, K=K, R=R)
        result["tags"] = tags
        result["claim_data"] = claim_data
        
        results.append(result)
        
        # Save per-claim result
        eval_dir = candidate_dir / "eval"
        eval_dir.mkdir(exist_ok=True)
        
        # Use claim hash as filename
        claim_hash = hashlib.sha256(claim_text.encode()).hexdigest()[:8]
        (eval_dir / f"{claim_hash}.json").write_text(json.dumps(result, indent=2))
    
    # Compute aggregate metrics
    aggregate_metrics = compute_benchmark_metrics(results)
    
    # Save benchmark results
    bench_results = {
        "candidate_id": candidate_id,
        "benchmark": str(bench_path),
        "sampling": {"K": K, "R": R},
        "n_claims": len(claims),
        "quick_mode": quick,
        "results": results,
        "aggregate_metrics": aggregate_metrics,
        "timestamp": int(time.time())
    }

    # Write generic and bench-specific files
    (candidate_dir / "benchmark_results.json").write_text(json.dumps(bench_results, indent=2))
    bench_stem = Path(bench_path).stem
    (candidate_dir / f"benchmark_results_{bench_stem}.json").write_text(json.dumps(bench_results, indent=2))

    return bench_results


def evaluate_benchmark_current(
    candidate_id: str,
    bench_path: Path,
    session_dir: Path,
    K: int = 8,
    R: int = 2,
    quick: bool = False
) -> Dict[str, Any]:
    """Evaluate the current production SYSTEM_RPL on a benchmark for comparison.

    Results are saved under the candidate directory as baseline_current_<bench>.json.
    """
    # Load production prompt
    from heretix_rpl.rpl_prompts import SYSTEM_RPL as PROD_SYSTEM_RPL

    # Load benchmark
    with open(bench_path) as f:
        bench_data = yaml.safe_load(f)

    claims = bench_data.get("claims", [])

    # Get session seed if available
    config_file = session_dir / "config.json"
    session_seed = None
    if config_file.exists():
        config = json.loads(config_file.read_text())
        session_seed = config.get("seed")

    evaluator = StandaloneEvaluator(PROD_SYSTEM_RPL, session_seed=session_seed)

    if quick:
        K, R = 5, 1

    results = []
    for claim_data in claims:
        claim_text = claim_data["claim"]
        # Apply invariance context if present
        if "invariance_context" in claim_data:
            claim_text = claim_data["invariance_context"] + " " + claim_text
        res = evaluator.evaluate_claim(claim_text, K=K, R=R)
        res["tags"] = claim_data.get("tags", [])
        res["claim_data"] = claim_data
        results.append(res)

    aggregate_metrics = compute_benchmark_metrics(results)

    bench_results = {
        "candidate_id": candidate_id,
        "benchmark": str(bench_path),
        "sampling": {"K": K, "R": R},
        "n_claims": len(claims),
        "quick_mode": quick,
        "results": results,
        "aggregate_metrics": aggregate_metrics,
        "timestamp": int(time.time()),
        "baseline": "current_production"
    }

    # Save under candidate folder
    cand_dir = session_dir / candidate_id
    cand_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(bench_path).stem
    (cand_dir / f"baseline_current_{stem}.json").write_text(json.dumps(bench_results, indent=2))

    return bench_results


def compute_benchmark_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate metrics across benchmark claims."""
    # Extract metrics
    ci_widths = []
    stabilities = []
    prob_values = []
    json_valid = []
    
    for r in results:
        aggs = r.get("aggregates", {})
        ci_widths.append(aggs.get("ci_width", 1.0))
        stabilities.append(aggs.get("stability_score", 0.0))
        prob_values.append(aggs.get("prob_true_rpl", 0.5))
        
        # Check if all samples had valid JSON
        samples = r.get("samples", [])
        if samples:
            valid_count = sum(1 for s in samples if s.get("raw"))
            json_valid.append(valid_count / len(samples))
    
    return {
        "median_ci_width": float(np.median(ci_widths)) if ci_widths else None,
        "median_stability": float(np.median(stabilities)) if stabilities else None,
        "mean_prob": float(np.mean(prob_values)) if prob_values else None,
        "json_validity_rate": float(np.mean(json_valid)) if json_valid else None,
        "n_claims_evaluated": len(results)
    }
