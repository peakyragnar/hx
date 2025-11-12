# Grok Explanation Fixes - Implementation Summary

## Problem Statement

Grok was producing poor explanations for non-technical users:
- Model errors leaked into user-facing text
- Generic/technical language instead of concrete examples
- Local UI (serve.py) differed from production API output
- No quality gates to catch low-quality explanations

---

## Fixes Implemented

### ✅ Fix #1: Model Accessibility Verification

**Files Changed**: `scripts/test_grok_models.py` (NEW)

**What Changed**:
- Created diagnostic script to test all Grok model variants
- Tests: `grok-4-0709`, `grok-4-fast-non-reasoning`, `grok-beta`, etc.
- Reports which models are accessible with your API key

**Usage**:
```bash
uv run python scripts/test_grok_models.py
```

---

### ✅ Fix #2: Error Sanitization

**Files Changed**: `heretix/simple_expl.py`

**What Changed**:
- Expanded error pattern detection from 5 → 30+ patterns
- Added JSON error object detection
- Filters: "error code", "model_not_found", "authentication failed", etc.

**Before**:
```json
{
  "lines": [
    "invalid_response: model_not_found",
    "Error code: 404"
  ]
}
```

**After**:
```json
{
  "lines": [
    "When Trump imposed tariffs in 2018, prices rose 12%.",
    "Historical data shows tariffs increase consumer costs."
  ]
}
```

---

### ✅ Fix #3: Context Enforcement

**Files Changed**: `heretix/provider/grok_xai.py`

**What Changed**:
- Rewrote `_CONTEXT_REQUIREMENTS` with explicit examples
- Increased default min words: 9 → 15
- Increased default min items: 3 → 4
- Increased max attempts: 2 → 3
- Added "BAD vs GOOD" examples in prompt

**New Prompt Excerpt**:
```
CRITICAL: Your reasoning must be CONCRETE and ACCESSIBLE to a general audience.

For EVERY reasoning bullet, you MUST:
1. Name specific actors, companies, dates, or examples
2. Use plain language—explain as if to someone with no technical background
3. Make each bullet a full 15-20 word sentence explaining WHY this fact shifts the probability
4. Avoid abstract statements like 'historical patterns suggest'
5. Instead say 'When X happened in YYYY, it resulted in Z, which suggests...'

BAD: 'Tariffs typically increase costs.'
GOOD: 'When Trump imposed steel tariffs in 2018, washing machine prices rose 12% within six months, documented by BLS.'
```

---

### ✅ Fix #4: Non-Technical Schema

**Files Changed**: `heretix/provider/grok_xai.py`

**What Changed**:
- Enhanced JSON schema instructions with tone requirements
- Explicitly requests "plain, conversational language"
- Forbids jargon and abbreviations
- Requires 15-20 words per bullet with specific examples

**New Schema Excerpt**:
```
Return ONLY JSON matching this schema. WRITE IN PLAIN, CONVERSATIONAL LANGUAGE—
pretend you're explaining to a friend who knows nothing about the topic:

TONE REQUIREMENTS:
- Use simple words (not 'utilizing', say 'using')
- Explain abbreviations ('EV' → 'electric vehicle')
- Give specific examples with numbers and dates
- Write like explaining to a curious non-expert
```

---

### ✅ Fix #5: Local/Production Parity

**Files Changed**: `ui/serve.py`

**What Changed**:
- Replaced subprocess execution with direct pipeline call
- Uses same code path as production API (heretix.pipeline)
- Environment variable: `HERETIX_UI_DIRECT_PIPELINE=1` (default)
- Fallback to subprocess still available if needed

**Before** (subprocess):
```python
subprocess.run([
    "uv", "run", "heretix", "run",
    "--config", cfg_path, "--out", out_path
], env=env)
```

**After** (direct):
```python
from heretix.pipeline import perform_run
from heretix.config import RunConfig

artifacts = perform_run(
    session=session,
    cfg=cfg,
    mode=mode_flag,
    options=options,
    use_mock=False,
)
```

**Benefits**:
- Exact same code as production
- Faster (no subprocess overhead)
- Easier debugging
- Guaranteed consistency

---

### ✅ Fix #6: Quality Gates

**Files Changed**: `heretix/simple_expl.py`

**What Changed**:
- Added `_validate_explanation_quality()` function
- Checks: min 2 lines, 10+ words each, 12+ avg words, no jargon
- Applied to both `compose_simple_expl()` and `compose_baseline_simple_expl()`
- Falls back to generic explanations if quality check fails

**Validation Rules**:
```python
def _validate_explanation_quality(lines: List[str], min_avg_words: int = 12) -> bool:
    # At least 2 lines
    # Each line ≥ 10 words
    # Average ≥ 12 words
    # No jargon: "econometric", "exogenous", "error", "exception", etc.
```

**Flow**:
1. Generate explanation lines
2. Validate quality
3. If fail → use generic fallback
4. If pass → return to user

---

## Configuration Changes

### Environment Variables Added

