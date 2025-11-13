Provider notes (DeepSeek R1):
- Suppress any "thought" channel and output the JSON object directly.
- Keep `support_bullets` and `oppose_bullets` lists balanced (max three entries each).
- Clamp `stance_prob_true` within [0,1] with at most two decimals.
