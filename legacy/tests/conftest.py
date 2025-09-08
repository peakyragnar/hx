"""
Pytest configuration, fixtures, and mocks for statistical testing.

Provides deterministic random seeds, mock OpenAI responses, and
synthetic data generators for testing RPL statistical components.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from unittest.mock import MagicMock, patch                  # Mocking utilities
from typing import Dict, List, Callable                     # Type hints
import hashlib                                               # For deterministic hashing
import json                                                  # JSON handling


# =============================================================================
# Random Seed Management
# =============================================================================

@pytest.fixture(autouse=True)
def deterministic_random():                                  # Ensure reproducible tests
    """Ensure deterministic randomness per test."""         # Fixture purpose
    np.random.seed(42)                                      # Set fixed seed
    yield                                                    # Run test
    np.random.seed(None)                                    # Reset after test


@pytest.fixture
def seeded_rng():                                           # Provide seeded RNG
    """Provide seeded RNG for clustered aggregation tests."""  # Fixture purpose
    return np.random.default_rng(12345)                     # Return deterministic RNG


# =============================================================================
# Mock OpenAI Responses
# =============================================================================

@pytest.fixture
def mock_openai_response():                                 # Mock API responses
    """Factory for creating mock OpenAI responses with synthetic probabilities."""  # Fixture purpose
    def _mock_response(                                     # Response factory function
        prob_true: float = 0.5,                            # Truth probability
        confidence_self: float = 0.7,                      # Model confidence
        paraphrase_idx: int = 0,                           # Paraphrase index
        replicate_idx: int = 0                             # Replicate index
    ) -> dict:                                              # Return mock response
        """Generate a mock OpenAI response matching expected schema."""  # Function purpose
        prompt_text = f"paraphrase_{paraphrase_idx}"       # Create unique prompt
        prompt_hash = hashlib.sha256(                       # Generate deterministic hash
            prompt_text.encode()
        ).hexdigest()                                       # Convert to hex string
        
        return {                                             # Mock response structure
            "raw": {                                         # Raw model output
                "prob_true": prob_true,                     # Probability estimate
                "confidence_self": confidence_self,         # Self-reported confidence
                "assumptions": ["Test assumption"],         # Model assumptions
                "reasoning_bullets": [                      # Reasoning steps
                    "Test reasoning 1",
                    "Test reasoning 2",
                    "Test reasoning 3"
                ],
                "contrary_considerations": [                # Counter-arguments
                    "Test contrary 1",
                    "Test contrary 2"
                ],
                "ambiguity_flags": []                       # Ambiguity indicators
            },
            "meta": {                                        # Metadata
                "provider_model_id": "gpt-5-test",         # Model identifier
                "prompt_sha256": prompt_hash,               # Prompt hash for clustering
                "prompt_version": "test_v1",                # Version tracking
                "response_id": f"resp_test_{paraphrase_idx}_{replicate_idx}",  # Unique ID
                "created": 1234567890.0                     # Timestamp
            },
            "paraphrase_idx": paraphrase_idx,               # Paraphrase slot
            "replicate_idx": replicate_idx                  # Replicate number
        }
    return _mock_response                                   # Return factory function


@pytest.fixture
def mock_call_rpl_once_gpt5(mock_openai_response):         # Mock single API call
    """Mock the call_rpl_once_gpt5 function."""            # Fixture purpose
    def _mock_call(claim_text, paraphrase, model):          # Mock function signature
        """Return deterministic response based on claim."""  # Function purpose
        # Use claim hash for deterministic but varied probabilities
        claim_hash = int(hashlib.sha256(                    # Hash claim for variety
            claim_text.encode()
        ).hexdigest()[:8], 16)                              # Convert to integer
        
        prob = 0.3 + (claim_hash % 40) / 100.0              # Generate prob in [0.3, 0.7]
        return mock_openai_response(prob_true=prob)         # Return mock response
    
    return _mock_call                                       # Return mock function


# =============================================================================
# Synthetic Data Generators
# =============================================================================

@pytest.fixture
def template_logits():                                      # Generate template data
    """Generate synthetic template-grouped logits for testing."""  # Fixture purpose
    return {                                                 # Template structure
        "tpl_hash_1": [0.1, 0.2, 0.15],                    # 3 replicates
        "tpl_hash_2": [0.3, 0.25],                         # 2 replicates (imbalanced)
        "tpl_hash_3": [0.4, 0.45, 0.42, 0.43],            # 4 replicates
        "tpl_hash_4": [-0.1, -0.05],                       # 2 replicates (negative logits)
        "tpl_hash_5": [0.6]                                # 1 replicate (minimal)
    }


@pytest.fixture
def small_template_logits():                                # Small dataset
    """Generate small template dataset for edge case testing."""  # Fixture purpose
    return {                                                 # Minimal structure
        "tpl_1": [0.5],                                     # Single replicate
        "tpl_2": [0.6]                                      # Single replicate
    }


@pytest.fixture
def uniform_template_logits():                              # Uniform data
    """Generate template logits with identical values."""    # Fixture purpose
    value = 0.0                                             # Logit of p=0.5
    return {                                                 # All same value
        f"tpl_{i}": [value] * 3                            # 3 replicates each
        for i in range(5)                                   # 5 templates
    }


@pytest.fixture
def outlier_template_logits():                              # Data with outliers
    """Generate template logits with outliers for robustness testing."""  # Fixture purpose
    return {                                                 # Mix of normal and outliers
        "tpl_normal_1": [0.1, 0.15, 0.12],                 # Normal values
        "tpl_normal_2": [0.2, 0.25, 0.22],                 # Normal values
        "tpl_normal_3": [0.3, 0.32, 0.28],                 # Normal values
        "tpl_outlier_1": [5.0, 5.2, 4.8],                  # Extreme high
        "tpl_outlier_2": [-5.0, -4.8, -5.2]                # Extreme low
    }


# =============================================================================
# Probability Generators
# =============================================================================

@pytest.fixture
def probability_samples():                                  # Generate probabilities
    """Generate diverse probability samples for testing."""  # Fixture purpose
    return [                                                 # Various probabilities
        0.001,                                              # Near zero
        0.01,                                               # Low
        0.1,                                                # Low-medium
        0.25,                                               # Quarter
        0.5,                                                # Middle
        0.75,                                               # Three quarters
        0.9,                                                # High-medium
        0.99,                                               # High
        0.999                                               # Near one
    ]


@pytest.fixture
def extreme_probabilities():                                # Extreme values
    """Generate extreme probability values for edge case testing."""  # Fixture purpose
    return [                                                 # Edge cases
        0.0,                                                # Exactly zero
        1e-10,                                              # Tiny positive
        1e-6,                                               # Clamping boundary
        1 - 1e-6,                                           # Upper clamping boundary
        1 - 1e-10,                                          # Tiny from one
        1.0                                                 # Exactly one
    ]


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def test_config():                                          # Test configuration
    """Provide test configuration with known values."""     # Fixture purpose
    from heretix_rpl.config import RPLConfig                # Import config class
    return RPLConfig(                                       # Create test config
        min_samples=3,                                      # Minimum samples
        trim=0.2,                                           # 20% trimming
        b_clustered=100,                                    # Reduced for speed
        b_simple=100,                                       # Reduced for speed
        stability_width=0.2                                 # Standard threshold
    )


# =============================================================================
# Test Markers
# =============================================================================

def pytest_configure(config):                               # Configure pytest
    """Register custom markers."""                          # Function purpose
    config.addinivalue_line(                                # Add marker definition
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(                                # Add marker definition
        "markers", "integration: marks tests as integration tests"
    )


# =============================================================================
# Utility Functions
# =============================================================================

@pytest.fixture
def assert_approx_equal():                                  # Comparison helper
    """Provide approximate equality assertion helper."""    # Fixture purpose
    def _assert(actual, expected, rel=1e-6, abs=1e-10):    # Assertion function
        """Assert approximate equality with sensible defaults."""  # Function purpose
        assert actual == pytest.approx(expected, rel=rel, abs=abs)  # Use pytest.approx
    return _assert                                          # Return helper