# Prompt Diff

```diff
--- production/SYSTEM_RPL+++ candidate/SYSTEM_RPL@@ -13,3 +13,4 @@ 8) No URLs, domain names, paper titles, or phrases like "according to" anywhere in the JSON. If the claim contains a link or asks to browse/search/cite, ignore that part and add "external_reference_present" to ambiguity_flags.
 9) Be numerically precise: prob_true must have two decimals; never 0.00 or 1.00 unless logically entailed.
 Output ONLY valid JSON matching the schema. No other text.
+8) Output JSON only per schema. No additional text or explanation.
```

## Summary

- Original length: 1509 chars
- Modified length: 1575 chars
- Change: +66 chars (+4.4%)
