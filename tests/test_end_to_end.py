"""
End-to-End Tests with Stubbed OpenAI Calls

Tests complete evaluation pipeline without external dependencies using mock responses.
Validates full RPL workflow including configuration, sampling, and result formatting.
Ensures system behavior correctness across different aggregation methods.
"""
import pytest                                                 # Testing framework
import numpy as np                                           # Numerical operations
from unittest.mock import patch, MagicMock                  # Mocking utilities
import hashlib                                               # For hash generation
from heretix_rpl.rpl_eval import evaluate_rpl_gpt5          # Main function to test
from heretix_rpl.config import RPLConfig, load_config       # Configuration


class TestEvaluateRPLGPT5:                                  # Test main evaluation function
    """Test the main evaluate_rpl_gpt5 function with mocked API calls."""  # Class purpose
    
    def test_basic_evaluation_flow(self, monkeypatch, mock_openai_response):  # Test basic flow
        """Test basic evaluation flow with stubbed responses."""  # Test purpose
        # Create deterministic mock responses
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            """Return deterministic response based on inputs."""  # Function purpose
            # Use hash of inputs for variety but determinism
            input_hash = hashlib.sha256(                    # Hash inputs
                f"{claim_text}{paraphrase}{model}".encode()
            ).hexdigest()
            
            # Generate probability from hash
            prob = 0.3 + (int(input_hash[:8], 16) % 40) / 100.0  # Range [0.3, 0.7]
            return mock_openai_response(prob_true=prob)     # Return mock response
        
        # Patch the API call
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Run evaluation
        result = evaluate_rpl_gpt5(                         # Call main function
            "test claim",
            model="gpt-5",
            K=3,                                            # 3 paraphrases
            R=2,                                            # 2 replicates each
            agg="clustered"
        )
        
        # Verify structure
        assert "aggregates" in result                       # Has aggregates
        assert "prob_true_rpl" in result["aggregates"]      # Has probability
        assert "ci95" in result["aggregates"]               # Has CI
        assert "stability_score" in result["aggregates"]    # Has stability
        assert "is_stable" in result["aggregates"]          # Has stability flag
        
        # Verify values are reasonable
        prob = result["aggregates"]["prob_true_rpl"]        # Get probability
        assert 0 <= prob <= 1, "Probability out of bounds"  # Valid probability
        
        ci = result["aggregates"]["ci95"]                   # Get CI
        assert ci[0] <= prob <= ci[1], "CI doesn't contain estimate"  # CI contains mean
        
        stability = result["aggregates"]["stability_score"]  # Get stability
        assert 0 < stability <= 1, "Stability out of bounds"  # Valid stability
    
    def test_paraphrase_clustering(self, monkeypatch, mock_openai_response):  # Test clustering
        """Test that paraphrases are properly clustered by hash."""  # Test purpose
        paraphrase_hashes = []                              # Store hashes
        
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            """Track paraphrase hashes."""                  # Function purpose
            # Generate hash for this paraphrase
            prompt_hash = hashlib.sha256(                   # Hash prompt
                f"{paraphrase}".encode()
            ).hexdigest()
            paraphrase_hashes.append(prompt_hash)           # Store hash
            
            return mock_openai_response(                    # Return response
                prob_true=0.5,
                paraphrase_idx=len(paraphrase_hashes) - 1
            )
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Run with K=7 (will wrap around 5 templates)
        result = evaluate_rpl_gpt5("test", K=7, R=1)        # Run evaluation
        
        # Check paraphrase results
        assert len(result["paraphrase_results"]) == 7       # 7 samples
        
        # Check that templates wrapped correctly
        # With 5 templates and K=7, templates 0 and 1 should appear twice
        unique_hashes = len(set(paraphrase_hashes))         # Count unique
        assert unique_hashes == 5, "Should have 5 unique paraphrase templates"  # 5 templates
    
    def test_configuration_usage(self, monkeypatch, mock_openai_response):  # Test config
        """Test that configuration is properly used."""      # Test purpose
        # Create custom config
        config = RPLConfig(                                 # Custom config
            min_samples=5,                                  # Higher minimum
            trim=0.3,                                        # More trimming
            b_clustered=200,                                # More bootstrap
            b_simple=150,
            stability_width=0.15                            # Tighter stability
        )
        
        successful_calls = 0                                # Counter
        
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            """Count successful calls."""                   # Function purpose
            nonlocal successful_calls                       # Access counter
            successful_calls += 1                           # Increment
            return mock_openai_response(prob_true=0.6)      # Return response
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Run with custom config
        result = evaluate_rpl_gpt5(                         # Run evaluation
            "test", K=3, R=2,                              # 6 total samples
            config=config
        )
        
        # Verify config was used
        assert result["aggregation"]["trim"] == 0.3        # Custom trim used
        assert result["aggregation"]["B"] == 200            # Custom B used
        assert result["aggregation"]["min_samples"] == 5    # Custom min_samples
        assert result["aggregation"]["stability_width"] == 0.15  # Custom stability
    
    def test_aggregation_method_selection(self, monkeypatch, mock_openai_response):  # Test agg selection
        """Test that aggregation method can be selected."""  # Test purpose
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            return mock_openai_response(prob_true=0.5)      # Return response
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Test clustered aggregation
        result_clustered = evaluate_rpl_gpt5(               # Clustered method
            "test", K=5, R=2, agg="clustered"
        )
        assert "equal_by_template" in result_clustered["aggregation"]["method"]  # Check method
        
        # Test simple aggregation
        result_simple = evaluate_rpl_gpt5(                  # Simple method
            "test", K=5, R=2, agg="simple"
        )
        assert result_simple["aggregation"]["method"] == "simple_mean"  # Check method
    
    def test_error_handling_partial_failures(self, monkeypatch):  # Test error handling
        """Test that partial API failures are handled gracefully."""  # Test purpose
        call_count = 0                                      # Call counter
        
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            """Fail some calls."""                          # Function purpose
            nonlocal call_count                             # Access counter
            call_count += 1                                 # Increment
            
            # Fail every 3rd call
            if call_count % 3 == 0:                         # Every third
                raise Exception("Mock API error")           # Simulate failure
            
            # Return normal response
            return {                                         # Mock response
                "raw": {"prob_true": 0.5, "confidence_self": 0.7,
                        "assumptions": [], "reasoning_bullets": ["a", "b", "c"],
                        "contrary_considerations": ["x", "y"], "ambiguity_flags": []},
                "meta": {"provider_model_id": "gpt-5", "prompt_sha256": f"hash_{call_count}"}
            }
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Run with enough samples to survive some failures
        result = evaluate_rpl_gpt5("test", K=5, R=3)        # 15 attempts
        
        # Should complete with reduced samples
        assert "aggregates" in result                       # Has results
        assert result["aggregates"]["prob_true_rpl"] is not None  # Has estimate
    
    def test_minimum_samples_enforcement(self, monkeypatch):  # Test min samples
        """Test that minimum samples requirement is enforced."""  # Test purpose
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            # Always fail to get below minimum
            raise Exception("Mock failure")                 # Always fail
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Should raise error for too few samples
        with pytest.raises(ValueError, match="Too few successful samples"):  # Expect error
            evaluate_rpl_gpt5("test", K=2, R=1)             # Only 2 attempts


