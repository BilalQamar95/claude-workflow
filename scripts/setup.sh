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
# The installed plugin runs from this checkout, so a feature branch or dirty tree here is live in client sessions.
repo_branch=$(git -C $REPO_ROOT branch --show-current 2>/dev/null || true)
repo_dirty=$(git -C $REPO_ROOT status --porcelain 2>/dev/null || true)
if [[ $repo_branch != main || -n $repo_dirty ]]; then
  print -u2 "warning: staff plugin is registered from $REPO_ROOT on branch ${repo_branch:-detached}${repo_dirty:+ (dirty)}; client sessions will run this checkout"
fi
for c in jq claude uv; do
  command -v $c >/dev/null || { print -u2 "missing prerequisite: $c"; exit 1; }
done
if ! command -v gh >/dev/null; then
  command -v brew >/dev/null || { print -u2 "missing prerequisite: gh (and brew to install it); install gh from https://cli.github.com, then re-run"; exit 1; }
  brew install gh
  changed+=("installed gh")
  print "run: gh auth login"
fi
# pyright-lsp plugin runs pyright-langserver. npm, not brew: brew builds llvm+rust from source on Intel Macs.
if ! command -v pyright-langserver >/dev/null; then
  if command -v npm >/dev/null; then
    npm install -g pyright@1.1.414
    changed+=("installed pyright@1.1.414")
  else
    print -u2 "warning: npm not found; pyright-lsp needs: npm install -g pyright@1.1.414"
  fi
fi
[[ -f $SETTINGS ]] || { print -u2 "missing $SETTINGS"; exit 1; }

# 2. Backup (every run, unique name, so each run is recoverable).
backup $SETTINGS

# 3. Settings merge (update channel, caveman lite, Claude Code telemetry and error reporting off, DO_NOT_TRACK for
# third-party CLIs, claude-security's post-push scan tip off because the build router decides when to scan).
# CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC is deliberately not set: it also turns off auto-updates.
# Skip the write when values already match, so re-runs leave the file byte-identical.
env_ok='.autoUpdatesChannel == "stable" and .env.CAVEMAN_DEFAULT_MODE == "lite" and .env.DISABLE_TELEMETRY == "1" and .env.DISABLE_ERROR_REPORTING == "1" and .env.DO_NOT_TRACK == "1" and .env.CLAUDE_SECURITY_SCAN_TIP == "off"'
if ! jq -e $env_ok $SETTINGS >/dev/null; then
  jq_write $SETTINGS '.autoUpdatesChannel = "stable" | .env.CAVEMAN_DEFAULT_MODE = "lite" | .env.DISABLE_TELEMETRY = "1" | .env.DISABLE_ERROR_REPORTING = "1" | .env.DO_NOT_TRACK = "1" | .env.CLAUDE_SECURITY_SCAN_TIP = "off"'
  changed+=("settings.json: autoUpdatesChannel, env.CAVEMAN_DEFAULT_MODE, env.DISABLE_TELEMETRY, env.DISABLE_ERROR_REPORTING, env.DO_NOT_TRACK, env.CLAUDE_SECURITY_SCAN_TIP")
fi
# Deny reading secret files (a Read deny also blocks Edit and Write on the path). In user settings a relative pattern
# anchors at the session's working directory and `~/` at home. Existing deny entries stay, in order; only missing ones are added.
deny='["Read(**/.env)","Read(**/.env.*)","Read(**/*.pem)","Read(**/*.key)","Read(~/.ssh/**)","Read(~/.aws/**)"]'
if ! jq -e --argjson new $deny '($new - (.permissions.deny // [])) == []' $SETTINGS >/dev/null; then
  jq_write $SETTINGS '.permissions.deny = ((.permissions.deny // []) as $d | $d + ($new - $d))' --argjson new $deny
  changed+=("settings.json: permissions.deny (secret files)")
