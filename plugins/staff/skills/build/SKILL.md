---
name: build
description: Route a task to the trivial, standard or critical workflow by risk, then run that workflow.
argument-hint: "<task description>"
disable-model-invocation: true
---

Task: $ARGUMENTS

## How to run a step

- `staff:<name>`: Read `${CLAUDE_PLUGIN_ROOT}/skills/<name>/SKILL.md` and follow it. Don't use the Skill tool here: it blocks staff skills that set `disable-model-invocation`.
- `/code-review <level>`: the bundled Claude Code review, not `staff:code-review`. Call the Skill tool with `code-review`, args `<level>` (plus a target if the step gives one). `/security-review`: Skill tool, `security-review`. Wait for each result before fixing.
- `/codex:adversarial-review`: user-only. Ask the user to run `/codex:adversarial-review --base <default branch>` and to tell you when its findings are in.
- When a step asks for a review fixed point, use the default branch (usually `main`).
- PR title and body: a plain, client-facing description of the change (what, why, how tested). Leave this workflow out of PRs: no tier, hunk list, metrics, labels or skill names.

## 1. Classify the tier

List the paths the task will likely touch. Match them against the `## Critical paths` globs in the project `CLAUDE.md`.

- Any match: **critical**.
- `trivial`: one file, no behaviour change, no critical path.
- Otherwise: **standard**.
- No `## Critical paths` section: say so, and use **standard** unless the task is trivial.

You may raise the tier. Never lower it. Print one line: the tier and why (name matched paths). Then start.

## 2. Bugs

If the task is a bug, run `staff:systematic-debugging` first. The regression test must fail before the fix. Then continue with the tier below.

## 3. Tier steps

Standard and critical need an issue tracker: an `## Agent skills` section in `CLAUDE.md`/`AGENTS.md`, or `docs/agents/issue-tracker.md`. If neither exists, stop and tell the user to run `/staff:setup-matt-pocock-skills` (pick local markdown unless they want GitHub), then rerun `/staff:build`.

Standard and critical work on a branch. If on the default branch, create one first.

### trivial

1. Implement.
2. Run the project test command (from `CLAUDE.md`; ask if none).
3. `/code-review low` with no target (it covers uncommitted changes, also on the default branch). Fix real findings.

### standard

1. `staff:to-spec`
2. `staff:implement`
3. `staff:verification-before-completion`
4. Push and open a PR with `gh pr create`.

### critical

1. `staff:grill-me`
2. `staff:to-spec`
3. `staff:to-tickets`
4. `staff:implement-spec`
5. `/code-review high` with target `<default branch>...HEAD`, `/security-review` and `/codex:adversarial-review`. Fix real findings.
6. Push and open a PR with `gh pr create`.
7. Print a **Read these hunks** list in the terminal: every hunk of `git diff <default branch>...HEAD` in a critical path, as `path:start-end` and one line on why it matters. If the user wants it kept, save it under `~/.local/share/staff/`, never in the repo or PR.

## 4. End

State the tier used and the PR link (if any). Tell the user to run `/staff:log merge --pr <n> --tier <tier>` after merge.
