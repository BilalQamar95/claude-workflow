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
- Shell commands that don't trip permission prompts: run from the repo root and use `git -C <dir>` rather than `cd <dir> && git`; no `VAR=x cmd` or `env -u` prefixes; the Grep and Glob tools where you have them, otherwise plain `grep` and `find`, never `find -exec` or `xargs sh -c`; temp files in your scratchpad directory (or `$TMPDIR`), never `/tmp`; a worktree's virtualenv inside the worktree.
- Never `git push` or `gh pr create` without the user's yes in this session.
- Client repos get no workflow files. The local-markdown tracker writes `.scratch/` (specs, tickets) and `docs/agents/` (tracker docs), setup's domain docs are `GLOSSARY.md`, `GLOSSARY-MAP.md` and `docs/adr/`, the tracker config goes in `CLAUDE.local.md`, and the gate config is `.staff-gate.toml`. Never `git add` these paths: commits contain only product code and tests.

## 1. Classify the tier

List the paths the task will likely touch. Match them against the `## Critical paths` globs in the project config.

- Any match: **critical**.
- `trivial`: one file, no behaviour change, no critical path.
- Otherwise: **standard**.
- No `## Critical paths` section: say so, and use **standard** unless the task is trivial.

You may raise the tier. Never lower it. Print one line: the tier and why (name matched paths). Then start.

## 2. Bugs

If the task is a bug, run phases 1–3 of `staff:systematic-debugging` (root cause, pattern, hypothesis) first; don't write the test or the fix yet. A bug fix changes behaviour, so it is never trivial. The reproduction becomes the first acceptance criterion, which the test author writes and the gate locks before the fix. Then continue with the tier below.

## 3. Tier steps

