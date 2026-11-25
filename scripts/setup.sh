#!/bin/zsh
# Idempotent machine setup for the staff workflow. Safe to re-run.
# Edits ~/.claude/settings.json only through jq, after a timestamped backup.
set -euo pipefail

REPO_ROOT=${0:A:h:h}
SETTINGS=$HOME/.claude/settings.json
CM_TELEMETRY=$HOME/.claude-mem/telemetry.json
changed=()

# 1. Prerequisites.
for c in jq claude uv brew; do
  command -v $c >/dev/null || { print -u2 "missing prerequisite: $c"; exit 1; }
done
if ! command -v gh >/dev/null; then
  brew install gh
  changed+=("installed gh")
  print "run: gh auth login"
fi
command -v pyright-langserver >/dev/null || print "note: pyright-lsp needs pyright-langserver on PATH (e.g. uv tool install pyright)"
[[ -f $SETTINGS ]] || { print -u2 "missing $SETTINGS"; exit 1; }

# 2. Backup (every run, so each run is recoverable).
backup="$SETTINGS.bak.$(date +%Y%m%d-%H%M%S)"
cp -p $SETTINGS $backup

# 3. Settings merge. Skip the write when values already match, so re-runs leave the file byte-identical.
if ! jq -e '.autoUpdatesChannel == "stable" and .env.CAVEMAN_DEFAULT_MODE == "lite"' $SETTINGS >/dev/null; then
  tmp=$(mktemp "$SETTINGS.XXXXXX")
  jq '.autoUpdatesChannel = "stable" | .env.CAVEMAN_DEFAULT_MODE = "lite"' $SETTINGS >$tmp
  mv $tmp $SETTINGS
  changed+=("settings.json: autoUpdatesChannel, env.CAVEMAN_DEFAULT_MODE")
fi

# 4. Local marketplace (name comes from .claude-plugin/marketplace.json).
if ! claude plugin marketplace list --json | jq -e 'any(.[]; .name == "claude-workflow")' >/dev/null; then
  claude plugin marketplace add "$REPO_ROOT"
  changed+=("marketplace added: claude-workflow")
fi

# Prints "missing", "true" or "false" for a plugin id.
plugin_state() {
  claude plugin list --json | jq -r --arg id $1 'first(.[] | select(.id == $id) | .enabled | tostring) // "missing"'
}

# 5. Install and enable.
for p in pyright-lsp@claude-plugins-official pr-review-toolkit@claude-plugins-official staff@claude-workflow; do
  case $(plugin_state $p) in
    missing) claude plugin install $p; changed+=("installed $p") ;;
    false) claude plugin enable $p; changed+=("enabled $p") ;;
  esac
done

# 6. Disable. Keys resolved from enabledPlugins on 2026-11-25.
for p in superpowers@claude-plugins-official impeccable@impeccable playwright@claude-plugins-official frontend-design@claude-plugins-official; do
  if [[ $(plugin_state $p) == true ]]; then
    claude plugin disable $p
    changed+=("disabled $p")
  fi
done

# 7. claude-mem (16.1.5).
# Telemetry: hook-service.cjs:27 Yk() reads ~/.claude-mem/telemetry.json and treats `enabled: false`
# as declined (env CLAUDE_MEM_TELEMETRY / DO_NOT_TRACK also work but only for processes that inherit them).
# vr() ignores the file unless installId is a string, so a missing file gets one.
if [[ ! -f $CM_TELEMETRY ]] || ! jq -e '.enabled == false' $CM_TELEMETRY >/dev/null; then
  mkdir -p ${CM_TELEMETRY:h}
  [[ -f $CM_TELEMETRY ]] || print '{}' >$CM_TELEMETRY
  tmp=$(mktemp "$CM_TELEMETRY.XXXXXX")
  jq --arg id "$(uuidgen | tr 'A-Z' 'a-z')" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '.installId = (.installId // $id) | .enabled = false | .decidedAt = $now' $CM_TELEMETRY >$tmp
  mv $tmp $CM_TELEMETRY
  changed+=("claude-mem telemetry: declined")
fi
# Startup injection: NOT set here, pending a decision.
# CLAUDE_MEM_EXCLUDED_PROJECTS (comma list of globs matched against cwd path and basename) is the only
# per-project switch, but it also stops capture: hook-service.cjs:190 we() gates SessionStart (:212),
# PostToolUse observations (:286), Stop summaries (:293) and file edits (:304).
# The CLAUDE_MEM_CONTEXT_* keys (:67) are global, not per project.

# 8. Third-party marketplace pinning: recorded in VENDORED.md ("Machine plugins"), not done here.

# 9. Summary (names only; never values from settings.json).
print "backup: $backup"
if (( ${#changed} )); then
  print "changed:"; printf '  %s\n' "${changed[@]}"
else
  print "no changes"
fi
