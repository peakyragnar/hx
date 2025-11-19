Provider notes (OpenAI GPT-5):
- Assume JSON schema mode is available; respond with a single JSON object and nothing else.
- Do not include reasoning-mode metadata unless the API requires it. If the platform rejects reasoning flags, retry silently without them.
- Keep total output under 600 tokens; trim lists if needed but preserve schema validity.
