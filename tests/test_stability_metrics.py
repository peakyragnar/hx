"""
Tests for stability metric calculations.

Verifies that stability scores are computed correctly and
have the expected mathematical properties.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from heretix_rpl.rpl_eval import compute_stability          # Function under test


class TestStabilityCalculation:                             # Test stability computation
    """Test the compute_stability function."""              # Class purpose
    
    def test_perfect_stability(self):                       # Test IQR=0 case
        """Test that identical values give stability = 1.0."""  # Test purpose
        identical = [0.5, 0.5, 0.5, 0.5, 0.5]              # All same value
        stability = compute_stability(identical)            # Calculate stability
        
        assert stability == 1.0, "Identical values should have perfect stability"  # Must be 1
    
    def test_stability_range(self):                         # Test valid range
        """Test that stability is always in (0, 1]."""      # Test purpose
        test_cases = [                                      # Various datasets
            [0.1, 0.2, 0.3],                               # Small spread
            [0.0, 0.5, 1.0],                               # Full range
            [-5.0, 0.0, 5.0],                              # Large spread in logits
            [0.49, 0.50, 0.51],                            # Tiny spread
        ]
        
        for data in test_cases:                             # Test each case
            stability = compute_stability(data)             # Calculate stability
            assert 0 < stability <= 1, f"Stability {stability} out of range"  # Check bounds
    
    def test_stability_monotonic(self):                     # Test monotonicity
        """Test that stability decreases with increasing spread."""  # Test purpose
        # Create datasets with increasing IQR
        tight = [0.49, 0.50, 0.51]                         # IQR ≈ 0.02
        medium = [0.40, 0.50, 0.60]                        # IQR ≈ 0.20
        wide = [0.10, 0.50, 0.90]                          # IQR ≈ 0.80
        very_wide = [-2.0, 0.0, 2.0]                       # IQR ≈ 4.0
        
        s_tight = compute_stability(tight)                  # Calculate stability
        s_medium = compute_stability(medium)                # Calculate stability
        s_wide = compute_stability(wide)                    # Calculate stability
        s_very_wide = compute_stability(very_wide)          # Calculate stability
        
        # Should decrease monotonically
        assert s_tight > s_medium, "Tighter spread should have higher stability"  # Check order
        assert s_medium > s_wide, "Medium spread should beat wide"  # Check order
        assert s_wide > s_very_wide, "Wide spread should beat very wide"  # Check order
    
    def test_stability_formula(self):                       # Test exact formula
        """Test the exact stability formula: 1/(1+IQR)."""  # Test purpose
        test_data = [1.0, 2.0, 3.0, 4.0, 5.0]              # Simple data
        
        # Calculate IQR manually
        q75 = np.percentile(test_data, 75)                  # 75th percentile
        q25 = np.percentile(test_data, 25)                  # 25th percentile
        iqr = q75 - q25                                     # IQR
        
        expected = 1.0 / (1.0 + iqr)                        # Expected stability
        actual = compute_stability(test_data)               # Actual stability
        
        assert actual == pytest.approx(expected, rel=1e-10)  # Should match formula
    
    def test_stability_with_outliers(self):                 # Test outlier effect
        """Test that outliers affect stability appropriately."""  # Test purpose
        normal = [0.4, 0.45, 0.5, 0.55, 0.6]               # Normal data
        with_outlier = [0.4, 0.45, 0.5, 0.55, 10.0]        # One outlier
        
        s_normal = compute_stability(normal)                # Normal stability
        s_outlier = compute_stability(with_outlier)         # With outlier
        
        # Outlier should reduce stability (increase IQR)
        assert s_outlier < s_normal, "Outlier should reduce stability"  # Check effect
    
    def test_stability_percentiles(self):                   # Test percentile calculation
        """Test that IQR is calculated correctly."""        # Test purpose
        # Use data where we know exact percentiles
        data = list(range(1, 101))                          # 1 to 100
        
        stability = compute_stability(data)                 # Calculate stability
        
        # Q25 = 25.5, Q75 = 75.5, IQR = 50
        expected_iqr = 50.0                                 # Known IQR
        expected_stability = 1.0 / (1.0 + expected_iqr)     # Expected result
        
        assert stability == pytest.approx(expected_stability, rel=0.01)  # Should match
    
    def test_stability_small_sample(self):                  # Test small samples
        """Test stability with minimal samples."""          # Test purpose
        small_samples = [                                   # Small datasets
            [0.5],                                          # Single value
            [0.4, 0.6],                                     # Two values
            [0.3, 0.5, 0.7],                                # Three values
        ]
        
        for data in small_samples:                          # Test each
            stability = compute_stability(data)             # Calculate stability
            assert 0 < stability <= 1, f"Small sample stability {stability} out of range"  # Valid
            
            # Single value should have perfect stability
            if len(data) == 1:                              # Single value
                assert stability == 1.0, "Single value should have perfect stability"  # Must be 1


class TestStabilityInContext:                               # Test stability in context
    """Test stability calculations within the evaluation pipeline."""  # Class purpose
    
    def test_stability_from_template_means(self, template_logits):  # Test with templates
        """Test stability calculation from template means."""  # Test purpose
        # Calculate template means manually
        template_means = []                                 # Store means
        for logits in template_logits.values():             # Each template
            template_means.append(np.mean(logits))          # Calculate mean
        
        # Calculate stability from means
        stability = compute_stability(template_means)       # Calculate stability
        
        # Should be reasonable value
        assert 0 < stability <= 1, "Stability out of range"  # Valid range
        
        # With 5 diverse templates, shouldn't be perfect
        assert stability < 1.0, "Diverse templates shouldn't have perfect stability"  # Not perfect
    
    def test_stability_interpretation(self):                # Test interpretation
        """Test interpretation of stability values."""      # Test purpose
        # High stability (tight distribution)
        tight_data = [0.48, 0.49, 0.50, 0.51, 0.52]        # Tight spread
        high_stability = compute_stability(tight_data)      # Calculate
        assert high_stability > 0.9, "Tight data should have high stability"  # High value
        
        # Medium stability
        medium_data = [0.3, 0.4, 0.5, 0.6, 0.7]            # Medium spread
        medium_stability = compute_stability(medium_data)   # Calculate
        assert 0.3 < medium_stability < 0.7, "Medium spread should have medium stability"  # Medium
        
        # Low stability (wide distribution)
        wide_data = [-2, -1, 0, 1, 2]                      # Wide spread
        low_stability = compute_stability(wide_data)        # Calculate
        assert low_stability < 0.3, "Wide data should have low stability"  # Low value
    
    def test_stability_ci_width_correlation(self):          # Test correlation
        """Test that low stability correlates with wide CIs."""  # Test purpose
        from heretix_rpl.aggregation import aggregate_simple  # Import aggregation
        
        # High stability data (low variance)
        tight = np.random.normal(0, 0.1, 50).tolist()      # Low variance
        _, (lo_t, hi_t), _ = aggregate_simple(tight, B=100)  # Get CI
        width_tight = hi_t - lo_t                           # CI width
        stability_tight = compute_stability(tight)          # Stability
        
        # Low stability data (high variance)  
        wide = np.random.normal(0, 1.0, 50).tolist()       # High variance
        _, (lo_w, hi_w), _ = aggregate_simple(wide, B=100)  # Get CI
        width_wide = hi_w - lo_w                            # CI width
        stability_wide = compute_stability(wide)            # Stability
        
        # Low stability should correlate with wide CI
        assert stability_tight > stability_wide, "Tight data should have higher stability"  # Check stability
        assert width_tight < width_wide, "Tight data should have narrower CI"  # Check CI