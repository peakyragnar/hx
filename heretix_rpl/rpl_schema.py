RPL_JSON_SCHEMA = {
    "name": "RPLScore",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prob_true": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "confidence_self": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "reasoning_bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
            "contrary_considerations": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
            "ambiguity_flags": {"type": "array", "items": {"type": "string"}}
        },
        "required": [
            "prob_true", "confidence_self",
            "assumptions", "reasoning_bullets",
            "contrary_considerations", "ambiguity_flags"
        ]
    }
}