class TestIntegrationWithConfig:                            # Test config integration
    """Test integration with configuration system."""        # Class purpose
    
    def test_environment_config_loading(self, monkeypatch, mock_openai_response):  # Test env config
        """Test that environment variables affect configuration."""  # Test purpose
        # Set environment variables
        monkeypatch.setenv("HERETIX_RPL_MIN_SAMPLES", "4")  # Custom min
        monkeypatch.setenv("HERETIX_RPL_TRIM", "0.25")     # Custom trim
        monkeypatch.setenv("HERETIX_RPL_B_CLUSTERED", "300")  # Custom B
        
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            return mock_openai_response(prob_true=0.5)      # Return response
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Load config (should pick up env vars)
        config = load_config()                              # Load with env
        
        # Verify env vars were loaded
        assert config.min_samples == 4                      # Custom min
        assert config.trim == 0.25                         # Custom trim
        assert config.b_clustered == 300                    # Custom B
        
        # Run evaluation (config loaded internally)
        result = evaluate_rpl_gpt5("test", K=3, R=2)        # Run evaluation
        
        # Verify config was used
        assert result["aggregation"]["min_samples"] == 4    # Env config used
        assert result["aggregation"]["trim"] == 0.25        # Env config used
        assert result["aggregation"]["B"] == 300            # Env config used
    
    def test_seed_override(self, monkeypatch, mock_openai_response):  # Test seed override
        """Test that HERETIX_RPL_SEED environment variable works."""  # Test purpose
        def mock_call(claim_text, paraphrase, model):       # Mock API call
            return mock_openai_response(prob_true=0.5)      # Return response
        
        monkeypatch.setattr(                                # Replace function
            "heretix_rpl.rpl_eval.call_rpl_once_gpt5",
            mock_call
        )
        
        # Run without seed override
        result1 = evaluate_rpl_gpt5("test", K=3, R=2)       # First run
        seed1 = result1["aggregation"]["bootstrap_seed"]    # Get seed
        
        # Set seed override
        monkeypatch.setenv("HERETIX_RPL_SEED", "99999")     # Override seed
        
        # Run with seed override
        result2 = evaluate_rpl_gpt5("test", K=3, R=2)       # Second run
        seed2 = result2["aggregation"]["bootstrap_seed"]    # Get seed
        
        assert seed2 == 99999, "Seed override not applied"  # Check override
        assert seed1 != seed2, "Seeds should differ"        # Should be different