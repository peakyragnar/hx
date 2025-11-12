# Testing Guide: Grok Explanation Fixes

This guide walks through testing all the fixes implemented to resolve Grok explanation issues.

## Prerequisites

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Set environment variables**:
   ```bash
   export XAI_API_KEY="xai-..."  # Your xAI API key
   export OPENAI_API_KEY="sk-..."  # For GPT-5 comparison
   export HERETIX_ENABLE_GROK=1
   export HERETIX_UI_DIRECT_PIPELINE=1
   ```

3. **Verify dependencies**:
   ```bash
   cd /Users/michael/Heretix
   uv sync
   ```

---

## Fix #1: Verify Grok Model Accessibility

**What it fixes**: Model name mismatches causing `model_not_found` errors

### Test Steps

1. **Run diagnostic script**:
   ```bash
   uv run python scripts/test_grok_models.py
   ```

2. **Expected output**:
   ```
   Testing Grok model accessibility...

   ✅ grok-4-0709                        → grok-4-0709
   ✅ grok-4-fast-non-reasoning          → grok-4-fast-non-reasoning
   ...
   ```

3. **If a model fails**, update your `.env`:
   ```bash
   # Use the working model name
   echo "HERETIX_GROK_MODEL=grok-4-0709" >> .env
   ```

---

## Fix #2: Error Sanitization

**What it fixes**: Provider errors leaking into user-facing explanations

### Test Steps

1. **Create a test claim**:
   ```bash
   cat > runs/test_grok_error.yaml << 'EOF'
   claim: "Tariffs always raise prices"
   model: grok-invalid-model-name
   prompt_version: rpl_g5_v5
   K: 4
   R: 2
   EOF
   ```

2. **Run with invalid model** (should fail gracefully):
   ```bash
   uv run heretix run --config runs/test_grok_error.yaml --out runs/test_error.json
   ```

3. **Check output**:
   ```bash
   cat runs/test_error.json | jq '.runs[0].simple_expl.lines[]'
   ```

4. **Expected**: No lines containing "error", "model_not_found", or JSON error objects

---

## Fix #3 & #4: Context Enforcement + Non-Technical Tone

**What it fixes**: Generic/technical explanations from Grok

### Test Steps

1. **Run Grok with a simple claim**:
   ```bash
   cat > runs/test_grok_context.yaml << 'EOF'
   claim: "Tariffs always raise prices"
   model: grok-4-0709
   prompt_version: rpl_g5_v5
   K: 4
   R: 2
   EOF

   uv run heretix run --config runs/test_grok_context.yaml --out runs/grok_context.json
   ```

2. **Inspect reasoning bullets**:
   ```bash
   cat runs/grok_context.json | jq '.runs[0].paraphrase_results[0].raw.reasoning_bullets[]'
   ```

3. **Expected qualities**:
   - ✅ Each bullet is 15-20 words
   - ✅ Names specific actors, dates, or examples
   - ✅ Uses plain language (not "utilizing", "exogenous", etc.)
   - ✅ Explains WHY facts matter

4. **BAD example** (old behavior):
   ```
   "Tariffs typically increase import costs for domestic consumers and businesses."
   ```

5. **GOOD example** (new behavior):
   ```
   "When Trump imposed steel tariffs in 2018, washing machine prices rose 12% within six months according to Bureau of Labor Statistics data."
   ```

---

## Fix #5: Local/Production Parity

**What it fixes**: Different outputs between `ui/serve.py` and production API

### Test Steps

1. **Start local UI server**:
   ```bash
   uv run python ui/serve.py
   ```

2. **Visit http://localhost:7799** and submit a claim with Grok selected

3. **Check local output**:
   ```bash
   # Find latest UI output
   latest=$(ls -t runs/ui_tmp/out_*.json | head -1)
   cat "$latest" | jq '.runs[0].simple_expl'
   ```

4. **Compare with direct CLI run**:
   ```bash
   cat > runs/test_parity.yaml << 'EOF'
   claim: "Tariffs always raise prices"
   model: grok-4-0709
   K: 8
   R: 2
   EOF

   uv run heretix run --config runs/test_parity.yaml --out runs/parity.json
   cat runs/parity.json | jq '.runs[0].simple_expl'
   ```

5. **Expected**: Both outputs should have identical structure and similar content

---

## Fix #6: Quality Gates

**What it fixes**: Low-quality explanations passing through to users

### Test Steps

1. **Force a low-quality response** (mock test):
   ```python
   # In Python REPL
   from heretix.simple_expl import _validate_explanation_quality

   # Too short
   assert not _validate_explanation_quality(["Short.", "Too brief."])

   # Contains errors
   assert not _validate_explanation_quality([
       "This is a long sentence with error text.",
       "Another sentence with failed context."
   ])

   # Good quality
   assert _validate_explanation_quality([
       "When Trump imposed steel tariffs in 2018, washing machine prices increased.",
       "Historical precedent shows import duties raise consumer costs significantly.",
       "Multiple economists documented these effects in peer-reviewed studies."
   ])
   ```

2. **Run full pipeline and verify fallback**:
   ```bash
   uv run heretix run --config runs/test_grok_context.yaml --out runs/quality_test.json
   cat runs/quality_test.json | jq '.runs[0].simple_expl.lines | length'
   # Should always output 3 lines (quality gate enforces this)
   ```

---

## Integration Test: Full Workflow

**End-to-end test of all fixes together**

### Test Workflow

