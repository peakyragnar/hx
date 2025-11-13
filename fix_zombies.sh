#!/bin/bash

echo "🧟 Hunting for zombie tasks (stuck in 'in_progress')..."

# 1. Find all tasks with 'in_progress' status
# We grab the first word (The ID) from lines containing "in_progress"
ZOMBIES=$(bd list | grep "in_progress" | awk '{print $1}')

if [ -z "$ZOMBIES" ]; then
    echo "✅ No zombies found. Your database is clean."
    exit 0
fi

# 2. Show them to the user
echo "⚠️  Found these stuck tasks:"
echo "$ZOMBIES"
echo "--------------------------------"

# 3. Loop through and reset each one
for ID in $ZOMBIES; do
    echo "💉 Curing $ID (Resetting to 'open')..."
    bd update "$ID" --status open
done

echo "---"
echo "✅ All tasks reset. You can safely launch the swarm now."