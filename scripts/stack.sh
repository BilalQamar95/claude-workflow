#!/bin/zsh
# Per-repo stack skills: detects a repo's dependencies, offers the matching rows of stacks/manifest.tsv one by one,
# and installs the accepted ones at local scope. Every path it writes is git-excluded first; it never commits.
# It also offers the Bash sandbox (default yes). Without a terminal it installs nothing, leaves the sandbox alone and
# only writes the excludes.
# Usage: scripts/stack.sh [--dry-run] <repo-path>
#        scripts/stack.sh --self-test
set -euo pipefail

MANIFEST=${0:A:h:h}/stacks/manifest.tsv
SKILLS_CLI=skills@1.9.0
# Everything the installers below write inside the client repo, then the workflow files /staff:build writes
# (it checks these with git check-ignore and stops if one is missing; keep the two lists in sync).
EXCLUDES=(.claude/settings.local.json .claude/skills/ .agents/skills/ skills-lock.json
  .scratch/ docs/agents/ CLAUDE.local.md GLOSSARY.md GLOSSARY-MAP.md docs/adr/ 'CLAUDE-SECURITY-*/' .staff-gate.toml)

# Prints "file: <name>" for each dependency file in repo $1, then the file contents, all lowercased.
haystack() {
  local f
  # shortcut: reads the repo root and one directory down only; widen the glob if a monorepo keeps its deps deeper.
  for f in $1/{,*/}{pyproject.toml,requirements*.txt,package.json,compose*.y*ml,docker-compose*.y*ml,Dockerfile}(N.); do
    print -r -- "file: ${f:t}"
    grep -v '^[[:space:]]*#' -- $f || true  # comment lines would match as dependencies
  done | tr '[:upper:]' '[:lower:]'
}

