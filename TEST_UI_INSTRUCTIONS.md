# Quick UI Testing Instructions

## ✅ Fixed: Import Error Resolved

The `get_session_local` import error has been fixed. The UI now creates its own database session.

---

## 🚀 Start the UI Server

```bash
cd /Users/michael/Heretix
uv run python ui/serve.py
```

**Expected output**:
```
[ui] Serving HTTP on 0.0.0.0 port 7799 (http://0.0.0.0:7799/) ...
```

**If you see errors**, stop with `Ctrl+C` and check the error message.

---

## 🌐 Open the UI

1. **Open browser**: http://localhost:7799

2. **You should see**:
   - Heretix homepage
   - Text area for claim input
   - Model dropdown (should show "GPT-5" and "Grok 4 (xAI)" if HERETIX_ENABLE_GROK=1)
   - Mode selector (Prior / Internet Search)

---

## 🧪 Test Grok Explanation Quality

### Test 1: Basic Grok Test

1. **Select Model**: "Grok 4 (xAI)"
2. **Select Mode**: "Internal Knowledge Only (no retrieval)"
3. **Enter Claim**:
   ```
   Tariffs always raise prices
   ```
4. **Click**: "Check this claim" (or Submit)
5. **Wait**: ~30-60 seconds

### Expected Good Output:

```
🔹 Why the model-only verdict looks this way

• When Trump imposed 25% steel tariffs in March 2018, washing machine
  prices jumped 12% within six months according to Bureau of Labor
  Statistics data, showing direct passthrough to consumers.

• Historical precedent from the 1930 Smoot-Hawley Tariff Act shows
  import duties raised consumer prices by 10% across affected goods,
  documented in Federal Reserve records from that era.

• Multiple economists documented these effects in peer-reviewed studies
  across different economies and time periods, establishing a robust
  pattern of tariff-induced price increases.

Taken together, these points suggest the claim is likely true.
```

**✅ Quality Checklist**:
- [ ] Each line is 15-20+ words
- [ ] Names specific actors/dates (Trump, 2018, 12%, Smoot-Hawley, etc.)
- [ ] Uses plain language (no "exogenous", "econometric", etc.)
- [ ] No error messages visible ("error", "failed", "model_not_found")
- [ ] Shows percentage probability (e.g., 67%)

---

### Test 2: Compare GPT-5 vs Grok

1. **Run SAME claim with GPT-5**
2. **Compare outputs**:
   - Both should have 3 concrete lines
   - Both should cite specific examples
   - Quality should be comparable

---

### Test 3: Web-Informed Mode

1. **Select Mode**: "Internet Search"
2. **Submit** same claim
3. **Verify**:
   - Takes ~60-120 seconds (web fetching)
   - Shows web sources in "Deeper explanation"
   - Simple View still has 3+ concrete lines

---

## 🔍 Debugging Failed Outputs

### If you see generic explanations:

```bash
# Enable debug mode
echo "HERETIX_GROK_DEBUG_DIR=runs/grok_debug" >> .env

# Restart server
# Ctrl+C to stop, then:
uv run python ui/serve.py

# After running a claim, check debug files:
ls -lh runs/grok_debug/
cat runs/grok_debug/grok_*.json | jq '.attempts[].parsed.reasoning_bullets[]'
```

### If you see error messages in output:

```bash
# Find the output file
latest=$(ls -t runs/ui_tmp/out_*.json | head -1)

# Check for errors
cat "$latest" | jq '.runs[0].simple_expl.lines[]' | grep -i "error\|invalid\|failed"

# View raw Grok response
cat "$latest" | jq '.runs[0].paraphrase_results[0].raw'
```

### If server crashes:

```bash
# Check logs (look at terminal output)
# Common issues:
# 1. Port already in use → kill -9 $(lsof -ti:7799)
# 2. Database locked → rm runs/heretix_ui.sqlite
# 3. Missing dependencies → uv sync
```

---

## 📊 Success Criteria

✅ **PASS** if:
- Server starts without errors
- Grok option appears in dropdown
- Explanations are concrete and specific
- No error messages visible to user
- Each line has 15+ words with examples
- Probability and stability scores display

❌ **FAIL** if:
- Error messages appear in Simple View
- Lines are generic ("Tariffs typically increase costs")
- Technical jargon present ("econometric", "exogenous")
- Less than 3 lines in explanation
- Server crashes or hangs

---

## 🎯 Quick Test Claims

Try these across different domains:

1. **"Tariffs always raise prices"** (Economics - likely true)
2. **"The Great Wall of China is visible from space"** (Geography - likely false)
3. **"Nuclear power is safer than coal"** (Energy - likely true)
4. **"Bitcoin will reach $1 million by 2030"** (Finance - uncertain)
5. **"Vaccines cause autism"** (Health - likely false)

Each should produce 3 concrete, citation-rich lines.

---

## 🚨 Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| **Import error** | Already fixed! Just restart server |
| **Grok not in dropdown** | Check `.env` has `HERETIX_ENABLE_GROK=1` |
| **Generic explanations** | Enable `HERETIX_GROK_DEBUG_DIR`, check transcripts |
| **Error messages visible** | Bug - share output file with developer |
| **Server won't start** | Check port with `lsof -ti:7799`, kill if needed |
| **Too slow** | Reduce K/R in `runs/rpl_example.yaml` |

---

## 📝 After Testing

### If ALL TESTS PASS:

1. **Test 3-5 more diverse claims**
2. **Compare GPT-5 vs Grok quality**
3. **Ready for production deployment**

### If ISSUES FOUND:

1. **Enable debug mode** (`HERETIX_GROK_DEBUG_DIR`)
2. **Capture screenshots** of bad outputs
3. **Share**:
   - Terminal output
   - Latest `runs/ui_tmp/out_*.json`
   - Any `runs/grok_debug/*.json` files
   - Screenshots of UI

---

## 🎉 Next Steps After Successful Testing

1. **Production Deployment**:
   ```bash
   # Add to Render environment variables
   HERETIX_GROK_MODEL=grok-4-fast-reasoning
   HERETIX_ENABLE_GROK=1
   # (all other Grok settings from .env)

   # Deploy
   git add -A
   git commit -m "Add Grok support with quality explanations"
   git push origin main
   ```

2. **Test Production**:
   - Visit https://heretix.ai
   - Submit test claim with Grok
   - Verify quality matches local

3. **Monitor**:
   - Check Render logs for errors
   - Verify xAI API usage
   - Collect user feedback

---

**Ready to test!** Run `uv run python ui/serve.py` and follow the test steps above. 🚀
