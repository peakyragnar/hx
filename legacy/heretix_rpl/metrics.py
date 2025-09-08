"""
Stability Metrics with Calibrated Scoring

Separates raw IQR measurements from business interpretation via parametric mapping.
Uses 1/(1+(IQR/s)^α) to ensure IQR=0.2 maps to medium stability (0.5).
Provides categorical bands (high/medium/low) for business logic.
"""
from __future__ import annotations                           # Enable forward type references
import numpy as np                                           # Numerical computations
from typing import Union, List                               # Type annotations


def stability_from_iqr(iqr_logit: float, s: float = 0.2, alpha: float = 1.7) -> float:  # Convert IQR to calibrated stability
    """
    Parametric stability mapping: 1/(1+(IQR/s)^α) with calibrated parameters.
    
    Args:
        iqr_logit: Interquartile range in logit space
        s: Midpoint parameter - IQR=0.2 maps to stability=0.5 (chosen for business semantics)
        alpha: Steepness parameter - controls falloff rate (1.7 gives good high/medium/low separation)
    """
    iqr = max(0.0, float(iqr_logit))                        # Ensure non-negative IQR
    s_safe = max(s, 1e-12)                                  # Avoid division by zero
    alpha_safe = max(alpha, 1e-6)                           # Ensure positive exponent
    return 1.0 / (1.0 + (iqr / s_safe) ** alpha_safe)       # Calibrated stability mapping


def stability_band_from_iqr(                               # Categorize IQR into stability bands
    iqr_logit: float,                                       # IQR in logit space
    high_max: float = 0.05,                                 # Threshold for high stability band
    medium_max: float = 0.30                                # Threshold for medium stability band
) -> str:                                                   # Returns categorical band
    """Categorize IQR into stability bands: high/medium/low."""  # Function purpose
    iqr = max(0.0, float(iqr_logit))                        # Ensure non-negative IQR
    if iqr <= high_max:                                     # Very tight spread
        return "high"                                       # High stability band
    elif iqr <= medium_max:                                 # Moderate spread  
        return "medium"                                     # Medium stability band
    else:                                                   # Wide spread
        return "low"                                        # Low stability band


def compute_stability_calibrated(logits: Union[List[float], np.ndarray]) -> tuple[float, float]:  # Compute calibrated stability from logits
    """Compute stability score and raw IQR from template means."""  # Function purpose  
    logits_arr = np.asarray(logits, dtype=float)            # Convert to numpy array
    iqr_logit = float(np.percentile(logits_arr, 75) - np.percentile(logits_arr, 25))  # Raw IQR measurement
    stability_score = stability_from_iqr(iqr_logit)         # Apply calibrated mapping
    return stability_score, iqr_logit                       # Return both score and raw IQR