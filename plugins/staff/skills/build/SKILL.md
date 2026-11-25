---
name: build
description: Route a task to the trivial, standard or critical workflow by risk, then run that workflow.
argument-hint: "<task description>"
disable-model-invocation: true
---

Task: $ARGUMENTS

## How to run a step

- `staff:<name>`: read `${CLAUDE_PLUGIN_ROOT}/skills/<name>/SKILL.md` and follow it. The same applies when a skill you are following names another staff skill (e.g. implement → tdd, code-review; implement-spec → implement), even if it says to call the Skill tool: the Skill tool blocks staff skills that set `disable-model-invocation`, and reading the file always works. When you brief a subagent to run a staff skill, give it that file path.
- `/code-review <level>`: the bundled Claude Code review, not `staff:code-review`. Call the Skill tool with `code-review`, args `<level>` (plus a target if the step gives one). `/security-review`: Skill tool, `security-review`. Wait for each result before fixing.
- `/codex:adversarial-review`: user-only. Ask the user to run `/codex:adversarial-review --base <default branch>` and to tell you when its findings are in.
- When a step asks for a review fixed point, use the default branch (usually `main`).
- PR rule: every PR title and body is a plain, client-facing description of the change (what, why, how tested). Leave this workflow out: no tier, hunk list, metrics, labels or skill names. This covers every PR, including the draft PR `staff:implement-spec` opens and any PR another followed skill creates.
- Project config: `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md` and `docs/agents/issue-tracker.md`, whichever exist. Read critical paths and the tracker config from them.
- Client repos get no workflow files. The local-markdown tracker writes `.scratch/` (specs, tickets) and `docs/agents/` (tracker docs), and the tracker config goes in `CLAUDE.local.md`. Never `git add` these paths: commits contain only product code and tests.

## 1. Classify the tier

List the paths the task will likely touch. Match them against the `## Critical paths` globs in the project config.

- Any match: **critical**.
- `trivial`: one file, no behaviour change, no critical path.
- Otherwise: **standard**.
- No `## Critical paths` section: say so, and use **standard** unless the task is trivial.

You may raise the tier. Never lower it. Print one line: the tier and why (name matched paths). Then start.

## 2. Bugs

If the task is a bug, run `staff:systematic-debugging` first. The regression test must fail before the fix. Then continue with the tier below.

## 3. Tier steps

Standard and critical write workflow files, so first make sure git ignores them locally. Append any missing line to the repo's exclude file (never edit its `.gitignore`):

```bash
ex="$(git rev-parse --git-common-dir)/info/exclude"; mkdir -p "$(dirname "$ex")"
for p in .scratch/ docs/agents/ CLAUDE.local.md; do grep -qxF "$p" "$ex" || echo "$p" >> "$ex"; done
```

They also need an issue tracker: an `## Agent skills` section in the project config, or `docs/agents/issue-tracker.md`. If neither exists, stop and tell the user to run `/staff:setup-matt-pocock-skills`, pick local markdown, and have it put the `## Agent skills` section in `CLAUDE.local.md` (not the committed `CLAUDE.md`). Then rerun `/staff:build`.

Standard and critical work on a branch. If on the default branch, create one first.

### trivial

1. Implement.
2. Run the project test command (from the project config; ask if none).
3. `/code-review low` with no target (it covers uncommitted changes, also on the default branch). Fix real findings.

### standard

1. `staff:to-spec`
2. `staff:implement`
3. `staff:verification-before-completion`
4. Push and open a PR with `gh pr create` (PR rule above).

### critical

1. `staff:grill-me`
2. `staff:to-spec`
3. `staff:to-tickets`
4. `staff:implement-spec`
5. `/code-review high` with target `<default branch>...HEAD`, `/security-review` and `/codex:adversarial-review`. Fix real findings.
6. Push and open a PR with `gh pr create` (PR rule above).
7. Print a **Read these hunks** list in the terminal: every hunk of `git diff <default branch>...HEAD` in a critical path, as `path:start-end` and one line on why it matters. If the user wants it kept, save it under `~/.local/share/staff/`, never in the repo or PR.

## 4. End

State the tier used and the PR link (if any). Tell the user to run `/staff:log merge --pr <n> --tier <tier>` after merge.
