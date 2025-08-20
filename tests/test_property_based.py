"""
Property-Based Tests Using Hypothesis

Tests mathematical invariants and properties across randomly generated inputs.
Validates transform relationships, aggregation properties, and stability bounds.
Uses Hypothesis to generate edge cases and verify statistical correctness.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from hypothesis import given, strategies as st, assume, settings  # Property testing
from heretix_rpl.rpl_eval import _logit, _sigmoid           # Transform functions
from heretix_rpl.aggregation import aggregate_clustered, _trimmed_mean  # Aggregation functions


# Custom strategies for bounded data generation
@st.composite
def probability_strategy(draw):                             # Generate valid probabilities
    """Strategy for generating valid probabilities."""      # Strategy purpose
    return draw(st.floats(min_value=0.001, max_value=0.999))  # Avoid extreme edges


@st.composite  
def logit_strategy(draw):                                   # Generate valid logits
    """Strategy for generating reasonable logit values."""   # Strategy purpose
    return draw(st.floats(min_value=-5.0, max_value=5.0))  # Reasonable range


@st.composite
def template_dict_strategy(draw):                           # Generate template data
    """Strategy for generating template dictionaries."""     # Strategy purpose
    n_templates = draw(st.integers(min_value=2, max_value=10))  # Number of templates
    templates = {}                                           # Template dictionary
    
    for i in range(n_templates):                            # Create each template
        n_replicates = draw(st.integers(min_value=1, max_value=5))  # Replicates per template
        logits = draw(st.lists(                             # Generate logits
            logit_strategy(),
            min_size=n_replicates,
            max_size=n_replicates
        ))
        templates[f"template_{i}"] = logits                 # Add to dictionary
    
    return templates                                         # Return template dict


class TestTransformProperties:                              # Test transform invariants
    """Property-based tests for probability transformations."""  # Class purpose
    
    @given(probability_strategy())
    @settings(max_examples=100, deadline=1000)              # Limit examples for speed
    def test_logit_sigmoid_inverse(self, p):                # Test inverse property
        """For any valid probability, sigmoid(logit(p)) ≈ p."""  # Test purpose
        reconstructed = _sigmoid(_logit(p))                 # Round trip
        assert abs(reconstructed - p) < 1e-10, f"Failed for p={p}"  # Should match
    
    @given(logit_strategy())
    @settings(max_examples=100, deadline=1000)
    def test_sigmoid_bounded(self, logit):                  # Test bounds
        """For any logit, sigmoid output is in [0, 1]."""   # Test purpose
        p = _sigmoid(logit)                                 # Convert to probability
        assert 0 <= p <= 1, f"sigmoid({logit}) = {p} out of bounds"  # Must be valid
    
    @given(probability_strategy(), probability_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_logit_ordering_preserved(self, p1, p2):        # Test ordering
        """If p1 < p2, then logit(p1) < logit(p2)."""       # Test purpose
        assume(p1 != p2)                                    # Skip equal values
        
        if p1 < p2:                                         # Order established
            assert _logit(p1) < _logit(p2), f"Ordering not preserved for {p1}, {p2}"  # Check order
        else:                                                # Reverse order
            assert _logit(p1) > _logit(p2), f"Ordering not preserved for {p1}, {p2}"  # Check order
    
    @given(probability_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_logit_sign_correct(self, p):                   # Test sign
        """logit(p) < 0 iff p < 0.5, logit(p) > 0 iff p > 0.5."""  # Test purpose
        logit = _logit(p)                                   # Calculate logit
        
        if p < 0.5:                                         # Below half
            assert logit < 0, f"logit({p}) should be negative"  # Must be negative
        elif p > 0.5:                                       # Above half
            assert logit > 0, f"logit({p}) should be positive"  # Must be positive
        else:                                                # Exactly half
            assert abs(logit) < 1e-10, f"logit(0.5) should be ~0"  # Should be zero


class TestAggregationInvariants:                            # Test aggregation properties
    """Property-based tests for aggregation invariants."""   # Class purpose
    
    @given(template_dict_strategy())
    @settings(max_examples=20, deadline=2000)               # Fewer examples (slower test)
    def test_permutation_invariance(self, templates):        # Test order independence
        """Aggregation is invariant to template key ordering."""  # Test purpose
        # Create permuted version
        keys = list(templates.keys())                       # Get keys
        permuted = {f"new_{i}": templates[keys[-(i+1)]]    # Reverse order
                   for i in range(len(keys))}
        
        # Use fixed seed for deterministic comparison
        rng1 = np.random.default_rng(42)                    # First RNG
        result1 = aggregate_clustered(templates, B=50, rng=rng1)  # Original order
        
        rng2 = np.random.default_rng(42)                    # Same seed
        result2 = aggregate_clustered(permuted, B=50, rng=rng2)  # Permuted order
        
        # Point estimates should be very close (equal weighting)
        assert abs(result1[0] - result2[0]) < 0.01, "Permutation affected result"  # Should match
    
    @given(template_dict_strategy())
    @settings(max_examples=20, deadline=2000)
    def test_replicate_duplication_invariance(self, templates):  # Test equal weighting
        """Duplicating replicates within template doesn't change result much."""  # Test purpose
        assume(len(templates) >= 3)                         # Need enough templates
        
        # Pick first template to duplicate
        first_key = list(templates.keys())[0]               # Get first key
        
        # Original aggregation
        rng1 = np.random.default_rng(99)                    # First RNG
        result1 = aggregate_clustered(templates, B=50, rng=rng1)  # Original
        
        # Duplicate replicates in first template
        modified = templates.copy()                         # Copy templates
        modified[first_key] = modified[first_key] * 3       # Triple replicates
        
        rng2 = np.random.default_rng(99)                    # Same seed
        result2 = aggregate_clustered(modified, B=50, rng=rng2)  # Modified
        
        # Results should be similar (equal template weighting)
        assert abs(result1[0] - result2[0]) < 0.1, "Replicate duplication changed result"  # Close
    
    @given(st.lists(logit_strategy(), min_size=5, max_size=20))
    @settings(max_examples=50, deadline=1000)
    def test_trimmed_mean_bounds(self, logits):             # Test trimmed mean bounds
        """Trimmed mean is between min and max of retained values."""  # Test purpose
        data = np.array(logits)                             # Convert to array
        trim = 0.2                                          # 20% trim
        
        result = _trimmed_mean(data, trim=trim)             # Calculate trimmed mean
        
        # Find what would be retained
        sorted_data = np.sort(data)                         # Sort data
        n = len(sorted_data)                                # Data size
        k = int(n * trim)                                   # Trim count
        
        if 2*k < n:                                         # If trimming applied
            retained = sorted_data[k:n-k]                   # Middle values
            # Allow small floating point errors
            min_val = float(retained.min())
            max_val = float(retained.max())
            assert result >= min_val - 1e-10, f"Trimmed mean {result} below min {min_val}"
            assert result <= max_val + 1e-10, f"Trimmed mean {result} above max {max_val}"
        else:                                                # Fallback to mean
            assert result == pytest.approx(np.mean(data), rel=1e-10)  # Should be regular mean


