#!/bin/bash

# --- CONFIGURATION ---
# Hardcoded path to your plan
PLAN_FILE="/Users/michael/Heretix/multi-ai-plan.md"

# --- CHECKS ---
if [ ! -f "$PLAN_FILE" ]; then
    echo "❌ Error: Plan file not found at $PLAN_FILE"
    exit 1
fi

echo "🚀 Reading plan from: $PLAN_FILE"
PLAN_CONTENT=$(cat "$PLAN_FILE")

# --- THE PROMPT ---
# We inject the file content directly into the instructions for Codex
PROMPT="I have a project plan. I need you to populate my 'beads' task database based on it.

PLAN CONTENT:
\"\"\"
$PLAN_CONTENT
\"\"\"

INSTRUCTIONS:
1. Write and execute a Python script immediately.
2. The script must parse the plan content above.
3. For every '## Header', run: subprocess.run(['bd', 'create', 'Header Name'], capture_output=True, text=True) and capture the ID from stdout.
4. For every bullet point under a header, run: subprocess.run(['bd', 'create', 'Task Name', '--parent', 'PARENT_ID'])
5. Handle any parsing errors gracefully.

GO."

# --- EXECUTE (YOLO MODE) ---
echo "🤖 Instructing Codex to ingest tasks..."
codex --sandbox danger-full-access --ask-for-approval never "$PROMPT"

echo "✅ Ingestion sequence finished."
echo "Run 'bd list' to verify tasks."