```bash
# .env (update your local file)
HERETIX_GROK_MODEL=grok-4-0709
HERETIX_GROK_REQUIRE_CONTEXT=1
HERETIX_GROK_CONTEXT_MIN_ITEMS=4
HERETIX_GROK_CONTEXT_MIN_WORDS=15
HERETIX_GROK_MAX_ATTEMPTS=3
HERETIX_UI_DIRECT_PIPELINE=1

# Optional debugging
# HERETIX_GROK_DEBUG_DIR=runs/grok_debug
```

---

## Testing

### Quick Smoke Test

```bash
# 1. Verify model access
uv run python scripts/test_grok_models.py

# 2. Run a claim with Grok
cat > runs/test_grok.yaml << 'EOF'
claim: "Tariffs always raise prices"
model: grok-4-0709
K: 4
R: 2
EOF

uv run heretix run --config runs/test_grok.yaml --out runs/test.json

# 3. Check explanation quality
cat runs/test.json | jq '.runs[0].simple_expl.lines[]'
```

### Expected Output

Each line should:
- Be 15-20 words
- Name specific actors/dates/examples
- Use plain language
- Explain WHY facts matter

**Good Example**:
```
"When Trump imposed 25% steel tariffs in March 2018, washing machine prices jumped 12% within six months according to Bureau of Labor Statistics data."
```

---

## Deployment Checklist

### Local Testing
- [x] Run diagnostic script
- [x] Test baseline mode
- [x] Test web-informed mode
- [x] Verify local UI matches CLI output

### Production Deployment (Render)
- [ ] Add environment variables to Render dashboard
- [ ] Deploy API: `git push origin main`
- [ ] Verify deployment logs
- [ ] Test production endpoint

### Production Deployment (Vercel)
- [ ] Deploy UI: `cd ui && vercel --prod`
- [ ] Test live site at heretix.ai
- [ ] Submit test claim with Grok

---

## Rollback Plan

If issues occur in production:

1. **Disable Grok temporarily**:
   ```bash
   # In Render dashboard
   HERETIX_ENABLE_GROK=0
   ```

2. **Revert to subprocess mode** (if direct pipeline causes issues):
   ```bash
   HERETIX_UI_DIRECT_PIPELINE=0
   ```

3. **Relax context requirements** (if too strict):
   ```bash
   HERETIX_GROK_CONTEXT_MIN_WORDS=10
   HERETIX_GROK_MAX_ATTEMPTS=2
   ```

4. **Full rollback**:
   ```bash
   git revert HEAD
   git push origin main
   ```

---

## Metrics to Monitor

### Success Indicators
- ✅ Compliance rate ≥ 98%
- ✅ Stability score ≥ 0.70
- ✅ No error messages in explanations
- ✅ Average explanation line length ≥ 15 words
- ✅ Local UI output == CLI output

### Warning Signs
- ⚠️ Compliance drops below 95%
- ⚠️ Explanations contain "error", "failed", "invalid"
- ⚠️ Generic fallbacks used > 20% of the time
- ⚠️ xAI rate limit errors (increase RPS)

---

## Files Changed Summary

### New Files
- `scripts/test_grok_models.py` - Model accessibility diagnostic
- `TESTING_GROK_FIXES.md` - Comprehensive testing guide
- `GROK_FIXES_SUMMARY.md` - This file

### Modified Files
- `heretix/provider/grok_xai.py` - Context enforcement, schema tone
- `heretix/simple_expl.py` - Error sanitization, quality gates
- `ui/serve.py` - Direct pipeline integration
- `.env.example` - Updated Grok configuration

### Lines Changed
- Added: ~400 lines
- Modified: ~200 lines
- Deleted: ~50 lines

---

## Next Steps

1. **Run full integration test**:
   ```bash
   bash TESTING_GROK_FIXES.md  # Follow test workflow
   ```

2. **Deploy to staging** (if available):
   - Test with real API keys
   - Submit 5-10 diverse claims
   - Verify explanation quality

3. **Deploy to production**:
   - Update Render environment variables
   - Push to main branch
   - Monitor logs for 24 hours

4. **User feedback**:
   - Collect examples of good/bad explanations
   - Tune `CONTEXT_MIN_WORDS` if needed
   - Adjust quality gate thresholds

---

## Contact & Support

**Documentation**:
- Testing Guide: `TESTING_GROK_FIXES.md`
- Grok Integration: `documentation/grok-integration.md`
- Stats Spec: `documentation/STATS_SPEC.md`

**Troubleshooting**:
- Check `runs/grok_debug/` for detailed transcripts
- Review Render logs for API errors
- Run diagnostic: `uv run python scripts/test_grok_models.py`

**If Issues Persist**:
1. Enable debug mode: `HERETIX_GROK_DEBUG_DIR=runs/grok_debug`
2. Run claim again
3. Share debug JSON files
4. Open GitHub issue with example

---

## Success Metrics (Post-Deployment)

After 1 week in production, verify:
- [ ] 95%+ of Grok explanations are concrete and specific
- [ ] Zero error messages leaked to users
- [ ] Local/production outputs are consistent
- [ ] User satisfaction with explanations (if tracked)
- [ ] No increase in API errors or rate limits

**Goal**: Grok explanations should be indistinguishable in quality from GPT-5 explanations for non-technical users.
