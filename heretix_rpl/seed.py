"""
Deterministic Seed Generation for Bootstrap Reproducibility

This module creates reproducible random number generator seeds from run configuration.
The same inputs always produce the same seed, ensuring identical confidence intervals
across runs while allowing seeds to change when configuration changes meaningfully.
"""
from __future__ import annotations                           # Enable forward type references
import hashlib                                               # Cryptographic hashing functions
from typing import Iterable                                  # Type hint for iterables

def make_bootstrap_seed(                                     # Create deterministic seed from config
    claim: str,                                              # The claim being evaluated
    model: str,                                              # Model identifier (e.g., gpt-5)
    prompt_version: str,                                     # Prompt template version
    k: int,                                                  # Number of paraphrase slots
    r: int,                                                  # Replicates per paraphrase
    template_hashes: Iterable[str],                          # Hashes of actual templates used
    center: str = "trimmed",                                 # Aggregation center method
    trim: float = 0.2,                                       # Trim percentage for robust center
    B: int = 5000,                                           # Bootstrap iterations
) -> int:                                                    # Returns 64-bit integer seed
    """
    Deterministic 64-bit seed from run config. Sort template hashes so order doesn't matter.
    """
    canon = "|".join([                                       # Create canonical config string
        "RPL-G5",                                            # Fixed prefix for this system
        f"model={model}",                                    # Model name and version
        f"prompt={prompt_version}",                          # Prompt template version
        f"claim={claim}",                                    # The actual claim text
        f"K={k}",                                            # Number of paraphrase slots
        f"R={r}",                                            # Replicates per slot
        f"center={center}",                                  # Center aggregation method
        f"trim={trim}",                                      # Trim percentage
        f"B={B}",                                            # Bootstrap iterations
        "templates=" + ",".join(sorted(set(template_hashes))), # Sorted unique template hashes
    ])
    h = hashlib.sha256(canon.encode("utf-8")).digest()       # Hash the canonical string to bytes
    return int.from_bytes(h[:8], "big")                      # Convert first 8 bytes to 64-bit int