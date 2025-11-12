#!/usr/bin/env python3
"""Quick diagnostic to test which Grok models are accessible via your xAI API key."""

import os
import sys
from openai import OpenAI

def test_model_access():
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    if not api_key:
        print("❌ ERROR: XAI_API_KEY or GROK_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")

    # Test each model variant
    models_to_test = [
        "grok-4-0709",
        "grok-4-fast-non-reasoning",
        "grok-4-fast-reasoning",
        "grok-beta",
        "grok-2-latest",
    ]

    print("Testing Grok model accessibility...\n")
    working_models = []

    for model in models_to_test:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
                temperature=0,
            )
            actual_model = getattr(resp, "model", model)
            print(f"✅ {model:35s} → {actual_model}")
            working_models.append((model, actual_model))
        except Exception as e:
            error_msg = str(e)
            if "model_not_found" in error_msg.lower():
                print(f"❌ {model:35s} → NOT ACCESSIBLE (model_not_found)")
            elif "does not exist" in error_msg.lower():
                print(f"❌ {model:35s} → DOES NOT EXIST")
            else:
                print(f"❌ {model:35s} → ERROR: {error_msg[:60]}")

    print(f"\n{'='*70}")
    if working_models:
        print(f"✅ Found {len(working_models)} working model(s):")
        for name, actual in working_models:
            print(f"   - {name} → {actual}")

        # Recommend which to use
        preferred = working_models[0][0]
        print(f"\n💡 RECOMMENDATION: Update .env with:")
        print(f"   HERETIX_GROK_MODEL={preferred}")
    else:
        print("❌ NO WORKING MODELS FOUND")
        print("\nTroubleshooting:")
        print("1. Verify your API key is correct")
        print("2. Check xAI Console: https://console.x.ai/")
        print("3. Request model access from support@x.ai")
        print("4. Try grok-beta if you have beta access")

    return len(working_models) > 0

if __name__ == "__main__":
    success = test_model_access()
    sys.exit(0 if success else 1)
