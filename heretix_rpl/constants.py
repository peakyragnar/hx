"""
Global constants for gates and thresholds used across the RPL system.

Minimal, explicit defaults to avoid magic numbers scattered in code.
"""
from __future__ import annotations

# Auto‑RPL gate defaults (frozen policy)
GATE_CI_WIDTH_MAX_DEFAULT: float = 0.20
GATE_STABILITY_MIN_DEFAULT: float = 0.70
GATE_IMBALANCE_MAX_DEFAULT: float = 1.50
GATE_IMBALANCE_WARN_DEFAULT: float = 1.25

# Drift thresholds for monitor baseline comparisons
DRIFT_P_THRESH_DEFAULT: float = 0.10
DRIFT_STAB_DROP_DEFAULT: float = 0.20
DRIFT_CI_INCREASE_DEFAULT: float = 0.10

