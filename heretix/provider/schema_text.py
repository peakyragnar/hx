from __future__ import annotations

"""Shared schema instructions for provider adapters."""


RPL_SAMPLE_JSON_SCHEMA = (
    "Return ONLY JSON matching this schema: "
    "{ \"belief\": {\"prob_true\": number between 0 and 1 (two decimals), "
    "\"label\": one of [very_unlikely, unlikely, uncertain, likely, very_likely]}, "
    "\"reasons\": [2-4 concise strings], "
    "\"assumptions\": [0-3 strings], \"uncertainties\": [0-3 strings], "
    "\"flags\": {\"refused\": bool, \"off_topic\": bool} } "
    "Return the JSON object only; no markdown, preamble, or commentary."
)


__all__ = ["RPL_SAMPLE_JSON_SCHEMA"]
