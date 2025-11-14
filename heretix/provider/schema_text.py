from __future__ import annotations

"""Shared schema instructions for provider adapters."""


RPL_SAMPLE_JSON_SCHEMA = (
    "Return ONLY JSON with this shape: "
    '{"belief":{"prob_true":0-1 with two decimals,"label":"very_unlikely|unlikely|uncertain|likely|very_likely"},'
    '"reasons":2-4 concise strings,"assumptions":0-3 strings,"uncertainties":0-3 strings,'
    '"flags":{"refused":bool,"off_topic":bool}}. '
    "No markdown, prefixes, or commentary."
)


__all__ = ["RPL_SAMPLE_JSON_SCHEMA"]
