"""
Tests for Calibrated Stability Metrics

Validates the parametric stability mapping formula and categorical band assignments.
Ensures calibrated scores match expected anchors and preserve monotonicity.
Tests both direct functions and integrated compute_stability_calibrated.
"""
import pytest
import numpy as np
from heretix_rpl.metrics import (
    stability_from_iqr, 
    stability_band_from_iqr,
    compute_stability_calibrated
)


class TestCalibratedStability:
    """Test the calibrated stability scoring function."""
    
    def test_stability_anchors(self):
        """Test that calibrated formula produces expected values at key points."""
        # With default s=0.2, alpha=1.7
        
        # Very low IQR -> high stability
        assert stability_from_iqr(0.02) > 0.95, "Very low IQR should give high stability"
        
        # Midpoint: IQR=0.2 -> stability=0.5
        assert pytest.approx(stability_from_iqr(0.2), abs=0.01) == 0.5, "IQR=s should give stability=0.5"
        
        # High IQR -> low stability
        assert stability_from_iqr(2.0) < 0.05, "High IQR should give low stability"
    
    def test_stability_monotonic(self):
        """Test that stability decreases monotonically with IQR."""
        iqr_values = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
        stabilities = [stability_from_iqr(iqr) for iqr in iqr_values]
        
        for i in range(len(stabilities) - 1):
            assert stabilities[i] > stabilities[i+1], "Stability should decrease with IQR"
    
    def test_stability_bounds(self):
        """Test that stability is always in [0, 1]."""
        for iqr in [0, 0.001, 0.1, 1, 10, 100, 1000]:
            s = stability_from_iqr(iqr)
            assert 0 <= s <= 1, f"Stability {s} out of bounds for IQR {iqr}"
    
    def test_custom_parameters(self):
        """Test that custom s and alpha parameters work correctly."""
        # Different midpoint
        assert pytest.approx(stability_from_iqr(0.5, s=0.5), abs=0.01) == 0.5
        
        # Different steepness
        s_steep = stability_from_iqr(0.3, s=0.2, alpha=3.0)
        s_gentle = stability_from_iqr(0.3, s=0.2, alpha=1.0)
        assert s_steep < s_gentle, "Higher alpha should give steeper falloff"


class TestStabilityBands:
    """Test categorical stability bands."""
    
    def test_band_thresholds(self):
        """Test that bands match expected IQR ranges."""
        # Default thresholds: high <= 0.05, medium <= 0.30
        
        assert stability_band_from_iqr(0.02) == "high"
        assert stability_band_from_iqr(0.05) == "high"
        assert stability_band_from_iqr(0.06) == "medium"
        assert stability_band_from_iqr(0.20) == "medium"
        assert stability_band_from_iqr(0.30) == "medium"
        assert stability_band_from_iqr(0.31) == "low"
        assert stability_band_from_iqr(2.0) == "low"
    
    def test_custom_thresholds(self):
        """Test that custom thresholds work correctly."""
        assert stability_band_from_iqr(0.15, high_max=0.1, medium_max=0.2) == "medium"
        assert stability_band_from_iqr(0.25, high_max=0.1, medium_max=0.2) == "low"


class TestComputeStabilityCalibrated:
    """Test the compute function that returns both score and IQR."""
    
    def test_returns_both_values(self):
        """Test that function returns (score, iqr) tuple."""
        logits = [0.1, 0.2, 0.3, 0.4, 0.5]
        score, iqr = compute_stability_calibrated(logits)
        
        assert isinstance(score, float)
        assert isinstance(iqr, float)
        assert 0 <= score <= 1
        assert iqr >= 0
    
    def test_consistent_with_direct_calculation(self):
        """Test that compute function matches direct calculation."""
        logits = [0.1, 0.2, 0.3, 0.4, 0.5]
        score, iqr = compute_stability_calibrated(logits)
        
        # Verify IQR calculation
        expected_iqr = np.percentile(logits, 75) - np.percentile(logits, 25)
        assert pytest.approx(iqr, abs=1e-10) == expected_iqr
        
        # Verify score calculation
        expected_score = stability_from_iqr(expected_iqr)
        assert pytest.approx(score, abs=1e-10) == expected_score
    
    def test_edge_cases(self):
        """Test edge cases like identical values."""
        # All identical -> IQR = 0 -> stability = 1
        score, iqr = compute_stability_calibrated([0.5] * 10)
        assert iqr == 0
        assert score == 1.0
        
        # Wide spread
        score, iqr = compute_stability_calibrated([-10, -5, 0, 5, 10])
        assert iqr > 5
        assert score < 0.01