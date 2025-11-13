#!/bin/bash

SESSION_PREFIX="test_worker"

# A simple "Hello World" prompt for the agents
# We ask them to check the mail server just to prove connection works.
CMD="codex --sandbox danger-full-access --ask-for-approval never 'Hello! Please identify yourself as \$AGENT_NAME. Then use the mail tool to check your inbox. If it works, just output \"SYSTEM ONLINE\".'"

echo "🧪 Initializing Test Swarm..."

for i in {1..8}
do
    SESSION_NAME="${SESSION_PREFIX}_${i}"

    # Check if session exists
    tmux has-session -t $SESSION_NAME 2>/dev/null

    if [ $? != 0 ]; then
        # 1. Create the session (starts with a normal shell)
        tmux new-session -d -s $SESSION_NAME

        # 2. Set Agent Identity
        tmux send-keys -t $SESSION_NAME "export AGENT_NAME=Worker-${i}" C-m
        
        # 3. Run the Codex command
        tmux send-keys -t $SESSION_NAME "$CMD" C-m
        
        echo "🤖 Test Agent $i launched"
        
        # Short sleep to pace the API calls
        sleep 3
    else
        echo "⚠️  $SESSION_NAME already active"
    fi
done

echo "--- Test Complete ---"
echo "1. Run 'tmux ls' to see them."
echo "2. Run 'tmux attach -t test_worker_1' to check the output."