Standard and critical write workflow files, so first check that git ignores them locally. This only reads; never write the exclude file yourself (in a worktree it lives outside the session's directories):

```bash
for p in .scratch/ docs/agents/ CLAUDE.local.md GLOSSARY.md GLOSSARY-MAP.md docs/adr/ CLAUDE-SECURITY-x/ .staff-gate.toml; do git check-ignore -q --no-index -- "$p" || echo "not ignored: $p"; done
```

If it prints anything, stop and tell the user to run `scripts/stack.sh <repo>` from the claude-workflow checkout (repos set up before the gate existed need this rerun for `.staff-gate.toml`) (it writes the exclude lines; without a terminal, e.g. through `!`, it installs nothing else), then rerun `/staff:build`. `docs/adr/` and `GLOSSARY.md` are among them: if the client repo already tracks its own ADRs or glossary there, tracked files are unaffected, but new hand-written ADRs there won't show in `git status`.

They also need an issue tracker: an `## Agent skills` section in the project config, or `docs/agents/issue-tracker.md`. If neither exists, stop and tell the user to run `/staff:setup-matt-pocock-skills`, pick local markdown, and have it put the `## Agent skills` section in `CLAUDE.local.md` (not the committed `CLAUDE.md`). Then rerun `/staff:build`.

On that rerun, if `git diff --name-only -- CLAUDE.md AGENTS.md` lists a file whose diff adds `## Agent skills`, setup edited a tracked file: stop and tell the user to move the block to `CLAUDE.local.md` and restore the tracked file.

If the configured tracker is not local markdown, stop and ask: to-spec, to-tickets and implement-spec would publish specs, tickets, issues, labels and closing links to the client's tracker.

Standard and critical work on a branch. If on the default branch, create one first. If you start services (docker compose, dev servers), say so and stop them at the end unless the user asks to keep them.

If the task adds a new component or service, offer 2–3 options with trade-offs and let the user pick before `staff:to-spec`.

When you run `staff:to-spec`, the spec must answer, or mark N/A with a reason: failure modes, idempotency, authz/tenancy, rollback, rate limits, cost, data sensitivity.

Reviews (standard and critical): follow `${CLAUDE_PLUGIN_ROOT}/skills/build/reviews.md` for the tier. It also holds the secret scan that runs before any push.

Standard and critical also need `.staff-gate.toml` in the repo root: if it is missing, stop as in trivial step 0.

### The gate (standard and critical)

`gate` below means `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/staff_gate.py"`. `<id>` is the task id, the feature slug `staff:to-spec` chose. `CLAUDE_PLUGIN_ROOT` isn't set in a shell, so when the user must run a gate command, give it in full: the plugin path written out, `--repo <worktree path>` and absolute file paths. These rules hold from `lock` until `packet`, while the gate's hooks guard the task:

- Every question to the user starts with `NEEDS-INPUT:` and ends your turn, in every step including the reviews. Any other stop without passing evidence for the current tree is blocked.
- `gate verify <id>`: exit 1 with `gate: FAIL` means fix the code and rerun. `gate: BLOCKED` means stop and show the user the blocker file it names; only the user allows more attempts. Exit 2 (`gate: cannot run`), a traceback or command not found: stop and show the output; don't work around it.
- Every file under the test roots at lock time is locked, not only the contract's tests: put new tests in new files. Never edit a locked file, `conftest.py`, the tool config or `.staff-gate.toml`, and never add a suppression to get a pass. The hooks deny most attempts; the gate catches the rest by hash.
- A locked test you believe is wrong: write `.scratch/<id>/dispute.md` (the test, what it asserts, why the contract means something else) and stop with `NEEDS-INPUT:`. If the user rules the test changes: if the ruling changes a criterion, update `.scratch/<id>/contract.json` first; brief the test author (below) with the dispute file and the ruling; then stop with `NEEDS-INPUT:`, asking the user to read the changed test and re-lock it from their own terminal with `gate lock <contract path> --amend '<the ruling in one line>'` in full. The hooks deny your own `--amend`. If the test stays, delete the dispute file and carry on.
- Only the user ends a task without a pass, with `gate packet <id> --drop '<reason>'` in their own terminal.

Test author: the Agent tool with `subagent_type` `staff:test-author`, briefed with the contract path (and for an amendment, the dispute file and the ruling). It writes the tests and any `NotImplementedError` stubs, and can't run tests.

Packet steps, after the last `verify` passes:

1. Write `.scratch/<id>/packet-notes.md` in normal prose with only these `## ` headings, each optional except Summary: `## Summary`, `## Review results` (each review step and what it found and fixed), `## Decisions`, `## Not verified and assumptions`, `## Fix rounds`, and for critical `## Read these hunks`.
2. `gate packet <id>`. It writes the packet to the gate's state folder, prints its path and the start of its sha256, and ends the task. Show the user both. If it exits 2 over the notes, fix them and rerun; any other exit 2, stop and show the output. The packet is a workflow file: never commit it or put it in the PR.

### trivial

0. Before any edit: if `.staff-gate.toml` is missing from the repo root, stop and tell the user to copy and edit the one in the claude-workflow Python template (`templates/python/.staff-gate.toml`).
1. Implement.
2. Run the gate: `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/staff_gate.py" verify --trivial`. It scans the uncommitted diff for suppressions and test shortcuts, flags changed tool config, runs the repo's own format, lint and type tools on changed Python files, then the tests. Exit 1 with a `gate: FAIL` line: fix what it flags and rerun until `gate: pass`. Any other result (exit 2 with `gate: cannot run`, a traceback, command not found): stop and show the user the output; don't change code to work around it. At most three failing runs in total across steps 2 and 3; then stop and tell the user what still fails. Never create or edit `.staff-gate.toml` or add a suppression to get a pass; if a flagged item is legitimate, ask the user.
3. `/code-review low` with no target (it covers uncommitted changes, also on the default branch). Fix real findings, then rerun the gate.
4. Commit the change with a plain-prose message, without asking. On the default branch, create a branch first. Don't push.

### standard

1. `staff:to-spec`. It writes the spec with its acceptance table and the draft contract at `.scratch/<id>/contract.json`.
2. Contract gate: show the user the acceptance table and the contract path and ask them to approve or change it. Don't go on without their yes; with no user available (e.g. headless), stop and say so.
3. Test author, briefed with the contract path.
4. `gate lock .scratch/<id>/contract.json`. It proves each test fails for the right reason, hashes the tests and protected config, and switches the hooks on. On `FAIL` lines, send the output back to the test author; after three failed locks, show the user the output and ask. Exit 2 because a criterion's test file doesn't exist: send it back to the test author once. Any other exit 2: stop and show the output. On `lock: ok`, commit the tests and stubs with a plain-prose message.
5. `staff:implement`, committing as it goes.
6. `gate verify <id>` until `gate: pass` or a blocker. It replaces `staff:verification-before-completion` here.
7. Reviews: standard.
8. `gate verify <id>` again on the reviewed tree, until it passes.
9. Packet steps.
10. Ask the user, showing the branch and the PR title and body (PR rule above). On yes, push and open the PR with `gh pr create`, then offer `gate packet <id> --ci <pr number>` once the client's CI has run; otherwise stop with the branch committed.

### critical

1. `staff:grill-me`. It needs the user's answers: never answer your own questions. With no user available (e.g. headless), stop and say so.
2. `staff:to-spec`, as in standard step 1.
3. `staff:to-tickets`
4. Contract gate, test author and lock, as in standard steps 2–4.
5. `staff:implement-spec`, with the current branch (where the tests were locked and committed) as its integration branch. Skip its draft PR: the PR comes in step 9, after the reviews and your yes. Brief each implementer subagent with the gate rules above (no edits to locked tests or protected config; a wrong test gets a dispute, not an edit): the hooks guard this worktree only, and the gate's hash check catches the rest when you verify. Run the implementer subagents in the foreground, as parallel Agent calls in one message, not in the background: ending your turn to wait trips the Stop hook. Run no `verify` until every ticket is merged.
6. `gate verify <id>` until it passes or a blocker, on the integration branch in this worktree.
7. Reviews: critical.
8. `gate verify <id>` again, then the packet steps, with the `## Read these hunks` list in the notes: every hunk of `git diff <default branch>...HEAD` in a critical path, as `path:start-end` and one line on why it matters.
9. Ask before push and PR, as in standard step 10.
10. Print the **Read these hunks** list in the terminal too.

## 4. End

State the tier used and the PR link (if any). Tell the user to run `/staff:log merge --pr <n> --tier <tier>` after merge.

At a natural break or the end of a long run, offer `staff:handoff`. It writes to the OS temp dir, not the repo.
