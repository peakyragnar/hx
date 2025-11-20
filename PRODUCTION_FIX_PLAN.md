# Production Fix Plan - Simple View Not Working

> 2025 update: The UI now ships from a Render Static Site (`heretix-ui.onrender.com` with `heretix.ai`/`www.heretix.ai`). Use Render to redeploy the frontend; Vercel notes below are legacy for historical context.

## Problem Summary

**Local (Working):**
- Shows clean Simple View with 4 bullet points from backend `heretix/simple_expl.py`
- Example: "Musk announced formation of the 'America Party' on his X platform."

**Production (Broken):**
- Shows OLD fallback format with meta-information
- Example: "Web evidence across 32 documents from 29 domains moved GPT-5's prior..."
- This is the **client-side SPA fallback**, NOT the backend composer

## Root Cause

Production Render deployment does NOT have the updated code from PR #50.
The backend is not returning `simple_expl` in the API response, so the frontend falls back to the old client-side composer in `ui/index.html`.

## Verification (What We Checked)

✅ `heretix/simple_expl.py` - Exists locally, has composer with stateful `grab()` function
✅ `heretix/pipeline.py:361` - Calls `compose_simple_expl()` and includes in `PipelineArtifacts`
✅ `heretix/cli.py:191` - Includes `simple_expl` in run output
✅ `api/main.py:314` - Returns `simple_expl` from `artifacts.simple_expl`
✅ `api/schemas.py:145` - Schema has `simple_expl: Optional[Dict[str, object]]`
✅ `ui/index.html:756` - Checks for and renders backend `simple_expl`
✅ `ui/serve.py:1026` - Local server checks for and uses `simple_expl`

**Conclusion:** All code is correct. Production just needs to redeploy.

---

## Fix Steps (Execute in Order)

### Step 1: Verify GitHub Has Latest Code

```bash
# Check local matches remote
git status
# Should show: "Your branch is up to date with 'origin/main'"

# Verify latest commit
git log --oneline -3
# Should show:
# c6f3917 Move DEPLOYMENT_STEPS.md to documentation folder
# 6bcd08d Reorganize docs and add deployment guides
# 3bbf9dd Merge pull request #50 from peakyragnar/clarify-output
```

### Step 2: Force Redeploy Backend (Render) - WITH CACHE CLEAR

This is the critical step that was likely missed.

**Via Render Dashboard:**
1. Go to https://dashboard.render.com
2. Find your backend service (e.g., "heretix-api" or similar name)
3. Click **"Settings"** tab
4. Scroll to **"Build & Deploy"** section
5. Click **"Clear build cache & deploy"** button (NOT just "Deploy")
6. Wait for build to complete (~3-5 minutes)
7. Check logs for errors

**Why cache clear is essential:**
- Render may have cached the Docker image WITHOUT `heretix/simple_expl.py`
- `COPY . .` in Dockerfile needs to pick up new files
- Cache clear forces a complete rebuild from scratch

### Step 3: Verify Backend Deployment

```bash
# Health check
curl https://api.heretix.ai/healthz
# Expected: {"status":"ok"}

# Check if simple_expl module is imported (indirect test)
# Submit a test claim via API and check response
curl -X POST https://api.heretix.ai/api/run \
  -H "Content-Type: application/json" \
  -H "Cookie: heretix_anon=test_token" \
  -d '{
    "claim": "Test claim",
    "mode": "web_informed",
    "K": 8,
    "R": 2,
    "T": 8
  }' \
  | jq '.simple_expl'

# Expected: {"title": "Why...", "lines": [...], "summary": "..."}
# If null or missing: Backend still doesn't have the code
```

### Step 4: Force Redeploy Frontend (Vercel, legacy) - NO CACHE

> Current prod uses a Render Static Site (`heretix-ui.onrender.com`). If you're on that stack, redeploy the Render static site with cache clear; the Vercel steps below are kept only for historical parity.

Even though the UI code should work, let's ensure Vercel has the latest too (legacy path).

**Via Vercel Dashboard:**
1. Go to https://vercel.com/dashboard
2. Find project "hx"
3. Go to **Deployments** tab
4. Find latest deployment
5. Click **three dots (...)** → **"Redeploy"**
6. **UNCHECK** "Use existing build cache"
7. Click **"Redeploy"**
8. Wait ~1-2 minutes

**Via Vercel CLI (Alternative):**
```bash
cd ui/
vercel --prod --force
```

### Step 5: Clear Browser Cache & Test

Production often caches aggressively. After both deployments:

