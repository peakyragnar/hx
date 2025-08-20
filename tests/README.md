# Heretix RPL Statistical Tests

Comprehensive test suite for verifying statistical correctness of the Raw Prior Lens (RPL) evaluation system.

## 🏃 Quick Start (using uv)

```bash
# Install test dependencies
uv pip install -e ".[test]"

# Run fast tests (pre-commit)
uv run pytest tests -m "not slow"

# Run all tests
uv run pytest tests

# Run with coverage
uv run pytest tests --cov=heretix_rpl
```

## 📁 Test Structure

- **conftest.py** - Fixtures, mocks, and test configuration
- **test_logit_transforms.py** - Probability ↔ logit transformations
- **test_aggregation_methods.py** - Simple and clustered aggregation
- **test_seed_determinism.py** - Deterministic seed generation
- **test_edge_cases.py** - Boundary conditions and edge cases
- **test_stability_metrics.py** - Stability score calculations
- **test_property_based.py** - Hypothesis-based invariant tests
- **test_end_to_end.py** - Integration tests with stubbed API calls

## 🏷️ Test Categories

### Fast Tests (Default)
- Run in < 2 seconds total
- Execute on every commit via git hook
- Core functionality and edge cases

### Slow Tests
- Marked with `@pytest.mark.slow`
- Bootstrap coverage tests, large sample convergence
- Run on push and in CI

## 🪝 Git Hooks

### Pre-commit (Fast Tests)
```bash
# Automatically runs fast tests
git commit -m "message"

# Bypass if needed
git commit -m "message" --no-verify
```

### Pre-push (Full Suite)
```bash
# Automatically runs all tests
git push
```

## 🧪 Key Test Properties

### Statistical Correctness
- **Logit/Sigmoid Inverse**: Round-trip transformations preserve values
- **Equal Template Weighting**: Replicate imbalance doesn't affect estimates
- **Bootstrap Coverage**: ~95% CIs contain true mean ~95% of time
- **Trimmed Mean Robustness**: Outliers properly handled

### Determinism
- Same configuration → same seed → same results
- Different configurations → different seeds
- Environment overrides work correctly

### Edge Cases
- Minimum samples (n=3)
- Single template scenarios
- Extreme probabilities (near 0 and 1)
- All identical values

## 🔧 Running Specific Tests

```bash
# Run single test file
pytest tests/test_logit_transforms.py

# Run specific test
pytest tests/test_edge_cases.py::TestMinimalData::test_minimum_samples_threshold

# Run with verbose output
pytest tests -v

# Run with detailed failure info
pytest tests --tb=long
```

## 📊 Coverage Goals

- Core functions: 100% coverage
- Edge cases: Comprehensive boundary testing
- Property tests: Bounded invariants verified
- Integration: Full pipeline with mocked externals

## 🐛 Debugging Tests

```bash
# Run with Python debugger
pytest tests --pdb

# Run with print statements visible
pytest tests -s

# Run with maximum verbosity
pytest tests -vv
```

## 🚀 CI/CD Integration

GitHub Actions runs tests on:
- Python 3.10, 3.11, 3.12
- Every push to main/develop
- All pull requests

## 📝 Adding New Tests

1. Choose appropriate file or create new one
2. Use fixtures from conftest.py
3. Mark slow tests with `@pytest.mark.slow`
4. Follow naming convention: `test_<functionality>`
5. Include docstrings explaining test purpose
6. Use `pytest.approx()` for floating point comparisons

## ⚠️ Important Notes

- All OpenAI calls are **stubbed** - no external dependencies
- Tests use **deterministic seeds** for reproducibility
- **Property tests** use bounded examples to maintain speed
- **Numeric tolerances** prevent brittle assertions