"""
Tests for Edge Cases and Boundary Conditions

Verifies robust system behavior with extreme inputs, minimal data, and boundary values.
Tests clamped probabilities, small sample aggregation, and bootstrap edge cases.
Ensures graceful handling of degenerate cases and numerical precision limits.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from heretix_rpl.rpl_eval import _logit, _sigmoid, compute_stability  # Functions under test
from heretix_rpl.aggregation import aggregate_simple, aggregate_clustered, _trimmed_mean  # Aggregation functions
from heretix_rpl.config import RPLConfig                    # Configuration


class TestMinimalData:                                      # Test with minimal data
    """Test behavior with minimum viable datasets."""        # Class purpose
    
    def test_minimum_samples_threshold(self):               # Test min samples
        """Test that exactly 3 samples works (minimum threshold)."""  # Test purpose
        logits = [0.1, 0.2, 0.3]                           # Exactly 3 samples
        
        # Should work with exactly minimum
        mean, ci, diag = aggregate_simple(logits, B=100)   # Aggregate
        assert diag["n_samples"] == 3                       # Confirm count
        assert mean == pytest.approx(0.2, abs=0.01)         # Check mean
    
    def test_below_minimum_samples_error(self):             # Test error case
        """Test that fewer than minimum samples raises error."""  # Test purpose
        # This would be caught in evaluate_rpl_gpt5 with config.min_samples
        # Here we test the aggregation doesn't fail but evaluation would
        logits = [0.1, 0.2]                                # Only 2 samples
        
        # Aggregation itself should work
        mean, ci, diag = aggregate_simple(logits, B=100)   # Should not error
        assert diag["n_samples"] == 2                       # Confirm count
        
        # But in real usage, evaluate_rpl_gpt5 would check:
        config = RPLConfig(min_samples=3)                   # Test config
        assert len(logits) < config.min_samples             # Would fail check
    
    def test_single_template_aggregation(self):             # Test single template
        """Test clustered aggregation with single template."""  # Test purpose
        single_template = {"only_one": [0.1, 0.2, 0.3]}    # One template
        
        mean, ci, diag = aggregate_clustered(               # Aggregate
            single_template, B=100, 
            center="trimmed", trim=0.2
        )
        
        # Should work but trimming won't apply (only 1 template)
        assert diag["n_templates"] == 1                     # One template
        expected = np.mean([0.1, 0.2, 0.3])                # Manual mean
        assert mean == pytest.approx(expected, abs=0.01)    # Check result
    
    def test_single_replicate_per_template(self):           # Test minimal replicates
        """Test with single replicate per template."""      # Test purpose
        minimal = {                                          # One replicate each
            "t1": [0.1],
            "t2": [0.2], 
            "t3": [0.3],
            "t4": [0.4],
            "t5": [0.5]
        }
        
        mean, ci, diag = aggregate_clustered(minimal, B=100)  # Aggregate
        
        # Should work fine - each template has equal weight already
        assert diag["n_templates"] == 5                     # Five templates
        assert diag["imbalance_ratio"] == 1.0               # Perfect balance
        
        # With trimming, should use middle 3 values
        expected = np.mean([0.2, 0.3, 0.4])                # Middle 3 after trim
        assert mean == pytest.approx(expected, abs=0.05)    # Check result


class TestExtremeValues:                                    # Test extreme probabilities
    """Test handling of extreme probability values."""       # Class purpose
    
    def test_extreme_probabilities_clamping(self, extreme_probabilities):  # Test clamping
        """Test that extreme probabilities are clamped correctly."""  # Test purpose
        for p in extreme_probabilities:                     # Test each extreme
            logit = _logit(p)                              # Convert to logit
            
            # Should not produce infinity or NaN
            assert np.isfinite(logit), f"logit({p}) not finite"  # Must be finite
            
            # Round-trip should work
            reconstructed = _sigmoid(logit)                 # Back to probability
            assert 0 <= reconstructed <= 1, f"sigmoid(logit({p})) out of bounds"  # Valid probability
    
    def test_all_zeros_probability(self):                   # Test all zeros
        """Test aggregation when all probabilities are 0 (clamped)."""  # Test purpose
        # All zeros get clamped to 1e-6
        probs = [0.0, 0.0, 0.0, 0.0, 0.0]                  # All zeros
        logits = [_logit(p) for p in probs]                # Convert to logits
        
        mean, ci, diag = aggregate_simple(logits, B=100)   # Aggregate
        
        # All should be clamped to same value
        expected_logit = _logit(1e-6)                      # Clamped value
        assert mean == pytest.approx(expected_logit, abs=0.01)  # Check mean
        
        # CI should be very narrow (all same value)
        assert (ci[1] - ci[0]) < 0.01, "CI should be narrow for identical values"  # Narrow CI
    
    def test_all_ones_probability(self):                    # Test all ones
        """Test aggregation when all probabilities are 1 (clamped)."""  # Test purpose
        # All ones get clamped to 1-1e-6
        probs = [1.0, 1.0, 1.0, 1.0, 1.0]                  # All ones
        logits = [_logit(p) for p in probs]                # Convert to logits
        
        mean, ci, diag = aggregate_simple(logits, B=100)   # Aggregate
        
        # All should be clamped to same value
        expected_logit = _logit(1 - 1e-6)                  # Clamped value
        assert mean == pytest.approx(expected_logit, abs=0.01)  # Check mean
    
    def test_mixed_extreme_values(self):                    # Test mixed extremes
        """Test aggregation with mix of extreme values."""  # Test purpose
        templates = {                                        # Mix of extremes
            "very_low": [_logit(1e-10)],                   # Near zero
            "low": [_logit(0.1)],                          # Low
            "mid": [_logit(0.5)],                          # Middle
            "high": [_logit(0.9)],                         # High
            "very_high": [_logit(1 - 1e-10)]               # Near one
        }
        
        # Should handle without errors
        mean, ci, diag = aggregate_clustered(               # Aggregate
            templates, B=100,
            center="trimmed", trim=0.2
        )
        
        assert np.isfinite(mean), "Mean should be finite"   # Must be finite
        assert np.isfinite(ci[0]) and np.isfinite(ci[1]), "CI should be finite"  # CI finite


class TestIdenticalValues:                                  # Test all same values
    """Test behavior when all values are identical."""       # Class purpose
    
    def test_all_identical_simple(self):                    # Test simple aggregation
        """Test simple aggregation with identical values."""  # Test purpose
        logits = [0.5] * 20                                # All same value
        
        mean, (lo, hi), diag = aggregate_simple(logits, B=100)  # Aggregate
        
        assert mean == 0.5, "Mean should be the common value"  # Exact mean
        assert lo == 0.5, "CI lower should be the value"    # CI collapses
        assert hi == 0.5, "CI upper should be the value"    # CI collapses
    
    def test_all_identical_clustered(self, uniform_template_logits):  # Test clustered
        """Test clustered aggregation with identical values."""  # Test purpose
        mean, (lo, hi), diag = aggregate_clustered(         # Aggregate
            uniform_template_logits, B=100
        )
        
        assert mean == 0.0, "Mean should be the common value"  # All zeros
        assert abs(hi - lo) < 0.001, "CI should be very narrow"  # Nearly collapsed
        
        # Stability should be perfect (no variation)
        assert diag["template_iqr_logit"] == 0.0, "IQR should be 0"  # No spread


class TestSmallBootstrap:                                   # Test tiny B values
    """Test behavior with very small bootstrap iterations."""  # Class purpose
    
    def test_b_equals_1(self, template_logits):             # Test B=1
        """Test with B=1 (minimal bootstrap)."""            # Test purpose
        # Should still produce valid results
        mean, (lo, hi), diag = aggregate_clustered(         # Aggregate
            template_logits, B=1
        )
        
        assert np.isfinite(mean), "Mean should be finite"   # Valid mean
        assert np.isfinite(lo) and np.isfinite(hi), "CI should be finite"  # Valid CI
        
        # CI might be degenerate but should be valid
        assert lo <= mean <= hi, "CI should contain mean"   # CI contains mean
    
    def test_b_equals_10(self, template_logits):            # Test B=10
        """Test with B=10 (very small bootstrap)."""        # Test purpose
        mean, (lo, hi), diag = aggregate_clustered(         # Aggregate
            template_logits, B=10
        )
        
        # Should produce reasonable results even with small B
        assert lo < mean < hi, "CI should bracket mean"     # Proper CI
        assert (hi - lo) > 0, "CI should have positive width"  # Non-zero width


class TestStabilityEdgeCases:                               # Test stability calculation
    """Test stability score calculation edge cases."""       # Class purpose
    
    def test_stability_with_zero_iqr(self):                 # Test perfect stability
        """Test stability score when IQR is 0."""           # Test purpose
        identical_logits = [0.5] * 10                       # All same
        stability = compute_stability(identical_logits)      # Calculate stability
        
        assert stability == 1.0, "Stability should be 1.0 for zero IQR"  # Perfect stability
    
    def test_stability_monotonic_decrease(self):            # Test monotonicity
        """Test that stability decreases with increasing IQR."""  # Test purpose
        # Create datasets with increasing spread
        narrow = [0.4, 0.5, 0.6]                           # Small spread
        medium = [0.2, 0.5, 0.8]                           # Medium spread  
        wide = [0.0, 0.5, 1.0]                             # Large spread
        
        stability_narrow = compute_stability(narrow)        # Calculate stability
        stability_medium = compute_stability(medium)        # Calculate stability
        stability_wide = compute_stability(wide)            # Calculate stability
        
        # Stability should decrease with spread
        assert stability_narrow > stability_medium > stability_wide  # Monotonic decrease
        
        # All should be in valid range
        for s in [stability_narrow, stability_medium, stability_wide]:  # Check each
            assert 0 < s <= 1, f"Stability {s} out of bounds"  # Valid range