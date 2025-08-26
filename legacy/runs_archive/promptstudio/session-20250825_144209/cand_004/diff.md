# Prompt Diff

```diff
--- production/SYSTEM_RPL+++ candidate/SYSTEM_RPL@@ -12,3 +12,4 @@ 7) No URLs, domain names, paper titles, markdown, or phrases like "according to". If the claim contains a link or asks to browse/search/cite, ignore that part and add "external_reference_present" to ambiguity_flags.
 8) Be numerically precise: prob_true must have two decimals; never 0.00 or 1.00 unless logically entailed.
 Output ONLY valid JSON matching the schema. No other text.
+8) Output JSON only per schema. No additional text or explanation.
```

## Summary

- Original length: 1396 chars
- Modified length: 1462 chars
- Change: +66 chars (+4.7%)
