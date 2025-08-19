# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ IMPORTANT: Core Design Integrity

**NEVER make changes to the core design methodology without explicitly asking the user first.** This includes:
- Statistical aggregation methods
- Evaluation lens definitions
- Sampling strategies
- Core metrics calculations
- Economic model fundamentals

Always propose changes and get approval before modifying these foundational elements.

## Project Overview

This repository contains the conceptual design for **Heretix**, a truth-scoring and belief evaluation platform. The system is designed to measure how AI models' beliefs change when exposed to different types of evidence and sources, with the goal of exposing consensus amplification and rewarding genuine intellectual discovery.

## Core Architecture Concepts

The system operates on four evaluation lenses:

1. **Raw Prior Lens (RPL)** - Model responses without external retrieval or citations
2. **Mainstream Evidence Lens (MEL)** - Responses constrained to canonical/official sources  
3. **Heterodox Evidence Lens (HEL)** - Non-mainstream but documented sources
4. **Sandbox Evidence Lens (SEL)** - Reasoning from only provided artifacts

## Key Metrics

- **Shock Index (SI)**: Difference between raw prior and heterodox evidence beliefs
- **Amplification Gap (AG)**: How mainstream retrieval reinforces or corrects model priors
- **Source Concentration (SC)**: Citation diversity measurement
- **Information Gain (IG)**: Belief updates measured via KL-divergence

## Economic Model

The platform uses a dual-pool system (Heretic/Orthodox) with:
- **Dynamic Claim Markets (DCM)**: Share-based betting on claim outcomes
- **Epistemic Prediction Communities (EPC)**: Rewards for durable belief updates
- **Exploration Track**: Reputation-based discovery without monetary stakes
- **Adjudication Track**: Cash payouts for robust outcomes

## Current Implementation: Raw Prior Lens (RPL)

The RPL module is now implemented with a robust statistical methodology designed to handle GPT-5's inherent stochasticity.

### Clustered Aggregation Methodology

The system uses a **clustered aggregation** approach to ensure unbiased estimation:

#### The Problem We Solved
When requesting K paraphrases but having only 5 templates, the system would wrap around (e.g., K=7 means templates 0,1 get used twice). This created bias where some paraphrase templates had double weight in the final estimate.

#### The Solution: Equal-by-Template Aggregation
1. **Clustering**: Samples are grouped by `prompt_sha256` (unique paraphrase hash)
2. **Per-Template Means**: Each template's replicates are averaged in log-odds space
3. **Equal Weighting**: Template means are averaged equally (regardless of sample count)
4. **Cluster Bootstrap**: Confidence intervals use cluster-aware resampling:
   - Resample templates (with replacement)
   - Then resample replicates within each template
   - This preserves the hierarchical structure of the data

#### Statistical Properties
- **K×R Sampling**: K paraphrases × R replicates (default: 7×3 = 21 samples)
- **Log-odds Transformation**: All averaging happens in logit space to avoid probability averaging artifacts
- **Bootstrap CI**: 2000 bootstrap iterations for 95% confidence intervals
- **Stability Score**: S = 1/(1 + IQR_logit) where IQR is computed on per-template means

#### Diagnostic Outputs
The system now reports:
- `paraphrase_balance`: Shows counts per template and imbalance ratio
- `imbalance_ratio`: Max/min template counts (ideal = 1.0)
- `template_iqr_logit`: Spread of template means (consistency measure)

### Backwards Compatibility
- Default: `--agg clustered` (correct, unbiased estimator)
- Legacy: `--agg simple` (old behavior for comparison)

## Future Implementation Priorities

When implementing remaining components:

- Focus on the four-lens evaluation architecture
- Implement reliability scoring for non-academic evidence sources
- Build the dual-track system (exploration vs adjudication)
- Create mechanisms to measure and reward information gain rather than raw point changes