class TestStabilityProperties:                              # Test stability invariants
    """Property-based tests for stability score properties."""  # Class purpose
    
    @given(st.floats(min_value=0.0, max_value=10.0))
    @settings(max_examples=100, deadline=1000)
    def test_stability_range(self, iqr):                    # Test stability bounds
        """Stability score is always in (0, 1]."""          # Test purpose
        stability = 1.0 / (1.0 + iqr)                       # Calculate stability
        assert 0 < stability <= 1, f"Stability {stability} out of range for IQR {iqr}"  # Check bounds
    
    @given(st.floats(min_value=0.0, max_value=10.0),
           st.floats(min_value=0.0, max_value=10.0))
    @settings(max_examples=50, deadline=1000)  
    def test_stability_monotonic(self, iqr1, iqr2):         # Test monotonicity
        """Stability decreases monotonically with IQR."""   # Test purpose
        if abs(iqr1 - iqr2) < 1e-10:                        # Skip if IQRs are essentially equal
            assume(False)                                    # Skip this case
        
        stability1 = 1.0 / (1.0 + iqr1)                     # First stability
        stability2 = 1.0 / (1.0 + iqr2)                     # Second stability
        
        if iqr1 < iqr2:                                     # First IQR smaller
            assert stability1 >= stability2 or abs(stability1 - stability2) < 1e-10, "Stability should decrease with IQR"  # Check ordering with tolerance
        else:                                                # Second IQR smaller
            assert stability1 <= stability2 or abs(stability1 - stability2) < 1e-10, "Stability should decrease with IQR"  # Check ordering with tolerance
    
    @given(st.lists(logit_strategy(), min_size=3, max_size=20))
    @settings(max_examples=50, deadline=1000)
    def test_stability_identical_values(self, logits):       # Test identical case
        """All identical values should give stability = 1."""  # Test purpose
        # Make all values identical
        identical = [logits[0]] * len(logits)               # All same value
        
        from heretix_rpl.rpl_eval import compute_stability  # Import function
        stability = compute_stability(identical)             # Calculate stability
        
        assert stability == 1.0, "Identical values should have perfect stability"  # Perfect stability


class TestBootstrapProperties:                              # Test bootstrap invariants
    """Property-based tests for bootstrap confidence intervals."""  # Class purpose
    
    @given(st.lists(logit_strategy(), min_size=5, max_size=30),
           st.integers(min_value=10, max_value=100))
    @settings(max_examples=10, deadline=5000)               # Very few (slow test)
    def test_ci_contains_point_estimate(self, logits, B):    # Test CI property
        """CI should always contain the point estimate."""   # Test purpose
        from heretix_rpl.aggregation import aggregate_simple  # Import function
        
        mean, (lo, hi), _ = aggregate_simple(logits, B=B)   # Calculate with CI
        
        assert lo <= mean <= hi, f"CI [{lo}, {hi}] doesn't contain mean {mean}"  # Must contain
    
    @given(st.lists(logit_strategy(), min_size=10, max_size=20))
    @settings(max_examples=5, deadline=5000)                # Very few (slow test)
    def test_ci_width_positive(self, logits):               # Test CI width
        """CI width should be positive for non-identical data."""  # Test purpose
        assume(len(set(logits)) > 1)                        # Not all identical
        
        from heretix_rpl.aggregation import aggregate_simple  # Import function
        _, (lo, hi), _ = aggregate_simple(logits, B=100)    # Calculate CI
        
        assert hi > lo, "CI width should be positive for varied data"  # Positive width