"""
Configuration module for Raw Prior Lens (RPL) evaluation.

This module provides environment-driven configuration with sensible defaults
for all configurable parameters in the RPL system.
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RPLConfig:
    """Configuration settings for RPL evaluation with environment variable overrides."""
    
    # Minimum number of successful samples required for aggregation
    min_samples: int = 3
    
    # Trim percentage for robust center calculation (20% = drop min/max)
    trim: float = 0.2
    
    # Bootstrap iterations for clustered aggregation (higher for smoother CIs)
    b_clustered: int = 5000
    
    # Bootstrap iterations for simple aggregation
    b_simple: int = 1000
    
    # CI width threshold for stability determination (probability space)
    # An estimate is considered stable when CI width <= stability_width
    stability_width: float = 0.2


def load_config() -> RPLConfig:
    """
    Load configuration from environment variables with fallback to defaults.
    
    Environment variables:
    - HERETIX_RPL_MIN_SAMPLES: Minimum successful samples (default: 3)
    - HERETIX_RPL_TRIM: Trim percentage for robust center (default: 0.2)
    - HERETIX_RPL_B_CLUSTERED: Bootstrap iterations for clustered agg (default: 5000)
    - HERETIX_RPL_B_SIMPLE: Bootstrap iterations for simple agg (default: 1000)
    - HERETIX_RPL_STABILITY_WIDTH: CI width threshold for stability (default: 0.2)
    
    Returns:
        RPLConfig: Configuration object with environment overrides applied
    """
    def _get_env_int(key: str, default: int) -> int:
        """Get integer from environment variable with default fallback."""
        value = os.getenv(key)
        return int(value) if value is not None else default
    
    def _get_env_float(key: str, default: float) -> float:
        """Get float from environment variable with default fallback."""
        value = os.getenv(key)
        return float(value) if value is not None else default
    
    return RPLConfig(
        min_samples=_get_env_int("HERETIX_RPL_MIN_SAMPLES", 3),
        trim=_get_env_float("HERETIX_RPL_TRIM", 0.2),
        b_clustered=_get_env_int("HERETIX_RPL_B_CLUSTERED", 5000),
        b_simple=_get_env_int("HERETIX_RPL_B_SIMPLE", 1000),
        stability_width=_get_env_float("HERETIX_RPL_STABILITY_WIDTH", 0.2),
    )


# Default configuration instance
DEFAULT_CONFIG = RPLConfig()