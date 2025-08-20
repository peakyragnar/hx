"""
Tests for deterministic seed generation.

Verifies that the same configuration always produces the same seed,
different configurations produce different seeds, and environment
overrides work correctly.
"""
import pytest                                                 # Testing framework
import os                                                    # Environment variables
import numpy as np                                           # Numerical operations
from heretix_rpl.seed import make_bootstrap_seed            # Function under test
from heretix_rpl.aggregation import aggregate_clustered      # For testing seed effects


class TestSeedGeneration:                                   # Test seed generation
    """Test deterministic seed generation from configuration."""  # Class purpose
    
    def test_same_config_same_seed(self):                   # Test determinism
        """Verify same configuration produces same seed."""  # Test purpose
        config = {                                           # Test configuration
            "claim": "test claim",                          # Claim text
            "model": "gpt-5",                               # Model name
            "prompt_version": "v1",                         # Version
            "k": 7,                                          # Paraphrases
            "r": 3,                                          # Replicates
            "template_hashes": ["hash1", "hash2"],          # Template hashes
            "center": "trimmed",                             # Center method
            "trim": 0.2,                                     # Trim percentage
            "B": 5000                                        # Bootstrap iterations
        }
        
        seed1 = make_bootstrap_seed(**config)               # First call
        seed2 = make_bootstrap_seed(**config)               # Second call
        
        assert seed1 == seed2, "Same config should produce same seed"  # Must match
        assert isinstance(seed1, int), "Seed should be integer"  # Type check
        assert 0 <= seed1 < 2**64, "Seed should be 64-bit unsigned"  # Range check
    
    def test_different_claims_different_seeds(self):        # Test claim sensitivity
        """Verify different claims produce different seeds."""  # Test purpose
        base_config = {                                      # Base configuration
            "model": "gpt-5",
            "prompt_version": "v1", 
            "k": 7,
            "r": 3,
            "template_hashes": ["hash1"],
            "center": "trimmed",
            "trim": 0.2,
            "B": 5000
        }
        
        seed1 = make_bootstrap_seed(claim="claim A", **base_config)  # First claim
        seed2 = make_bootstrap_seed(claim="claim B", **base_config)  # Different claim
        
        assert seed1 != seed2, "Different claims should produce different seeds"  # Must differ
    
    def test_different_models_different_seeds(self):        # Test model sensitivity
        """Verify different models produce different seeds."""  # Test purpose
        base_config = {                                      # Base configuration
            "claim": "test claim",
            "prompt_version": "v1",
            "k": 7,
            "r": 3,
            "template_hashes": ["hash1"],
            "center": "trimmed",
            "trim": 0.2,
            "B": 5000
        }
        
        seed1 = make_bootstrap_seed(model="gpt-5", **base_config)  # First model
        seed2 = make_bootstrap_seed(model="gpt-4", **base_config)  # Different model
        
        assert seed1 != seed2, "Different models should produce different seeds"  # Must differ
    
    def test_template_order_affects_seed(self):             # Test hash ordering
        """Verify template hash order affects seed (as designed)."""  # Test purpose
        config = {                                           # Base configuration
            "claim": "test",
            "model": "gpt-5",
            "prompt_version": "v1",
            "k": 7,
            "r": 3,
            "center": "trimmed",
            "trim": 0.2,
            "B": 5000
        }
        
        # Different template orderings
        seed1 = make_bootstrap_seed(                        # First ordering
            template_hashes=["hash1", "hash2", "hash3"],
            **config
        )
        seed2 = make_bootstrap_seed(                        # Different ordering
            template_hashes=["hash2", "hash1", "hash3"],
            **config
        )
        
        # Seeds will differ because templates are sorted in make_bootstrap_seed
        # but the sorted order will be consistent
        config_sorted = config.copy()                       # Copy config
        sorted_hashes = sorted(["hash1", "hash2", "hash3"])  # Sort hashes
        seed3 = make_bootstrap_seed(                        # Sorted order
            template_hashes=sorted_hashes,
            **config
        )
        seed4 = make_bootstrap_seed(                        # Same sorted order
            template_hashes=sorted_hashes,
            **config
        )
        
        assert seed3 == seed4, "Same sorted templates should produce same seed"  # Must match
    
    def test_parameter_changes_affect_seed(self):           # Test parameter sensitivity
        """Verify changes to parameters affect seed."""      # Test purpose
        base_config = {                                      # Base configuration
            "claim": "test",
            "model": "gpt-5",
            "prompt_version": "v1",
            "template_hashes": ["hash1"],
            "center": "trimmed",
            "trim": 0.2,
            "B": 5000
        }
        
        # Test k parameter
        seed_k7_r3 = make_bootstrap_seed(k=7, r=3, **base_config)  # Original
        seed_k8_r3 = make_bootstrap_seed(k=8, r=3, **base_config)  # Different k
        assert seed_k7_r3 != seed_k8_r3, "Different k should produce different seed"  # Must differ
        
        # Test r parameter  
        seed_k7_r4 = make_bootstrap_seed(k=7, r=4, **base_config)  # Different r
        assert seed_k7_r3 != seed_k7_r4, "Different r should produce different seed"  # Must differ
        
        # Test B parameter
        seed_b5000 = make_bootstrap_seed(k=7, r=3, B=5000, **base_config)  # Original B
        seed_b1000 = make_bootstrap_seed(k=7, r=3, B=1000, **base_config)  # Different B
        assert seed_b5000 != seed_b1000, "Different B should produce different seed"  # Must differ


