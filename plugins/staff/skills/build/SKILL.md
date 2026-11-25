---
name: build
description: Route a task to the trivial, standard or critical workflow by risk, then run that workflow.
argument-hint: "<task description>"
disable-model-invocation: true
---

Task: $ARGUMENTS

## How to run a step

- `staff:<name>`: call the Skill tool with it. If the tool refuses (`disable-model-invocation`), Read `${CLAUDE_SKILL_DIR}/../<name>/SKILL.md` and follow it.
- `/code-review <level>` and `/security-review`: call the Skill tool (`code-review` with args `<level>`, `security-review`).
- `/codex:adversarial-review`: user-only. Ask the user to run `/codex:adversarial-review --base main`, then wait for its findings.
- Review fixed point is `main` (the merge-base of `HEAD` with it).

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
3. `/code-review low`. Fix real findings.

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
5. `/code-review high`, `/security-review` and `/codex:adversarial-review`. Fix real findings.
6. Push and open a PR with `gh pr create`. The PR body has a **Read these hunks** list: every diff hunk in a critical path, as `path:start-end` and one line on why it matters.

## 4. End

State the tier used and the PR link (if any). Tell the user to run `/staff:log merge --pr <n> --tier <tier>` after merge.
