#!/bin/bash

SESSION="HeretixSwarm"
PROTOCOL_FILE="AGENTS.md"
PLAN_FILE="multi-ai-plan.md"

# --- CONFIGURATION ---
# We inject the text from your image as the core instruction.
# We swapped the filename to 'multi-ai-plan.md' to match your actual file.

INSTRUCTIONS="You are \$AGENT_NAME.

Phase 1: Boot & Handshake
Before doing anything else, read ALL of $PROTOCOL_FILE; then register with agent mail (ensure_project -> register_agent) and introduce yourself to the other agents.

Phase 2: Planning & Coordination
Coordinate on the remaining tasks left in $PLAN_FILE with the other agents. Come up with a game plan for splitting and reviewing the work. Use 'bd' (Beads) for task management and issue tracking.

Phase 3: Execution & Communication
Check your agent mail and promptly respond if needed. Proceed meticulously with the plan, doing all your remaining unfinished tasks systematically.
- Notate your progress in-line in the plan document ($PLAN_FILE).
- Send agent mail messages to update others.
- Don't get stuck in \"communication purgatory\" where nothing gets done.
- Be proactive about starting tasks.

Phase 4: Review & Deep Dive
Review the code written by your fellow agents. Check for issues, bugs, errors, inefficiencies, security problems, and reliability issues.
- Diagnose root causes using first-principle analysis.
- Fix or revise them if necessary.
- Don't restrict yourself to the latest commits; cast a wider net and go super deep!

Phase 5: Verification
Check what is left in $PLAN_FILE that hasn't been fully implemented.
- Add end-to-end implementation tests with extremely detailed logging (using the rich library's formatting) to explain inputs, functions called, and results.
- Communicate findings via agent mail and by adding sections to the plan document.

KEEP GOING."

# --- LAUNCH COMMAND ---
# We write the instructions to a file inside the session to handle the complex text safely
CMD="codex --model gpt-5-codex --sandbox danger-full-access --ask-for-approval never \"$INSTRUCTIONS\""

echo "🔥 Launching Ultimate Swarm (GPT-5 + Image Instructions)..."

# 1. Create Session + Worker 1
tmux new-session -d -s $SESSION -n "Worker-1"

# 2. Create Workers 2-8
for i in {2..8}; do
    tmux new-window -t $SESSION -n "Worker-${i}"
done

# 3. Wake them up
for i in {1..8}; do
    TARGET="$SESSION:Worker-${i}"
    
    # Identify
    tmux send-keys -t "$TARGET" "export AGENT_NAME=Worker-${i}" C-m
    
    # We use a temp script approach to ensure the long multi-line prompt is passed correctly
    # 1. Create temp file with the prompt
    tmux send-keys -t "$TARGET" "cat <<EOF > /tmp/agent_prompt_${i}.txt
$INSTRUCTIONS
EOF" C-m
    
    # 2. Run Codex using that file content
    tmux send-keys -t "$TARGET" "codex --model gpt-5-codex --sandbox danger-full-access --ask-for-approval never \"\$(cat /tmp/agent_prompt_${i}.txt)\"" C-m
    
    echo "✅ Agent $i initialized with Master Instructions"
    sleep 3
done

# 4. Attach
tmux attach -t $SESSION