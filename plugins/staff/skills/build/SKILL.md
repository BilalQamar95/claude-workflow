---
name: build
description: Route a task to the trivial, standard or critical workflow by risk, then run that workflow.
argument-hint: "<task description>"
disable-model-invocation: true
---

Task: $ARGUMENTS

## How to run a step

- `staff:<name>`: read `${CLAUDE_PLUGIN_ROOT}/skills/<name>/SKILL.md` and follow it. The same applies when a skill you are following names another staff skill (e.g. implement → tdd, code-review; implement-spec → implement), even if it says to call the Skill tool: the Skill tool blocks staff skills that set `disable-model-invocation`, and reading the file always works. When you brief a subagent to run a staff skill, give it that file path, the PR rule and the no-`git add` rule below.
- `/code-review <level>`: the bundled Claude Code review, not `staff:code-review`. Call the Skill tool with `code-review`, args `<level>` (plus a target if the step gives one). `/security-review` runs through a subagent (see `reviews.md`). Other slash steps (`/simplify`, `/claude-security:claude-security`): Skill tool with the name after `/`, args as given. Wait for each result before fixing.
- When a step asks for a review fixed point, use the default branch (usually `main`).
- PR rule: every PR title and body is a plain, client-facing description of the change (what, why, how tested). Leave this workflow out: no tier, hunk list, metrics, labels or skill names. Write PR bodies, commit messages, specs and handoffs in normal prose, never caveman style. This covers every PR, including the draft PR `staff:implement-spec` opens and any PR another followed skill creates.
- Project config: `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md` and `docs/agents/issue-tracker.md`, whichever exist. Read critical paths and the tracker config from them.
- Shell commands that don't trip permission prompts: run from the repo root and use `git -C <dir>` rather than `cd <dir> && git`; no `VAR=x cmd` or `env -u` prefixes; the Grep and Glob tools rather than `find -exec` or `xargs sh -c`; temp files in your scratchpad directory (or `$TMPDIR`), never `/tmp`; a worktree's virtualenv inside the worktree.
- Never `git push` or `gh pr create` without the user's yes in this session.
- Client repos get no workflow files. The local-markdown tracker writes `.scratch/` (specs, tickets) and `docs/agents/` (tracker docs), setup's domain docs are `GLOSSARY.md`, `GLOSSARY-MAP.md` and `docs/adr/`, and the tracker config goes in `CLAUDE.local.md`. Never `git add` these paths: commits contain only product code and tests.

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

Standard and critical write workflow files, so first check that git ignores them locally. This only reads; never write the exclude file yourself (in a worktree it lives outside the session's directories):

```bash
for p in .scratch/ docs/agents/ CLAUDE.local.md GLOSSARY.md GLOSSARY-MAP.md docs/adr/ CLAUDE-SECURITY-x/; do git check-ignore -q --no-index -- "$p" || echo "not ignored: $p"; done
```

If it prints anything, stop and tell the user to run `scripts/stack.sh <repo>` from the claude-workflow checkout (it writes the exclude lines; without a terminal, e.g. through `!`, it installs nothing else), then rerun `/staff:build`. `docs/adr/` and `GLOSSARY.md` are among them: if the client repo already tracks its own ADRs or glossary there, tracked files are unaffected, but new hand-written ADRs there won't show in `git status`.

They also need an issue tracker: an `## Agent skills` section in the project config, or `docs/agents/issue-tracker.md`. If neither exists, stop and tell the user to run `/staff:setup-matt-pocock-skills`, pick local markdown, and have it put the `## Agent skills` section in `CLAUDE.local.md` (not the committed `CLAUDE.md`). Then rerun `/staff:build`.

On that rerun, if `git diff --name-only -- CLAUDE.md AGENTS.md` lists a file whose diff adds `## Agent skills`, setup edited a tracked file: stop and tell the user to move the block to `CLAUDE.local.md` and restore the tracked file.

If the configured tracker is not local markdown, stop and ask: to-spec, to-tickets and implement-spec would publish specs, tickets, issues, labels and closing links to the client's tracker.

Standard and critical work on a branch. If on the default branch, create one first. If you start services (docker compose, dev servers), say so and stop them at the end unless the user asks to keep them.

If the task adds a new component or service, offer 2–3 options with trade-offs and let the user pick before `staff:to-spec`.

When you run `staff:to-spec`, the spec must answer, or mark N/A with a reason: failure modes, idempotency, authz/tenancy, rollback, rate limits, cost, data sensitivity.

Reviews (standard and critical): follow `${CLAUDE_PLUGIN_ROOT}/skills/build/reviews.md` for the tier. It also holds the secret scan that runs before any push.

### trivial

1. Implement.
2. Run the project test command (from the project config; ask if none).
3. `/code-review low` with no target (it covers uncommitted changes, also on the default branch). Fix real findings.
4. Commit the change with a plain-prose message, without asking. On the default branch, create a branch first. Don't push.

### standard

1. `staff:to-spec`
2. `staff:implement`
3. `staff:verification-before-completion`
4. Reviews: standard.
5. Ask the user, showing the branch and the PR title and body (PR rule above). On yes, push and open the PR with `gh pr create`; otherwise stop with the branch committed.

### critical

1. `staff:grill-me`. It needs the user's answers: never answer your own questions. With no user available (e.g. headless), stop and say so.
2. `staff:to-spec`
3. `staff:to-tickets`
4. `staff:implement-spec`. Skip its draft PR: the PR comes in step 6, after the reviews and your yes.
5. Reviews: critical.
6. Ask before push and PR, as in standard step 5.
7. Print a **Read these hunks** list in the terminal: every hunk of `git diff <default branch>...HEAD` in a critical path, as `path:start-end` and one line on why it matters. If the user wants it kept, save it under `~/.local/share/staff/`, never in the repo or PR.

## 4. End

State the tier used and the PR link (if any). Tell the user to run `/staff:log merge --pr <n> --tier <tier>` after merge.

At a natural break or the end of a long run, offer `staff:handoff`. It writes to the OS temp dir, not the repo.