fi
# Teach mode: STAFF_OUTPUT_STYLE=Explanatory (or Learning, or a custom style name) sets the user default output style.
if [[ -n ${STAFF_OUTPUT_STYLE:-} ]] && ! jq -e --arg s $STAFF_OUTPUT_STYLE '.outputStyle == $s' $SETTINGS >/dev/null; then
  jq_write $SETTINGS '.outputStyle = $s' --arg s $STAFF_OUTPUT_STYLE
  changed+=("settings.json: outputStyle")
fi

# 4. Local marketplace (name comes from .claude-plugin/marketplace.json).
# Captured by assignment so errexit fires if the CLI fails.
marketplaces=$(claude plugin marketplace list --json)
if ! jq -e 'any(.[]; .name == "claude-workflow")' <<<$marketplaces >/dev/null; then
  claude plugin marketplace add "$REPO_ROOT"
  changed+=("marketplace added: claude-workflow")
fi
# Trail of Bits, pinned to a reviewed commit (a full SHA as ref needs Claude Code >= 2.1.324). An existing
# registration is left alone, because re-registering uninstalls its plugins; a different pin is only reported.
TOB_SHA=149d7b21f4067765b82e67029730b42d228ef4b4
if ! jq -e 'any(.[]; .name == "trailofbits")' <<<$marketplaces >/dev/null; then
  claude plugin marketplace add "trailofbits/skills#$TOB_SHA"
  changed+=("marketplace added: trailofbits (pinned)")
elif ! jq -e --arg sha $TOB_SHA '.trailofbits.source.ref == $sha' $HOME/.claude/plugins/known_marketplaces.json >/dev/null; then
  print -u2 "warning: marketplace trailofbits is not pinned to $TOB_SHA; see VENDORED.md"
fi

# Prints "missing", "true" or "false" for plugin id $1 from the captured $plugins list.
plugin_state() {
  jq -r --arg id $1 'first(.[] | select(.id == $id) | .enabled | tostring) // "missing"' <<<$plugins
}

# 5. Install and enable.
plugins=$(claude plugin list --json)
for p in pyright-lsp@claude-plugins-official pr-review-toolkit@claude-plugins-official claude-security@claude-plugins-official \
    sharp-edges@trailofbits supply-chain-risk-auditor@trailofbits insecure-defaults@trailofbits staff@claude-workflow; do
  state=$(plugin_state $p)
  case $state in
    missing) claude plugin install $p; changed+=("installed $p") ;;
    false) claude plugin enable $p; changed+=("enabled $p") ;;
  esac
done

# 6. Disable. Keys resolved from enabledPlugins on 2026-11-25. Stack plugins synced from claude.ai (qdrant, langfuse)
# go off user-wide; scripts/stack.sh turns one back on in a repo that uses it, at local scope.
plugins=$(claude plugin list --json)  # re-read: step 5 may have changed state
for p in superpowers@claude-plugins-official impeccable@impeccable playwright@claude-plugins-official frontend-design@claude-plugins-official \
    qdrant@synced langfuse@synced; do
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

# 8. Third-party marketplace auto-update off wherever settings declare the marketplace (the third-party default is
# already off; this makes it explicit). Pinning the older marketplaces is recorded in VENDORED.md ("Machine plugins").
mk_off='.extraKnownMarketplaces // {} | with_entries(select(.key != "claude-plugins-official")) | all(.[]; .autoUpdate == false)'
if ! jq -e $mk_off $SETTINGS >/dev/null; then
  jq_write $SETTINGS '.extraKnownMarketplaces |= with_entries(if .key == "claude-plugins-official" then . else .value.autoUpdate = false end)'
  changed+=("settings.json: extraKnownMarketplaces.*.autoUpdate")
fi
auto_on=$(jq -r '[to_entries[] | select(.value.autoUpdate == true) | .key] | join(" ")' $HOME/.claude/plugins/known_marketplaces.json 2>/dev/null || true)
print "marketplaces with auto-update on (official ones default to on): ${auto_on:-none}"
# Advisor: report only; advisorModel unset means the advisor is off. Never changed here.
if jq -e '.advisorModel // empty' $SETTINGS >/dev/null; then print "advisor: configured"; else print "advisor: not configured"; fi