1. **Hard refresh** in browser:
   - Mac: Cmd+Shift+R
   - Windows: Ctrl+F5
   - Or open Incognito/Private window

2. Go to production URL (e.g., https://heretix.ai)

3. Submit test claim: "Elon musk will create his own political party"

4. **Wait for results** (~30-60 seconds)

5. **Check Simple View section:**
   - Should show 2-4 bullet points with specific evidence
   - Should NOT show meta-information like "Web evidence across 32 documents..."
   - Summary should be last: "Taken together, these points suggest the claim is..."

### Step 6: If Still Not Working - Nuclear Option

If Steps 1-5 don't work, force a new commit to trigger auto-deploy:

```bash
# Make a trivial change to force rebuild
echo "# Force rebuild $(date)" >> .deployment-trigger
git add .deployment-trigger
git commit -m "Force production rebuild - trigger Render/Vercel"
git push origin main
```

Both Render services should auto-deploy on push to `main`. Wait 5 minutes and test again.

---

## Troubleshooting

### Issue: Backend health check fails
**Solution:** Check Render logs for errors. Ensure environment variables are set:
- `OPENAI_API_KEY`
- `DATABASE_URL` or `DATABASE_URL_PROD`
- `TAVILY_API_KEY`

### Issue: Backend returns null for simple_expl
**Possible causes:**
1. `heretix/simple_expl.py` not included in Docker build
2. Import error in `heretix/pipeline.py`
3. Exception in `compose_simple_expl()` (caught and set to None)

**Debug:**
- Check Render logs for Python import errors
- Look for "simple_expl" or "compose_simple_expl" in logs
- Check if exception is logged around pipeline.py:359-369

### Issue: Frontend still shows old format
**Possible causes:**
1. Browser cache (hard refresh needed)
2. Vercel didn't deploy (check Vercel dashboard deployments)
3. Backend not returning `simple_expl` (see above)

**Debug:**
- Open browser DevTools → Network tab
- Submit claim and check the API response
- Look for `simple_expl` field in the JSON response
- If missing: backend issue
- If present but not rendered: frontend issue (unlikely)

---

## Success Criteria

✅ Backend health check passes
✅ Backend API response includes `simple_expl` field with `title`, `lines`, `summary`
✅ Frontend loads without console errors
✅ Test claim shows 2-4 specific evidence bullets (NOT meta-information)
✅ Summary appears at the end
✅ No domain/brand prefixes (sanitization working)
✅ Percentages match local behavior (within stochastic variance)

---

## Verification Checklist

- [ ] Step 1: GitHub has latest code (commit c6f3917 or later)
- [ ] Step 2: Render redeployed WITH cache clear
- [ ] Step 3: Backend health check passes
- [ ] Step 3: Backend API returns `simple_expl` (test with curl)
- [ ] Step 4: Vercel redeployed without cache
- [ ] Step 5: Browser cache cleared (hard refresh)
- [ ] Step 5: Test claim shows correct Simple View format
- [ ] SUCCESS: Production matches local output

---

## Rollback Plan (If Needed)

If deployment causes critical issues:

```bash
# Revert to commit before PR #50
git revert 3bbf9dd -m 1
git push origin main
# Wait for auto-deploy (both Render and Vercel)
```

This will restore the old behavior (fallback composer only).

---

## Key Files Changed in PR #50

- `heretix/simple_expl.py` - NEW: Backend composer with stateful grab()
- `heretix/tests/test_simple_expl.py` - NEW: 27 comprehensive tests
- `heretix/pipeline.py` - MODIFIED: Integration (line 361)
- `heretix/cli.py` - MODIFIED: Output serialization (line 191)
- `api/main.py` - MODIFIED: API response (line 314)
- `api/schemas.py` - MODIFIED: Schema (line 145)
- `ui/index.html` - MODIFIED: Frontend rendering (line 756)
- `documentation/optimize-simplify-output.md` - NEW: Design guide

---

## Notes

- Render Web Service deploys entire repo → includes `heretix/` backend code
- Render Static Site (current) or Vercel (legacy) deploys only `ui/` directory → static frontend files
- Both services must be updated for Simple View to work end-to-end
- Cache clearing is CRITICAL - standard redeploy may not pick up new files
- Local `ui/serve.py` works because it directly imports from `heretix/` module
- Production API is separate service, must be redeployed independently

---

## Contact Points

If issues persist after following this plan:
1. Check Render logs: https://dashboard.render.com → service → Logs tab
2. Check Vercel logs: https://vercel.com/dashboard → project → Deployments → click deployment → View Logs
3. Check GitHub Actions: https://github.com/peakyragnar/hx/actions (CI tests)