# Prints the manifest ids whose detect pattern matches haystack $1, in manifest order.
# shortcut: plain substring regex, so a name in a description or config also matches; the y/N prompt is the filter.
matches() {
  local id detect rest
  while IFS=$'\t' read -r id detect rest; do
    [[ -z $id || $id == \#* ]] && continue
    if grep -qiE -- $detect <<<$1; then print -r -- $id; fi
  done <$MANIFEST
}

# Appends each missing EXCLUDES line to exclude file $1 (newline guard + grep -qxF).
add_excludes() {
  local p
  mkdir -p ${1:h}
  [[ -z $(tail -c1 $1 2>/dev/null) ]] || print >>$1
  for p in $EXCLUDES; do grep -sqxF -- $p $1 || print -r -- $p >>$1; done
}

# Asks prompt $1 with default $2 (y or n). Without a terminal the answer is no: nothing installs unattended.
ask() {
  local ans= hint=y/N
  [[ $2 == y ]] && hint=Y/n
  [[ -t 0 ]] || return 1
  read -r "ans?$1 [$hint] " || ans=
  [[ ${ans:-$2} == [yY]* ]]
}

# Sets enabledPlugins[$2] = true in repo $1's .claude/settings.local.json, unless already set.
enable_local() {
  local f=${1:A}/.claude/settings.local.json t
  f=${f:A}  # a symlinked file is updated where it points, not replaced
  mkdir -p ${f:h}
  [[ -s $f ]] || print '{}' >$f
  jq -e --arg p $2 '.enabledPlugins[$p] == true' $f >/dev/null && return 0
  t=$(mktemp $f.XXXXXX) || return 1
  { jq --arg p $2 '.enabledPlugins[$p] = true' $f >$t && mv $t $f; } || { rm -f -- $t; return 1; }
}

# Sandbox for Bash in settings file $1: on, writes also to the staff state dir and uv's cache (uv won't run without a
# writable cache), and Python package indexes and GitHub pre-allowed; other hosts prompt. Existing entries are kept.
# autoAllowBashIfSandboxed is pinned to false unless already set: before Claude Code 2.1.324 it defaulted to true,
# which would run every sandboxed command without a prompt. The gate hooks use their own uv cache (guard.sh), so
# code written into this one doesn't run outside the sandbox.
SANDBOX_WRITE=(${STAFF_STATE_DIR:-$HOME/.local/share/staff} ${$(uv cache dir 2>/dev/null):-$HOME/.cache/uv})
SANDBOX_DOMAINS=(pypi.org files.pythonhosted.org github.com api.github.com)
sandbox_local() {
  local f=${1:A} t
  mkdir -p ${f:h}
  [[ -s $f ]] || print '{}' >$f
  t=$(mktemp $f.XXXXXX) || return 1
  { jq --argjson w "$(jq -nc '$ARGS.positional' --args $SANDBOX_WRITE)" \
       --argjson d "$(jq -nc '$ARGS.positional' --args $SANDBOX_DOMAINS)" '
      .sandbox.enabled = true
      | .sandbox.filesystem.allowWrite = ((.sandbox.filesystem.allowWrite // []) as $o | $o + ($w - $o))
      | .sandbox.network.allowedDomains = ((.sandbox.network.allowedDomains // []) as $o | $o + ($d - $o))
      | .sandbox.autoAllowBashIfSandboxed //= false' $f >$t &&
    mv $t $f; } || { rm -f -- $t; return 1; }
}

# Installs one manifest row into repo $1. Called only in an `||` list (errexit off), so each step chains with &&.
install_row() {
  local repo=$1 kind=$2 src=$3 items=$4 s
  local -a args
  case $kind in
    skills)
      for s in ${(s:,:)items}; do
        # A skill the repo already tracks would be overwritten in place and show up as a diff.
        if [[ -n $(git -C $repo ls-files -- .claude/skills/$s .agents/skills/$s) ]]; then
          print -u2 "skipping: $s is tracked in this repo"; continue
        fi
        args+=(--skill $s)
      done
      (( $#args )) || return 0
      command -v npx >/dev/null || { print -u2 "missing: npx (Node 22.20+)"; return 1; }
      (cd $repo && DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 npx -y $SKILLS_CLI add $src $args -a claude-code -y) ;;
    plugin)
      jq -e --arg p $items '.enabledPlugins[$p] == true' $repo/.claude/settings.local.json >/dev/null 2>&1 && return 0
      if ! (cd $repo && claude plugin marketplace list --json) | jq -e --arg m ${items#*@} 'any(.[]; .name == $m)' >/dev/null; then
        (cd $repo && claude plugin marketplace add --scope local $src) || return 1
      fi
      (cd $repo && claude plugin install $items --scope local) ;;
    synced)
      enable_local $repo $items ;;
    library-skills)
      command -v uvx >/dev/null || { print -u2 "missing: uvx"; return 1; }
      (cd $repo && DO_NOT_TRACK=1 uvx $src --claude) ;;
    *) print -u2 "unknown kind: $kind"; return 1 ;;
  esac
}

self_test() {
  local fails=0 got t
  eq() { [[ $1 == $2 ]] || { print -u2 "FAIL $3: got [$1] want [$2]"; (( ++fails )); }; }
  got=(${(f)"$(matches $'file: pyproject.toml\n"django>=5", "djangorestframework", "celery[redis]", "psycopg[binary]", "pgvector",\n"pydantic-ai-slim", "langgraph", "langfuse", "deepeval"\nfile: docker-compose.yml\nimage: redis:7')"})
  eq "$got" "pydantic pydantic-ai langchain langfuse docker redis django django-review postgres deepeval" agencyos-like
  got=(${(f)"$(matches $'file: requirements.txt\nfastapi==0.115\nqdrant-client\nneo4j\npydantic-settings')"})
  eq "$got" "pydantic qdrant neo4j fastapi" fastapi-graph
  got=(${(f)"$(matches 'file: package.json')"}); eq "$got" "" filename-only
  got=(${(f)"$(matches 'file: compose.yaml')"}); eq "$got" docker compose-v2-name
  got=(${(f)"$(matches 'file: dockerfile')"}); eq "$got" docker dockerfile
  got=(${(f)"$(matches 'pydantic_ai')"}); eq "$got" "pydantic pydantic-ai" underscore-name
  # No terminal means no, even for a default-y row.
  ask 'x?' y </dev/null && eq yes no ask-no-tty
  # Every row has 7 fields, a pinned source for its kind, and a y/n default.
  # A 40-hex commit pattern spelled out: Debian's default awk (mawk) has no {n} repeat counts.
  got=$(awk -F'\t' -v sha="$(printf '[0-9a-f]%.0s' {1..40})" '!/^#/ && NF && !(NF == 7 && $6 ~ /^[yn]$/ &&
    (($3 == "skills" && $4 ~ ("^[^/@]+/[^/@]+@" sha "$")) || ($3 == "plugin" && $4 ~ ("^[^/#]+/[^/#]+#" sha "$")) ||
     ($3 == "synced" && $4 == "-" && $5 ~ /@synced$/) || ($3 == "library-skills" && $4 ~ /@[0-9.]+$/))) { print $1 }' $MANIFEST)
  eq "$got" "" manifest-pins
  # Excludes: newline guard on a file without a trailing newline, then idempotent.
  t=$(mktemp)
  printf 'keep' >$t
  add_excludes $t; add_excludes $t
  eq "$(<$t)" "keep"$'\n'"${(pj:\n:)EXCLUDES}" excludes
  rm -f -- $t
  # Sandbox: keeps other keys and existing entries, then idempotent.
  t=$(mktemp)
  print '{"enabledPlugins":{"x@y":true},"sandbox":{"filesystem":{"allowWrite":["/keep"]}}}' >$t
  sandbox_local $t; sandbox_local $t
  eq "$(jq -c . $t)" "$(jq -nc --args '{enabledPlugins:{"x@y":true},sandbox:{filesystem:{allowWrite:(["/keep"] + $ARGS.positional[:2])},
    enabled:true,network:{allowedDomains:$ARGS.positional[2:]},autoAllowBashIfSandboxed:false}}' $SANDBOX_WRITE $SANDBOX_DOMAINS)" sandbox
  rm -f -- $t
  # An explicit autoAllowBashIfSandboxed is kept, and a symlinked file is written where it points.
  t=$(mktemp -d)
  print '{"sandbox":{"autoAllowBashIfSandboxed":true}}' >$t/real.json
  ln -s $t/real.json $t/link.json
  sandbox_local $t/link.json
  eq "$([[ -L $t/link.json ]] && jq -c .sandbox.autoAllowBashIfSandboxed $t/real.json)" true sandbox-explicit-and-symlink
  rm -f -- $t/real.json $t/link.json && rmdir -- $t
  (( fails == 0 )) && print "self-test: ok" || { print -u2 "self-test: $fails failed"; return 1; }
}

dry=0
case ${1:-} in
  --self-test) self_test; exit ;;
  --dry-run) dry=1; shift ;;
