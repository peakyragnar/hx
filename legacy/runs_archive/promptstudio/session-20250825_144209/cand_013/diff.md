# Prompt Diff

```diff
--- production/SYSTEM_RPL+++ candidate/SYSTEM_RPL@@ -13,3 +13,4 @@ 9) Two decimals for prob_true; never 0.00 or 1.00 unless entailed.
 
 Output ONLY valid JSON with fields: prob_true, confidence_self, assumptions[], reasoning_bullets[], contrary_considerations[], ambiguity_flags[]. No other text.
+8) Output JSON only per schema. No additional text or explanation.
```

## Summary

- Original length: 1410 chars
- Modified length: 1476 chars
- Change: +66 chars (+4.7%)
