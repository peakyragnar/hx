# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Current State

This repository currently contains only design documentation. No implementation code exists yet. When implementing:

- Focus on the four-lens evaluation architecture
- Implement reliability scoring for non-academic evidence sources
- Build the dual-track system (exploration vs adjudication)
- Create mechanisms to measure and reward information gain rather than raw point changes