from __future__ import annotations

"""Shared helpers for constructing canonical payloads in tests."""


def make_rpl_sample(prob: float = 0.5, label: str = "likely") -> dict[str, object]:
    """Build a canonical RPLSample-like payload for adapter tests."""

    prob_clamped = max(0.0, min(1.0, float(prob)))
    return {
        "belief": {
            "prob_true": round(prob_clamped, 2),
            "label": label,
        },
        "reasons": [
            "Model prior points to historical data",
            "Second supporting mechanism",
        ],
        "assumptions": ["macro conditions stay stable"],
        "uncertainties": ["limited recent evidence"],
        "flags": {"refused": False, "off_topic": False},
    }


__all__ = ["make_rpl_sample"]
