# Production Deployment Fix - Nov 11, 2024

## Issue
Local changes (Simple View improvements) not appearing in production after standard redeploy.

## Root Cause
Two-part deployment (Backend on Render + Frontend on Vercel) requires both to redeploy.
Vercel may not have auto-deployed the UI changes in `ui/index.html`.

## Fix Steps

### 1. Force Redeploy Backend API (Render) - WITH CACHE CLEAR

Go to Render dashboard:
1. Navigate to https://dashboard.render.com
2. Find your backend service (e.g., "heretix-api")
3. Click **Settings** → Scroll to **Build & Deploy**
4. Click **"Clear build cache & deploy"** (important!)
5. Wait for deploy to complete (~3-5 minutes)
6. Verify: `curl https://api.heretix.ai/healthz` should return `{"status":"ok"}`

**Why cache clear?** Ensures `heretix/simple_expl.py` and all new files are included.

---

### 2. Force Redeploy Frontend (Vercel) - FROM ui/ DIRECTORY

**Option A: Vercel Dashboard (Recommended)**
1. Go to https://vercel.com/dashboard
2. Find your project (should be "hx")
3. Go to **Deployments** tab
4. Click the **three dots (...)** on the latest deployment
5. Select **"Redeploy"** → Check **"Use existing build cache: NO"**
6. Wait for deployment (~1-2 minutes)

**Option B: Vercel CLI (If dashboard doesn't work)**
```bash
# From your project root
cd ui/
vercel --prod --force

# Or deploy with specific scope
vercel --prod --force --scope team_gLiEIcZRGpBnE255gcV91UpS
```

**Why from ui/?** Your Vercel config has `"rootDirectory": "ui"`, so it deploys only that folder.

---

### 3. Verify Deployment Sync

**Backend Check:**
```bash
# Test that backend returns simple_expl in the response
curl -s -X POST https://api.heretix.ai/api/checks/run \
  -H "Content-Type: application/json" \
  -d '{"claim": "Test claim", "mode": "web_informed"}' \
  | jq '.simple_expl'

# Should return an object like: {"title": "Why...", "lines": [...], "summary": "..."}
```

**Frontend Check:**
1. Visit https://heretix.ai (or your production URL)
2. Open browser DevTools → Console
3. Submit a test claim
4. Check the response JSON includes `simple_expl` field
5. Verify the UI renders 2-3 content lines (not just 1)

**Full E2E Test:**
1. Go to https://heretix.ai
2. Submit: "The NFL will ban guardian caps in 2025"
3. Wait for results
4. **Simple View should show:**
   - Line 1: "A ban would require formal approval by the owners at a rules meeting in 2025."
   - Line 2: "Recent reporting points to debate and expectations of a vote, not a finalized decision."
   - Line 3: (possibly) "Earlier proposals were discussed or tabled..."
   - Summary: "Taken together, these points suggest the claim is likely false."

---

### 4. If Still Not Working - Nuclear Option

**Force Push Rebuild:**
```bash
# Make a tiny commit to force rebuild
echo "# Deployment $(date)" >> .deployment-trigger
git add .deployment-trigger
git commit -m "Force production rebuild"
git push origin main
```

Both Render and Vercel should auto-deploy on push to main.

---

### 5. Check Environment Variables (If API errors occur)

**Render Environment:**
- `OPENAI_API_KEY` - should be set
- `DATABASE_URL` or `DATABASE_URL_PROD` - should point to Neon
- `TAVILY_API_KEY` - should be set for WEL

**Vercel Environment (if applicable):**
- `NEXT_PUBLIC_API_URL` - should be `https://api.heretix.ai`

---

## Debugging Commands

```bash
# Check what commit is deployed (backend)
curl https://api.heretix.ai/healthz

# Check frontend is serving updated HTML
curl -s https://heretix.ai/ | grep -o 'simple_expl' | wc -l
# Should return > 0 if updated index.html is deployed

# Check backend can import simple_expl
# (SSH into Render container if possible, or check logs for import errors)
```

---

## Success Criteria

✅ Backend health check passes
✅ Frontend loads without console errors
✅ Test claim shows 2-3 content lines in Simple View
✅ Summary appears at the end
✅ Sanitization removes brands/domains (no "example.com:" prefixes)

---

## Rollback Plan (If needed)

If the deployment causes issues:
```bash
# Revert to previous commit
git log --oneline -5  # Find the commit before merge
git revert 3bbf9dd  # Revert the merge commit
git push origin main  # Trigger redeploy
```

---

## Notes
- Render deploys the entire repo (including `heretix/` backend code)
- Vercel deploys only the `ui/` directory (frontend static files)
- Both need to redeploy for the Simple View feature to work end-to-end
- Browser cache: Users may need to hard refresh (Cmd+Shift+R / Ctrl+F5)
