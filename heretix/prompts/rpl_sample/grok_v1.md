Provider notes (xAI Grok):
- Return a single minified JSON object; no markdown fences or commentary.
- Grok may prepend meta text; explicitly avoid any prefix such as "Sure" or "Answer:".
- If JSON parsing fails, callers will retry; do not include apologies or follow-up prose.