# 8b. gitleaks 8.19+ (the router runs `gitleaks git`). Homebrew only when it has a bottle for this macOS, because it
# builds some formulae from source on Intel Macs; otherwise the pinned release tarball, sha256-checked.
GITLEAKS_VERSION=8.30.1
typeset -A GITLEAKS_SHA=(
  x64 dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709
  arm64 b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5
)
# Called only in an `||` list, where errexit is off, so every step checks its own status.
install_gitleaks() {
  if command -v brew >/dev/null && brew ruby -e 'exit(Formula["gitleaks"].bottle ? 0 : 1)' >/dev/null 2>&1; then
    brew install gitleaks || return 1
    changed+=("installed gitleaks (brew bottle)")
    return 0
  fi
  local arch=x64 dir ok=0
  [[ $(uname -m) == arm64 ]] && arch=arm64
  dir=$(mktemp -d) || return 1
  curl -fsSL -o $dir/gl.tgz "https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION/gitleaks_${GITLEAKS_VERSION}_darwin_$arch.tar.gz" \
    && [[ $(shasum -a 256 $dir/gl.tgz | cut -d' ' -f1) == ${GITLEAKS_SHA[$arch]} ]] \
    && tar -xzf $dir/gl.tgz -C $dir gitleaks \
    && mkdir -p $HOME/.local/bin && install -m 755 $dir/gitleaks $HOME/.local/bin/gitleaks \
    && ok=1
  rm -f -- $dir/gl.tgz $dir/gitleaks; rmdir -- $dir
  (( ok )) || return 1
  changed+=("installed gitleaks $GITLEAKS_VERSION to ~/.local/bin")
  [[ :$PATH: == *:$HOME/.local/bin:* ]] || print -u2 "warning: ~/.local/bin is not on PATH; add it so the router finds gitleaks"
}
autoload -Uz is-at-least
if command -v gitleaks >/dev/null; then
  gl_ver=$(gitleaks version 2>/dev/null || true)
  is-at-least 8.19 ${gl_ver#v} || print -u2 "warning: gitleaks ${gl_ver:-unknown} is older than 8.19, which the router's secret scan needs"
else
  install_gitleaks || print -u2 "warning: gitleaks not installed; the router will skip the secret scan"
fi

# 9. Global guidelines: Karpathy CLAUDE.md. Upstream has no licence, so it is fetched, never committed (see VENDORED.md).
KARPATHY_URL=https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/2c606141936f1eeef17fa3043a72095b4765b9c2/CLAUDE.md
KARPATHY_SHA=694a2d721e41c385f3db492838c23299826df5ba9809e3b0721aac70021e196a
GUIDELINES=$HOME/.claude/CLAUDE.md
if [[ ! -e $GUIDELINES ]]; then
  tmp=$(mktemp "$GUIDELINES.XXXXXX")
  if ! curl -fsSL -o $tmp $KARPATHY_URL; then
    rm -f -- "$tmp"; tmp=
    print -u2 "failed to fetch $KARPATHY_URL; nothing written"; exit 1
  fi
  if [[ $(shasum -a 256 $tmp | cut -d' ' -f1) != $KARPATHY_SHA ]]; then
    rm -f -- "$tmp"; tmp=
    print -u2 "sha256 mismatch for $KARPATHY_URL (expected $KARPATHY_SHA); nothing written"; exit 1
  fi
  chmod 644 $tmp && mv $tmp $GUIDELINES || { rm -f -- "$tmp"; tmp=; exit 1; }
  tmp=
  changed+=("installed ~/.claude/CLAUDE.md (pinned Karpathy guidelines)")
elif [[ $(shasum -a 256 $GUIDELINES | cut -d' ' -f1) != $KARPATHY_SHA ]]; then
  print -u2 "warning: ~/.claude/CLAUDE.md differs from pinned Karpathy guidelines; left unchanged"
fi

# 10. Summary (names only; never values from settings files).
if (( ${#changed} )); then
  print "changed:"; printf '  %s\n' "${changed[@]}"
else
  print "no changes"
fi
