"""
JSON Schema for Raw Prior Lens (RPL) Model Responses

This module defines the structured output schema that models must follow when
providing RPL evaluations. The schema enforces required fields, data types,
and constraints to ensure consistent, parseable responses.
"""
RPL_JSON_SCHEMA = {                                          # OpenAI structured output schema
    "name": "RPLScore",                                      # Schema name identifier
    "strict": True,                                          # Strict mode - no extra fields allowed
    "schema": {                                              # Schema definition
        "type": "object",                                    # Root type is JSON object
        "additionalProperties": False,                       # No additional properties allowed
        "properties": {                                      # Define required fields
            "prob_true": {"type": "number", "minimum": 0.0, "maximum": 1.0},  # Probability [0,1]
            "confidence_self": {"type": "number", "minimum": 0.0, "maximum": 1.0},  # Self-confidence [0,1]
            "assumptions": {"type": "array", "items": {"type": "string"}},  # Array of assumption strings
            "reasoning_bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},  # 3-6 reasoning points
            "contrary_considerations": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},  # 2-4 counterarguments
            "ambiguity_flags": {"type": "array", "items": {"type": "string"}}  # Array of ambiguity markers
        },
        "required": [                                        # All these fields are required
            "prob_true", "confidence_self",                  # Core probability and confidence
            "assumptions", "reasoning_bullets",              # Reasoning structure
            "contrary_considerations", "ambiguity_flags"     # Critical thinking elements
        ]
    }
}