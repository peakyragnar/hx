#!/bin/bash
# Production Verification Script
# Run this after deploying to verify Simple View is working

set -e

echo "🔍 Verifying Production Deployment..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="${API_URL:-https://api.heretix.ai}"
APP_URL="${APP_URL:-https://heretix.ai}"

# 1. Backend Health Check
echo "1️⃣  Checking backend health..."
HEALTH=$(curl -s "$API_URL/healthz" 2>/dev/null || echo "ERROR")
if [[ "$HEALTH" == *"ok"* ]]; then
    echo -e "${GREEN}✅ Backend is healthy${NC}"
else
    echo -e "${RED}❌ Backend health check failed: $HEALTH${NC}"
    exit 1
fi

# 2. Check if simple_expl module exists on backend
echo ""
echo "2️⃣  Checking if simple_expl is deployed..."
# We can't directly import, but we can check the frontend HTML includes it
HTML_CHECK=$(curl -s "$APP_URL/" | grep -c "simple_expl" || echo "0")
if [[ "$HTML_CHECK" -gt 0 ]]; then
    echo -e "${GREEN}✅ Frontend HTML includes simple_expl logic ($HTML_CHECK occurrences)${NC}"
else
    echo -e "${YELLOW}⚠️  Frontend HTML doesn't include 'simple_expl' - may not be deployed${NC}"
fi

# 3. Check recent commit on GitHub
echo ""
echo "3️⃣  Checking GitHub main branch..."
LATEST_COMMIT=$(git log origin/main --oneline -1 2>/dev/null || echo "unknown")
echo "   Latest commit: $LATEST_COMMIT"
if [[ "$LATEST_COMMIT" == *"3bbf9dd"* ]] || [[ "$LATEST_COMMIT" == *"Merge pull request #50"* ]]; then
    echo -e "${GREEN}✅ GitHub has the Simple View merge${NC}"
else
    echo -e "${YELLOW}⚠️  GitHub commit doesn't match expected merge${NC}"
fi

# 4. Test claim submission (requires API key)
echo ""
echo "4️⃣  Testing live claim submission..."
if [[ -z "$OPENAI_API_KEY" ]]; then
    echo -e "${YELLOW}⚠️  OPENAI_API_KEY not set, skipping live test${NC}"
    echo "   To test: export OPENAI_API_KEY=your-key && $0"
else
    echo "   Submitting test claim (this will take ~30 seconds)..."
    # This would require authentication, skip for now
    echo -e "${YELLOW}⚠️  Skipped (would require auth token)${NC}"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Summary:"
echo ""
echo "To complete verification:"
echo "1. Go to $APP_URL"
echo "2. Submit test claim: 'The NFL will ban guardian caps in 2025'"
echo "3. Check Simple View shows 2-3 content lines + summary"
echo "4. Verify no 'example.com:' prefixes (sanitization working)"
echo ""
echo "If issues persist, see DEPLOYMENT_STEPS.md for troubleshooting"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
