#!/bin/sh
# Entry point for the staff plugin's hooks. Exits at once, before Python starts, unless a staff
# task is active somewhere on this machine; the gate then decides per worktree. For stop, a lock
# record without a packet also counts, so deleting the marker doesn't end a task.
# Usage: guard.sh pre-tool | post-tool | stop   (hook payload on stdin)
S="${STAFF_STATE_DIR:-$HOME/.local/share/staff}/gate"
gate() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "staff gate hook: uv is not on PATH, so the staff task's checks can't run; install uv or ask the user to end the task." >&2
    # A Stop already sent back once may end, as the gate itself allows; otherwise every stop would loop.
    [ "$1" = stop ] && grep -q '"stop_hook_active" *: *true' && exit 0
    exit 2
  fi
  # Hooks run outside the Bash sandbox, which may write uv's usual cache; their own cache keeps code planted
  # there from running here. It must never be in sandbox.filesystem.allowWrite.
  export UV_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/staff-hook-uv"
  exec uv run --quiet --script "$(dirname "$0")/../scripts/staff_gate.py" hook "$1"
}
for m in "$S/active/"*; do
  [ -e "$m" ] && gate "$1"
done
if [ "$1" = stop ]; then
  for c in "$S"/repos/*/*/contract.json; do
    [ -e "$c" ] && [ ! -f "${c%/contract.json}/packet.md" ] && gate stop
  done
fi
exit 0
