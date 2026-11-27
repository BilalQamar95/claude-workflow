#!/bin/sh
# Entry point for the staff plugin's hooks. Exits at once, before Python starts, unless a staff
# task is active somewhere on this machine; the gate then decides per worktree.
# Usage: guard.sh pre-tool | post-tool   (hook payload on stdin)
for m in "${STAFF_STATE_DIR:-$HOME/.local/share/staff}/gate/active/"*; do
  [ -e "$m" ] || continue
  command -v uv >/dev/null 2>&1 || { echo "staff gate hook: uv is not on PATH, so the staff task's checks can't run; install uv or ask the user to end the task." >&2; exit 2; }
  exec uv run --quiet --script "$(dirname "$0")/../scripts/staff_gate.py" hook "$1"
done
exit 0