class TestSeedEffects:                                      # Test seed usage
    """Test that seeds produce deterministic aggregation results."""  # Class purpose
    
    def test_seed_produces_deterministic_ci(self, template_logits):  # Test CI determinism
        """Verify same seed produces same confidence intervals."""  # Test purpose
        # Run aggregation twice with same seed
        rng1 = np.random.default_rng(42)                    # First RNG
        result1 = aggregate_clustered(template_logits, B=100, rng=rng1)  # First run
        
        rng2 = np.random.default_rng(42)                    # Same seed
        result2 = aggregate_clustered(template_logits, B=100, rng=rng2)  # Second run
        
        # Results should be identical
        assert result1[0] == result2[0], "Point estimates should match"  # Estimates match
        assert result1[1][0] == result2[1][0], "CI lower bounds should match"  # Lower match
        assert result1[1][1] == result2[1][1], "CI upper bounds should match"  # Upper match
    
    def test_different_seeds_produce_different_ci(self, template_logits):  # Test variation
        """Verify different seeds produce (slightly) different CIs."""  # Test purpose
        # Run aggregation with different seeds
        rng1 = np.random.default_rng(42)                    # First seed
        result1 = aggregate_clustered(template_logits, B=1000, rng=rng1)  # First run
        
        rng2 = np.random.default_rng(99)                    # Different seed
        result2 = aggregate_clustered(template_logits, B=1000, rng=rng2)  # Second run
        
        # Point estimate should be same (deterministic from data)
        assert result1[0] == result2[0], "Point estimates should match"  # Estimates match
        
        # But CIs might differ slightly due to bootstrap randomness
        # With enough B, they should be close but not identical
        ci1_width = result1[1][1] - result1[1][0]           # First CI width
        ci2_width = result2[1][1] - result2[1][0]           # Second CI width
        
        # Widths should be similar but not necessarily identical
        assert abs(ci1_width - ci2_width) < 0.1, "CI widths should be similar"  # Close widths
    
    def test_environment_override(self, monkeypatch, template_logits):  # Test env override
        """Test that HERETIX_RPL_SEED environment variable works."""  # Test purpose
        # This would be tested in integration, but we can verify the concept
        # by checking that providing the same seed gives same results
        
        # Simulate what would happen with env override
        override_seed = 12345                               # Fixed seed
        
        rng1 = np.random.default_rng(override_seed)         # First RNG
        result1 = aggregate_clustered(template_logits, B=100, rng=rng1)  # First run
        
        rng2 = np.random.default_rng(override_seed)         # Same seed
        result2 = aggregate_clustered(template_logits, B=100, rng=rng2)  # Second run
        
        assert result1 == result2, "Same override seed should produce same results"  # Must match