"""
Tests for probability <-> logit transformations.

Verifies that logit and sigmoid functions are correct inverses,
handle edge cases properly, and maintain expected mathematical properties.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from heretix_rpl.rpl_eval import _logit, _sigmoid           # Functions under test


class TestLogitSigmoid:                                     # Test logit/sigmoid transforms
    """Test the core probability transformation functions."""  # Class purpose
    
    def test_inverse_relationship(self, probability_samples):  # Test inverse property
        """Verify logit and sigmoid are mathematical inverses."""  # Test purpose
        for p in probability_samples:                       # Test each probability
            reconstructed = _sigmoid(_logit(p))             # Round-trip transformation
            assert reconstructed == pytest.approx(p, rel=1e-10)  # Should match original
    
    def test_logit_clamping_lower(self):                   # Test lower bound clamping
        """Test that probabilities near 0 are clamped properly."""  # Test purpose
        # Values at or below 0 should be clamped to 1e-6
        assert _logit(0) == _logit(1e-6)                   # Zero clamped
        assert _logit(1e-10) == _logit(1e-6)               # Tiny value clamped
        assert _logit(5e-7) == _logit(1e-6)                # Below threshold clamped
        
    def test_logit_clamping_upper(self):                   # Test upper bound clamping
        """Test that probabilities near 1 are clamped properly."""  # Test purpose
        # Values at or above 1 should be clamped to 1-1e-6
        assert _logit(1) == _logit(1 - 1e-6)               # One clamped
        assert _logit(1 - 1e-10) == _logit(1 - 1e-6)       # Near one clamped
        assert _logit(1 - 5e-7) == _logit(1 - 1e-6)        # Above threshold clamped
    
    def test_logit_monotonic_increasing(self):             # Test monotonicity
        """Verify logit is strictly monotonic increasing."""  # Test purpose
        ps = np.linspace(0.01, 0.99, 100)                  # Generate probability range
        logits = [_logit(p) for p in ps]                   # Convert to logits
        
        # Check strict monotonicity
        for i in range(len(logits) - 1):                   # Compare adjacent pairs
            assert logits[i] < logits[i + 1], f"Not monotonic at index {i}"  # Must increase
    
    def test_sigmoid_bounded(self):                        # Test sigmoid bounds
        """Verify sigmoid output is always in [0, 1]."""   # Test purpose
        test_logits = [-1000, -10, -1, 0, 1, 10, 1000]    # Wide range of logits
        
        for logit in test_logits:                          # Test each logit
            p = _sigmoid(logit)                             # Convert to probability
            assert 0 <= p <= 1, f"Sigmoid({logit}) = {p} out of bounds"  # Must be valid probability
    
    def test_logit_at_half(self):                          # Test midpoint
        """Test that logit(0.5) = 0."""                    # Test purpose
        assert _logit(0.5) == pytest.approx(0, abs=1e-10)  # Logit of 0.5 is 0
        
    def test_sigmoid_at_zero(self):                        # Test midpoint
        """Test that sigmoid(0) = 0.5."""                  # Test purpose
        assert _sigmoid(0) == pytest.approx(0.5, abs=1e-10)  # Sigmoid of 0 is 0.5
    
    def test_logit_negative_for_low_p(self):               # Test sign of logit
        """Verify logit is negative for p < 0.5."""        # Test purpose
        for p in [0.1, 0.2, 0.3, 0.4, 0.49]:               # Probabilities below half
            assert _logit(p) < 0, f"logit({p}) should be negative"  # Must be negative
    
    def test_logit_positive_for_high_p(self):              # Test sign of logit
        """Verify logit is positive for p > 0.5."""        # Test purpose
        for p in [0.51, 0.6, 0.7, 0.8, 0.9]:               # Probabilities above half
            assert _logit(p) > 0, f"logit({p}) should be positive"  # Must be positive
    
    def test_symmetry_around_half(self):                   # Test symmetry property
        """Test that logit(p) = -logit(1-p)."""            # Test purpose
        test_probs = [0.1, 0.2, 0.3, 0.4]                  # Test probabilities
        
        for p in test_probs:                               # Test each probability
            logit_p = _logit(p)                            # Logit of p
            logit_complement = _logit(1 - p)               # Logit of complement
            assert logit_p == pytest.approx(-logit_complement, rel=1e-10)  # Should be negatives
    
    def test_extreme_values_dont_overflow(self, extreme_probabilities):  # Test overflow
        """Ensure extreme values don't cause overflow/underflow."""  # Test purpose
        for p in extreme_probabilities:                    # Test extreme values
            try:
                logit_val = _logit(p)                      # Attempt transformation
                sigmoid_val = _sigmoid(logit_val)          # Round trip
                
                # Should produce finite values
                assert np.isfinite(logit_val), f"logit({p}) not finite"  # Must be finite
                assert np.isfinite(sigmoid_val), f"sigmoid(logit({p})) not finite"  # Must be finite
                
            except (OverflowError, ValueError) as e:       # Catch math errors
                pytest.fail(f"Overflow/underflow for p={p}: {e}")  # Should not happen


class TestLogitProperties:                                  # Mathematical properties
    """Test mathematical properties of logit transformation."""  # Class purpose
    
    def test_logit_derivative_at_half(self):               # Test derivative
        """Test derivative of logit at p=0.5 equals 4."""   # Test purpose
        # Derivative of logit(p) = 1/(p(1-p))
        # At p=0.5: 1/(0.5*0.5) = 4
        epsilon = 1e-8                                      # Small perturbation
        p = 0.5                                             # Test point
        
        # Numerical derivative
        derivative = (_logit(p + epsilon) - _logit(p - epsilon)) / (2 * epsilon)  # Finite difference
        assert derivative == pytest.approx(4.0, rel=1e-5)  # Should be 4
    
    def test_logit_odds_relationship(self):                # Test odds interpretation
        """Verify logit equals log of odds."""             # Test purpose
        test_probs = [0.2, 0.33, 0.5, 0.67, 0.8]          # Various probabilities
        
        for p in test_probs:                               # Test each probability
            odds = p / (1 - p)                             # Calculate odds
            log_odds = np.log(odds)                        # Log of odds
            logit_val = _logit(p)                          # Logit transformation
            
            assert logit_val == pytest.approx(log_odds, rel=1e-10)  # Should match
    
    def test_sigmoid_as_cdf(self):                         # Test CDF interpretation
        """Verify sigmoid matches logistic CDF."""         # Test purpose
        # Sigmoid is the CDF of standard logistic distribution
        # Test a few values against known CDF values
        test_cases = [                                     # Known CDF values
            (0, 0.5),                                       # CDF(0) = 0.5
            (np.log(3), 0.75),                              # CDF(log(3)) = 0.75
            (-np.log(3), 0.25)                              # CDF(-log(3)) = 0.25
        ]
        
        for x, expected_cdf in test_cases:                 # Test each case
            assert _sigmoid(x) == pytest.approx(expected_cdf, rel=1e-10)  # Should match CDF