esac
(( $# == 1 )) || { print -u2 "usage: stack.sh [--dry-run] <repo-path> | --self-test"; exit 2; }
repo=$(git -C $1 rev-parse --show-toplevel) || { print -u2 "not a git repo: $1"; exit 1; }
for c in jq claude; do command -v $c >/dev/null || { print -u2 "missing prerequisite: $c"; exit 1; }; done

ids=(${(f)"$(matches "$(haystack $repo)")"})

if (( ! dry )); then
  # Written first, even with no stack match or a refusal below: /staff:build needs the workflow-file lines and can't
  # write the common git dir itself. A line for a tracked file has no effect on it.
  add_excludes "$(git -C $repo rev-parse --path-format=absolute --git-common-dir)/info/exclude"
  print "excludes: ok"
  for p in .claude/settings.local.json skills-lock.json; do
    [[ -z $(git -C $repo ls-files -- $p) ]] || { print -u2 "$p is tracked in $repo; refusing to install stack skills"; exit 1; }
  done
  print "sandbox: Bash may write only the directory Claude Code starts in, temp, $SANDBOX_WRITE; network to $SANDBOX_DOMAINS pre-allowed, other hosts prompt"
  if ask "turn on the Bash sandbox for this repo?" y; then
    sandbox_local $repo/.claude/settings.local.json && print "sandbox: on" || { print -u2 "sandbox: failed"; exit 1; }
    mkdir -p -- $SANDBOX_WRITE  # on Linux an allowWrite entry for a missing path has no effect
    main=${$(git -C $repo rev-parse --path-format=absolute --git-common-dir):h}
    if [[ ${main:A} != ${repo:A} ]] && jq -e '.sandbox | has("enabled")' $main/.claude/settings.local.json >/dev/null 2>&1; then
      print -u2 "sandbox: $main/.claude/settings.local.json also sets sandbox.enabled; in this worktree Claude Code uses that value"
    fi
    [[ $(uname) != Linux ]] || command -v bwrap socat >/dev/null ||
      print -u2 "sandbox: needs bubblewrap and socat on Linux, or Claude Code runs commands unsandboxed"
  else
    print "sandbox: unchanged"
  fi
else
  print "sandbox: would offer to turn it on (default yes)"
fi
(( $#ids )) || { print "no stack matches in $repo"; exit 0; }

installed=() skipped=() failed=()
# The manifest is read on fd 3 so prompts and installers keep the terminal on stdin.
while IFS=$'\t' read -r -u 3 id detect kind src items def notes; do
  (( ${ids[(Ie)$id]} )) || continue
  if (( dry )); then
    print -r -- "$id [$kind, default $def] $src ${items/#-/}"$'\n'"    $notes"
    continue
  fi
  print -r -- "$id: $notes"
  if ! ask "install $id ($kind)?" $def; then skipped+=($id); continue; fi
  if install_row $repo $kind $src $items; then installed+=($id); else failed+=($id); fi
done 3<$MANIFEST
(( dry )) && { print "dry run: nothing written"; exit 0; }

print "installed: ${installed:-none}"
print "skipped: ${skipped:-none}"
(( $#failed )) && print -u2 "failed: $failed"
# Nothing workflow-internal may reach the client repo: the written paths must stay invisible to git.
leak=$(git -C $repo status --porcelain --untracked-files=all -- .claude .agents skills-lock.json)
[[ -z $leak ]] || print -u2 "warning: git sees stack files; check $repo/.git/info/exclude:"$'\n'"$leak"
(( ! $#failed ))
