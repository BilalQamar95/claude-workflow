#!/bin/zsh
# Idempotent machine setup for the staff workflow. Safe to re-run.
# Edits ~/.claude/settings.json and ~/.claude-mem/*.json only through jq, after a backup.
set -euo pipefail

REPO_ROOT=${0:A:h:h}
SETTINGS=$HOME/.claude/settings.json
CM_SETTINGS=$HOME/.claude-mem/settings.json
CM_TELEMETRY=$HOME/.claude-mem/telemetry.json
changed=()
# zsh skips EXIT traps when errexit fires inside a function, so the helpers below also clean up
# explicitly; this trap covers interrupts.
tmp=
trap '[[ -z ${tmp:-} ]] || rm -f -- "$tmp"' EXIT

# Copies $1 to a unique timestamped backup next to it and prints the path.
backup() {
  local b
  b=$(mktemp "$1.bak.$(date +%Y%m%d-%H%M%S).XXXXXX")
  cp -p $1 $b || { rm -f -- "$b"; return 1; }
  print "backup: $b"
}

# Applies jq filter $2 to file $1 via a temp file in the same directory.
jq_write() {
  tmp=$(mktemp "$1.XXXXXX")
  { jq "${@:3}" $2 $1 >$tmp && mv $tmp $1; } || { rm -f -- "$tmp"; tmp=; return 1; }
  tmp=
}

# 1. Prerequisites.
for c in jq claude uv brew; do
  command -v $c >/dev/null || { print -u2 "missing prerequisite: $c"; exit 1; }
done
if ! command -v gh >/dev/null; then
  brew install gh
  changed+=("installed gh")
  print "run: gh auth login"
fi
if ! command -v pyright-langserver >/dev/null; then
  brew install pyright  # pyright-lsp plugin runs pyright-langserver
  changed+=("installed pyright")
fi
[[ -f $SETTINGS ]] || { print -u2 "missing $SETTINGS"; exit 1; }

# 2. Backup (every run, unique name, so each run is recoverable).
backup $SETTINGS

# 3. Settings merge (update channel, caveman lite, Claude Code telemetry off). Skip the write when values already match, so re-runs leave the file byte-identical.
if ! jq -e '.autoUpdatesChannel == "stable" and .env.CAVEMAN_DEFAULT_MODE == "lite" and .env.DISABLE_TELEMETRY == "1"' $SETTINGS >/dev/null; then
  jq_write $SETTINGS '.autoUpdatesChannel = "stable" | .env.CAVEMAN_DEFAULT_MODE = "lite" | .env.DISABLE_TELEMETRY = "1"'
  changed+=("settings.json: autoUpdatesChannel, env.CAVEMAN_DEFAULT_MODE, env.DISABLE_TELEMETRY")
fi

# 4. Local marketplace (name comes from .claude-plugin/marketplace.json).
# Captured by assignment so errexit fires if the CLI fails.
marketplaces=$(claude plugin marketplace list --json)
if ! jq -e 'any(.[]; .name == "claude-workflow")' <<<$marketplaces >/dev/null; then
  claude plugin marketplace add "$REPO_ROOT"
  changed+=("marketplace added: claude-workflow")
fi

# Prints "missing", "true" or "false" for plugin id $1 from the captured $plugins list.
plugin_state() {
  jq -r --arg id $1 'first(.[] | select(.id == $id) | .enabled | tostring) // "missing"' <<<$plugins
}

# 5. Install and enable.
plugins=$(claude plugin list --json)
for p in pyright-lsp@claude-plugins-official pr-review-toolkit@claude-plugins-official staff@claude-workflow; do
  state=$(plugin_state $p)
  case $state in
    missing) claude plugin install $p; changed+=("installed $p") ;;
    false) claude plugin enable $p; changed+=("enabled $p") ;;
  esac
done

# 6. Disable. Keys resolved from enabledPlugins on 2026-11-25.
plugins=$(claude plugin list --json)  # re-read: step 5 may have changed state
for p in superpowers@claude-plugins-official impeccable@impeccable playwright@claude-plugins-official frontend-design@claude-plugins-official; do
  state=$(plugin_state $p)
  if [[ $state == true ]]; then
    claude plugin disable $p
    changed+=("disabled $p")
  fi
done

# 7. claude-mem (16.1.5; line refs are to the bundled scripts/hook-service.cjs).
mkdir -p ${CM_SETTINGS:h}
# Startup injection off globally, capture stays on. Flat string-valued keys (DEFAULTS, :16).
# Counts parse as whole-number strings, "0" allowed (OT/jH, :67); show-last-summary is compared ==="true" (:67).
# CLAUDE_MEM_EXCLUDED_PROJECTS was rejected: its gate we() (:190) also stops capture (:286, :293, :304).
[[ -f $CM_SETTINGS ]] || print '{}' >$CM_SETTINGS
backup $CM_SETTINGS
cm_ctx='.CLAUDE_MEM_CONTEXT_OBSERVATIONS == "0" and .CLAUDE_MEM_CONTEXT_SESSION_COUNT == "0" and .CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY == "false"'
if ! jq -e $cm_ctx $CM_SETTINGS >/dev/null; then
  jq_write $CM_SETTINGS '.CLAUDE_MEM_CONTEXT_OBSERVATIONS = "0" | .CLAUDE_MEM_CONTEXT_SESSION_COUNT = "0" | .CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY = "false"'
  changed+=("claude-mem settings: CLAUDE_MEM_CONTEXT_OBSERVATIONS, CLAUDE_MEM_CONTEXT_SESSION_COUNT, CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY")
fi
# Telemetry: Yk() (:27) reads ~/.claude-mem/telemetry.json and treats `enabled: false` as declined.
# vr() (:27) ignores the file unless installId is a string, so a missing file gets one.
if [[ ! -f $CM_TELEMETRY ]] || ! jq -e '.enabled == false' $CM_TELEMETRY >/dev/null; then
  [[ -f $CM_TELEMETRY ]] || print '{}' >$CM_TELEMETRY
  jq_write $CM_TELEMETRY '.installId = (.installId // $id) | .enabled = false | .decidedAt = $now' \
    --arg id "$(uuidgen | tr 'A-Z' 'a-z')" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  changed+=("claude-mem telemetry: declined")
fi

# 8. Third-party marketplace pinning: recorded in VENDORED.md ("Machine plugins"), not done here.

# 9. Summary (names only; never values from settings files).
if (( ${#changed} )); then
  print "changed:"; printf '  %s\n' "${changed[@]}"
else
  print "no changes"
fi
