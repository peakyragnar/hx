# Prompt Diff

```diff
--- production/SYSTEM_RPL+++ candidate/SYSTEM_RPL@@ -13,3 +13,4 @@ 9) prob_true must have two decimals; never 0.00 or 1.00 unless logically entailed.
 
 Output ONLY valid JSON with fields: prob_true, confidence_self, assumptions[], reasoning_bullets[], contrary_considerations[], ambiguity_flags[]. No other text.
+8) Output JSON only per schema. No additional text or explanation.
```

## Summary

- Original length: 1780 chars
- Modified length: 1846 chars
- Change: +66 chars (+3.7%)
