"""
Environment-driven Configuration for Raw Prior Lens (RPL) Evaluation

Provides RPLConfig dataclass with environment variable overrides and sensible defaults.
Controls min samples, bootstrap iterations, trimming thresholds, and stability criteria.
Centralizes all RPL system parameters for consistent behavior across evaluations.
"""
import os                                                    # Environment variable access
from dataclasses import dataclass                           # Configuration structure
from typing import Optional                                  # Type hints for optional values


@dataclass
class RPLConfig:                                             # Configuration settings container
    """Configuration settings for RPL evaluation with environment variable overrides."""  # Class purpose
    
    min_samples: int = 3                                     # Minimum successful samples required for aggregation
    trim: float = 0.2                                        # Trim percentage for robust center (20% = drop min/max)
    b_clustered: int = 5000                                  # Bootstrap iterations for clustered aggregation (smoother CIs)
    b_simple: int = 1000                                     # Bootstrap iterations for simple aggregation
    stability_width: float = 0.2                             # CI width threshold for stability (stable when width <= threshold)


def load_config() -> RPLConfig:                              # Load configuration with environment overrides
    """Load configuration from environment variables with fallback to defaults."""  # Function purpose
    def _get_env_int(key: str, default: int) -> int:         # Helper for integer environment variables
        """Get integer from environment variable with default fallback."""  # Helper purpose
        value = os.getenv(key)                               # Get environment value
        return int(value) if value is not None else default  # Convert or use default
    
    def _get_env_float(key: str, default: float) -> float:   # Helper for float environment variables
        """Get float from environment variable with default fallback."""  # Helper purpose
        value = os.getenv(key)                               # Get environment value
        return float(value) if value is not None else default  # Convert or use default
    
    return RPLConfig(                                        # Create configuration object
        min_samples=_get_env_int("HERETIX_RPL_MIN_SAMPLES", 3),          # Override minimum samples threshold
        trim=_get_env_float("HERETIX_RPL_TRIM", 0.2),                    # Override trim percentage
        b_clustered=_get_env_int("HERETIX_RPL_B_CLUSTERED", 5000),       # Override clustered bootstrap iterations
        b_simple=_get_env_int("HERETIX_RPL_B_SIMPLE", 1000),             # Override simple bootstrap iterations
        stability_width=_get_env_float("HERETIX_RPL_STABILITY_WIDTH", 0.2),  # Override stability width threshold
    )


DEFAULT_CONFIG = RPLConfig()                                 # Default configuration instance