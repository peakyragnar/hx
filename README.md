# Heretix - Raw Prior Lens (RPL) Evaluator

A truth-scoring and belief evaluation platform that measures how AI models' beliefs change when exposed to different types of evidence and sources.

## Overview

Heretix implements the Raw Prior Lens (RPL) evaluation system for GPT-5, using robust statistical methods to handle the model's stochastic nature. The system evaluates claims by sampling multiple paraphrases and replicates, then aggregates results using median-of-means in log-odds space.

## Features

- **K×R Sampling**: Multiple paraphrases × replicates for robust evaluation
- **Statistical Aggregation**: Median-of-means in log-odds space
- **Confidence Intervals**: 95% bootstrap CIs for uncertainty quantification
- **Stability Scoring**: Measures consistency across samples
- **GPT-5 Support**: Uses OpenAI's Responses API with proper parameter handling

## Installation

1. Clone the repository:
```bash
git clone https://github.com/peakyragnar/hx.git
cd hx
```

2. Install uv (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install dependencies:
```bash
uv sync
```

4. Set up your OpenAI API key:
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

## Usage

Basic usage with defaults (K=7 paraphrases, R=3 replicates):
```bash
uv run heretix-rpl --claim "Your claim here"
```

Custom sampling parameters:
```bash
uv run heretix-rpl --claim "Your claim" --k 5 --r 2 --out results.json
```

Using different models:
```bash
# GPT-5 (default)
uv run heretix-rpl --claim "Your claim" --model gpt-5

# GPT-5 nano (faster, less capable)
uv run heretix-rpl --claim "Your claim" --model gpt-5-nano

# GPT-4 (legacy, deterministic)
uv run heretix-rpl --claim "Your claim" --model gpt-4o
```

## Output Format

The system outputs JSON with:
- `prob_true_rpl`: Robust probability estimate (0-1)
- `ci95`: 95% confidence interval [lower, upper]
- `stability_score`: Consistency measure (0-1)
- `is_stable`: Boolean flag (true if CI width d 0.2)
- Full provenance and individual sample results

## Architecture

The system uses four evaluation lenses (RPL implemented):
1. **Raw Prior Lens (RPL)** - Model responses without external retrieval
2. **Mainstream Evidence Lens (MEL)** - Planned
3. **Heterodox Evidence Lens (HEL)** - Planned
4. **Sandbox Evidence Lens (SEL)** - Planned

## Requirements

- Python 3.10+
- OpenAI API key with GPT-5 access
- uv package manager

## License

[Add your license here]