```bash
# 1. Clean start
rm -rf runs/ui_tmp/*
rm -f runs/integration_test.json

# 2. Configure environment
export HERETIX_GROK_MODEL=grok-4-0709
export HERETIX_GROK_DEBUG_DIR=runs/grok_debug
export HERETIX_GROK_MAX_ATTEMPTS=3

# 3. Run baseline (prior only)
cat > runs/integration_test.yaml << 'EOF'
claim: "Tariffs always raise prices"
model: grok-4-0709
prompt_version: rpl_g5_v5
K: 8
R: 2
T: 8
B: 5000
EOF

uv run heretix run \
  --config runs/integration_test.yaml \
  --out runs/integration_test.json \
  --mode baseline

# 4. Validate output
python3 << 'VALIDATE'
import json
from pathlib import Path

# Load result
result = json.loads(Path("runs/integration_test.json").read_text())
run = result["runs"][0]

# Check simple explanation
simple = run.get("simple_expl", {})
lines = simple.get("lines", [])

print(f"✓ Got {len(lines)} explanation lines")

for i, line in enumerate(lines, 1):
    word_count = len(line.split())
    print(f"  Line {i}: {word_count} words")
    assert word_count >= 10, f"Line {i} too short: {word_count} words"
    assert "error" not in line.lower(), f"Line {i} contains 'error'"
    assert "model_not_found" not in line.lower(), f"Line {i} contains error message"

print("✓ All quality checks passed")

# Check aggregates
agg = run["aggregates"]
print(f"✓ prob_true_rpl: {agg['prob_true_rpl']:.2%}")
print(f"✓ stability_score: {agg['stability_score']:.3f}")
print(f"✓ rpl_compliance_rate: {agg['rpl_compliance_rate']:.2%}")

assert agg["rpl_compliance_rate"] >= 0.98, "Compliance too low"
print("✓ All metrics passed")
VALIDATE

# 5. Check debug transcripts (if enabled)
if [ -d runs/grok_debug ]; then
    echo "Debug transcripts written to runs/grok_debug/"
    ls -lh runs/grok_debug/ | tail -5
fi
```

### Expected Output

```
✓ Got 3 explanation lines
  Line 1: 18 words
  Line 2: 22 words
  Line 3: 19 words
✓ All quality checks passed
✓ prob_true_rpl: 67.00%
✓ stability_score: 0.842
✓ rpl_compliance_rate: 100.00%
✓ All metrics passed
```

---

## Production Deployment Checklist

Before deploying to Render/Vercel:

### 1. Environment Variables (Render API)

```bash
# Add to Render dashboard:
XAI_API_KEY=xai-...
HERETIX_GROK_MODEL=grok-4-0709
HERETIX_GROK_REQUIRE_CONTEXT=1
HERETIX_GROK_CONTEXT_MIN_ITEMS=4
HERETIX_GROK_CONTEXT_MIN_WORDS=15
HERETIX_GROK_MAX_ATTEMPTS=3
HERETIX_XAI_RPS=1
HERETIX_XAI_BURST=2
HERETIX_ENABLE_GROK=1
```

### 2. Deploy API

```bash
git add -A
git commit -m "Fix Grok explanations - concrete context + quality gates"
git push origin main
# Render will auto-deploy
```

### 3. Deploy UI (Vercel)

```bash
cd ui
vercel --prod
```

### 4. Post-Deployment Verification

```bash
# Test production API
curl -X POST https://api.heretix.ai/api/checks/run \
  -H "Content-Type: application/json" \
  -d '{
    "claim": "Tariffs always raise prices",
    "model": "grok-4-0709",
    "mode": "baseline"
  }' | jq '.simple_expl'

# Expected: 3 concrete, non-technical explanation lines
```

### 5. Monitor for Issues

- Check Render logs for any new errors
- Verify Grok API usage in xAI console
- Test claims from different domains (economics, tech, sports)

---

## Troubleshooting

### Issue: "model_not_found"

**Solution**: Update `HERETIX_GROK_MODEL` to a working model:
```bash
uv run python scripts/test_grok_models.py
# Use the first ✅ model name
export HERETIX_GROK_MODEL=grok-4-0709
```

### Issue: Explanations still generic

**Solution**: Increase context requirements:
```bash
export HERETIX_GROK_CONTEXT_MIN_WORDS=20
export HERETIX_GROK_MAX_ATTEMPTS=4
```

### Issue: Rate limit errors

**Solution**: Reduce request rate:
```bash
export HERETIX_XAI_RPS=0.5
export HERETIX_XAI_BURST=1
```

### Issue: Local vs production outputs differ

**Solution**: Ensure `HERETIX_UI_DIRECT_PIPELINE=1`:
```bash
grep HERETIX_UI_DIRECT_PIPELINE .env || echo "HERETIX_UI_DIRECT_PIPELINE=1" >> .env
```

---

## Success Criteria

All fixes are working when:

- ✅ No error messages in user-facing explanations
- ✅ Each explanation line is 15+ words with specific examples
- ✅ No technical jargon (econometric, exogenous, etc.)
- ✅ Local UI matches CLI output structure
- ✅ Compliance rate ≥ 98%
- ✅ Stability score ≥ 0.70 for most claims
- ✅ Quality gates prevent low-quality outputs

---

## Contact

If issues persist:
1. Check `runs/grok_debug/` for detailed transcripts
2. Review Render logs for API errors
3. Open GitHub issue with example claim and output
