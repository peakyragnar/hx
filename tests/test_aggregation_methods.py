"""
Tests for Statistical Aggregation Methods

Validates simple and clustered aggregation with equal-by-template weighting.
Tests trimmed mean behavior, bootstrap mechanics, and CI properties. 
Ensures cluster bootstrap handles template imbalance correctly.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from heretix_rpl.aggregation import (                       # Functions under test
    aggregate_simple,
    aggregate_clustered,
    _trimmed_mean
)


class TestSimpleAggregation:                                # Test simple aggregation
    """Test the simple (unclustered) aggregation method."""  # Class purpose
    
    def test_mean_calculation(self):                        # Test basic mean
        """Verify simple aggregation computes correct mean."""  # Test purpose
        logits = [0.0, 1.0, -1.0, 0.5, -0.5]               # Test data
        mean, ci, diag = aggregate_simple(logits, B=100)   # Aggregate
        
        expected_mean = np.mean(logits)                     # Expected result
        assert mean == pytest.approx(expected_mean, abs=1e-10)  # Should match
        assert diag["n_samples"] == 5                       # Sample count
        assert diag["method"] == "simple_mean"              # Method name
    
    def test_ci_contains_mean(self):                        # Test CI property
        """Verify confidence interval contains the point estimate."""  # Test purpose
        logits = np.random.normal(0, 1, 50).tolist()       # Generate data
        mean, (lo, hi), _ = aggregate_simple(logits, B=500)  # Aggregate with CI
        
        assert lo <= mean <= hi, "CI should contain point estimate"  # CI must contain mean
    
    def test_ci_width_reasonable(self):                     # Test CI width
        """Check that CI width is reasonable for sample size."""  # Test purpose
        # Small sample -> wider CI
        small_logits = np.random.normal(0, 1, 10).tolist()  # Small sample
        _, (lo_s, hi_s), _ = aggregate_simple(small_logits, B=500)  # Get CI
        width_small = hi_s - lo_s                           # CI width
        
        # Large sample -> narrower CI  
        large_logits = np.random.normal(0, 1, 100).tolist()  # Large sample
        _, (lo_l, hi_l), _ = aggregate_simple(large_logits, B=500)  # Get CI
        width_large = hi_l - lo_l                           # CI width
        
        assert width_small > width_large, "Larger samples should have narrower CIs"  # Check relationship
    
    def test_deterministic_with_seed(self):                 # Test reproducibility
        """Verify results are deterministic with fixed seed."""  # Test purpose
        logits = [0.1, 0.2, 0.3, 0.4, 0.5]                 # Test data
        
        np.random.seed(123)                                 # Set seed
        result1 = aggregate_simple(logits, B=100)           # First run
        
        np.random.seed(123)                                 # Reset seed
        result2 = aggregate_simple(logits, B=100)           # Second run
        
        assert result1[0] == result2[0]                     # Means match
        assert result1[1] == result2[1]                     # CIs match
    
    def test_single_value_edge_case(self):                  # Test edge case
        """Test aggregation with single value."""           # Test purpose
        logits = [0.5]                                      # Single value
        mean, (lo, hi), diag = aggregate_simple(logits, B=100)  # Aggregate
        
        assert mean == 0.5                                  # Mean is the value
        assert lo == 0.5                                    # CI collapses
        assert hi == 0.5                                    # CI collapses
        assert diag["n_samples"] == 1                       # One sample


class TestClusteredAggregation:                             # Test clustered aggregation
    """Test the clustered (equal-by-template) aggregation method."""  # Class purpose
    
    def test_equal_template_weighting(self, template_logits, seeded_rng):  # Test key property
        """Verify templates get equal weight despite replicate imbalance."""  # Test purpose
        # Original has different replicate counts per template
        result1 = aggregate_clustered(template_logits, B=100, rng=seeded_rng)  # Original
        
        # Double replicates for first template (shouldn't change result much)
        modified = template_logits.copy()                   # Copy data
        modified["tpl_hash_1"] = modified["tpl_hash_1"] * 2  # Double one template
        
        rng2 = np.random.default_rng(12345)                 # Same seed
        result2 = aggregate_clustered(modified, B=100, rng=rng2)  # Modified
        
        # Results should be similar (equal weighting)
        assert result1[0] == pytest.approx(result2[0], abs=0.1)  # Similar estimates
    
    def test_trimmed_mean_calculation(self, seeded_rng):    # Test trimming
        """Verify trimmed mean correctly drops extremes."""  # Test purpose
        # Create data with clear outliers
        templates = {                                        # 5 templates
            "t1": [0.0],                                    # Middle
            "t2": [0.1],                                    # Middle  
            "t3": [0.2],                                    # Middle
            "t4": [-10.0],                                  # Low outlier
            "t5": [10.0]                                    # High outlier
        }
        
        # With trimming (20% each side drops min/max)
        result_trimmed = aggregate_clustered(               # Trimmed aggregation
            templates, B=100, rng=seeded_rng, 
            center="trimmed", trim=0.2
        )
        
        # Without trimming
        rng2 = np.random.default_rng(12345)                 # Same seed
        result_mean = aggregate_clustered(                  # Mean aggregation
            templates, B=100, rng=rng2,
            center="mean", trim=0.0
        )
        
        # Trimmed should be closer to middle values (0.0, 0.1, 0.2)
        assert abs(result_trimmed[0] - 0.1) < abs(result_mean[0] - 0.1)  # Trimmed closer
    
    def test_small_template_fallback(self, small_template_logits, seeded_rng):  # Test fallback
        """Test that trimming falls back to mean when T < 5."""  # Test purpose
        # Only 2 templates - can't trim 20% 
        result = aggregate_clustered(                       # Try to trim
            small_template_logits, B=100, rng=seeded_rng,
            center="trimmed", trim=0.2
        )
        
        # Should fall back to regular mean
        expected = np.mean([0.5, 0.6])                     # Manual calculation
        assert result[0] == pytest.approx(expected, abs=0.01)  # Should use mean
    
    def test_fixed_m_behavior(self, seeded_rng):           # Test fixed_m parameter
        """Test that fixed_m equalizes inner sampling variance."""  # Test purpose
        # Highly unequal replicates
        unequal = {                                         # Unbalanced data
            "many": [0.5] * 20,                            # Many replicates
            "few": [0.5]                                   # One replicate
        }
        
        # Without fixed_m (unequal inner sampling)
        result_unfixed = aggregate_clustered(               # Default behavior
            unequal, B=500, rng=seeded_rng, fixed_m=None
        )
        ci_width_unfixed = result_unfixed[1][1] - result_unfixed[1][0]  # CI width
        
        # With fixed_m=1 (equal inner sampling)
        rng2 = np.random.default_rng(12345)                 # Same seed
        result_fixed = aggregate_clustered(                 # Fixed sampling
            unequal, B=500, rng=rng2, fixed_m=1
        )
        ci_width_fixed = result_fixed[1][1] - result_fixed[1][0]  # CI width
        
        # Fixed_m should reduce variance from unequal replicates
        # Note: This is a statistical property, may need multiple runs
        assert ci_width_fixed <= ci_width_unfixed * 1.1    # Should not increase much
    
    def test_diagnostics_output(self, template_logits, seeded_rng):  # Test diagnostics
        """Verify diagnostic information is correctly computed."""  # Test purpose
        _, _, diag = aggregate_clustered(template_logits, B=100, rng=seeded_rng)  # Get diagnostics
        
        assert "n_templates" in diag                        # Template count
        assert diag["n_templates"] == 5                     # Should be 5
        assert "counts_by_template" in diag                 # Sample counts
        assert "imbalance_ratio" in diag                    # Imbalance metric
        assert "template_iqr_logit" in diag                 # Template spread
        
        # Check imbalance ratio calculation
        counts = list(diag["counts_by_template"].values())  # Get counts
        expected_ratio = max(counts) / min(counts)          # Max/min ratio
        assert diag["imbalance_ratio"] == pytest.approx(expected_ratio)  # Should match
    
    def test_empty_template_error(self):                     # Test error handling
        """Verify error is raised for empty input."""       # Test purpose
        with pytest.raises(ValueError, match="No templates"):  # Expect error
            aggregate_clustered({}, B=100)                  # Empty input
    
    def test_deterministic_with_rng(self, template_logits):  # Test determinism
        """Verify results are deterministic with same RNG."""  # Test purpose
        rng1 = np.random.default_rng(999)                   # First RNG
        result1 = aggregate_clustered(template_logits, B=100, rng=rng1)  # First run
        
        rng2 = np.random.default_rng(999)                   # Same seed
        result2 = aggregate_clustered(template_logits, B=100, rng=rng2)  # Second run
        
        assert result1[0] == result2[0]                     # Estimates match
        assert result1[1] == result2[1]                     # CIs match


class TestTrimmedMean:                                      # Test trimmed mean helper
    """Test the _trimmed_mean helper function."""           # Class purpose
    
    def test_basic_trimming(self):                          # Test basic case
        """Test basic 20% trimming."""                      # Test purpose
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])   # Test data
        result = _trimmed_mean(data, trim=0.2)              # Trim 20%
        
        # Should drop 2 from each end: [3,4,5,6,7,8]
        expected = np.mean([3, 4, 5, 6, 7, 8])              # Expected result
        assert result == pytest.approx(expected)            # Should match
    
    def test_no_trimming(self):                             # Test trim=0
        """Test with trim=0 (regular mean)."""              # Test purpose
        data = np.array([1, 2, 3, 4, 5])                   # Test data
        result = _trimmed_mean(data, trim=0.0)              # No trimming
        
        assert result == np.mean(data)                      # Should be regular mean
    
    def test_fallback_for_small_n(self):                    # Test fallback
        """Test fallback to regular mean when too few values."""  # Test purpose
        data = np.array([1, 2])                            # Only 2 values
        result = _trimmed_mean(data, trim=0.5)              # Try to trim 50%
        
        # Can't trim 50% from each side of 2 values
        assert result == np.mean(data)                      # Falls back to mean
    
    def test_outlier_resistance(self):                      # Test robustness
        """Verify trimmed mean resists outliers."""         # Test purpose
        normal_data = [4, 5, 6, 5, 4]                      # Normal data
        with_outliers = [4, 5, 6, 5, 4, 100, -100]         # Add outliers
        
        trimmed_normal = _trimmed_mean(np.array(normal_data), trim=0.2)  # Trim normal
        trimmed_outliers = _trimmed_mean(np.array(with_outliers), trim=0.3)  # Trim with outliers
        
        # Trimmed means should be similar despite outliers
        assert abs(trimmed_normal - trimmed_outliers) < 1.0  # Should be close


@pytest.mark.slow
class TestBootstrapProperties:                              # Slow bootstrap tests
    """Test statistical properties of bootstrap (marked as slow)."""  # Class purpose
    
    def test_ci_coverage(self):                             # Test coverage
        """Test that CI coverage is approximately correct."""  # Test purpose
        true_mean = 0.0                                     # Known mean
        coverage_count = 0                                  # Coverage counter
        n_trials = 200                                      # Number of trials
        
        for _ in range(n_trials):                           # Run trials
            # Generate data with known mean
            data = np.random.normal(true_mean, 1.0, 30).tolist()  # Sample data
            _, (lo, hi), _ = aggregate_simple(data, B=500)  # Get CI
            
            if lo <= true_mean <= hi:                       # Check coverage
                coverage_count += 1                         # Count hits
        
        coverage = coverage_count / n_trials                # Calculate coverage
        # Allow reasonable band (90-98% for 95% CI)
        assert 0.90 <= coverage <= 0.98, f"Coverage {coverage} outside expected range"  # Check range
    
    def test_ci_width_scales_with_n(self):                  # Test width scaling
        """Verify CI width decreases with sample size."""   # Test purpose
        widths = []                                         # Store widths
        
        for n in [10, 50, 200]:                             # Different sample sizes
            data = np.random.normal(0, 1, n).tolist()       # Generate data
            _, (lo, hi), _ = aggregate_simple(data, B=300)  # Get CI
            widths.append(hi - lo)                          # Store width
        
        # Width should decrease with larger samples
        assert widths[0] > widths[1] > widths[2], "CI width should decrease with n"  # Check ordering