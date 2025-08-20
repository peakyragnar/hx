#!/bin/bash
# Test runner script for Heretix RPL statistical tests

echo "🧪 Heretix RPL Test Runner"
echo "========================="
echo ""

# Check if we should use uv run
if command -v uv &> /dev/null; then
    RUNNER="uv run"
    PYTEST="uv run pytest"
else
    RUNNER=""
    PYTEST="pytest"
fi

# Check for pytest
if ! $RUNNER pytest --version &> /dev/null; then
    echo "❌ pytest not found."
    echo "   Install test dependencies with: uv pip install -e '.[test]'"
    exit 1
fi

# Parse command line arguments
if [ "$1" == "fast" ]; then
    echo "Running fast tests only (no slow tests)..."
    echo ""
    $PYTEST tests -m "not slow" -v --tb=short
elif [ "$1" == "slow" ]; then
    echo "Running slow tests only..."
    echo ""
    $PYTEST tests -m "slow" -v --tb=short
elif [ "$1" == "coverage" ]; then
    echo "Running all tests with coverage report..."
    echo ""
    $PYTEST tests -v --cov=heretix_rpl --cov-report=term-missing --cov-report=html
    echo ""
    echo "📊 Coverage report generated in htmlcov/index.html"
elif [ "$1" == "watch" ]; then
    echo "Running tests in watch mode (requires pytest-watch)..."
    echo "Install with: uv pip install pytest-watch"
    echo ""
    $RUNNER ptw tests -- -m "not slow" --tb=short
else
    echo "Running all tests..."
    echo ""
    $PYTEST tests -v --tb=short
fi

# Report result
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Tests completed successfully!"
else
    echo ""
    echo "❌ Some tests failed. See output above for details."
    exit 1
fi