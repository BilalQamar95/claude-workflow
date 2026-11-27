# Stage 2a — contract, locked tests, gate, hooks, local evidence packet

Status: ready-for-agent. Written 2026-11-27 from the stage-2 grilling (round 1, all recommendations accepted by the user) and the to-spec seam check. Builds on branch `stage1.1`, which must pass one real standard task and be merged to `main` first.

Inputs: goal doc (`2026-11-25-staff-workflow-goal.md`), stage-1 spec and its stage-2 backlog (`2026-11-25-stage1-daily-driver-design.md`), blueprint §3 pipeline, §4 anti-gaming, §7 tiers, §8 evidence packet, §13 build plan (local-only design docs), pilot-2 report.

## Problem Statement

Today every standard and critical task ends with me reading the whole diff, because nothing in the workflow proves the change does what was asked. The tests are written by the same session that writes the code, so they can be bent to pass. Nothing stops the agent from editing a test, adding a `skip` or a `noqa`, or claiming success without running anything. The review list finds problems but produces no single record of what was checked. By week 6 I want standard tasks reviewed by exception: I approve a contract before the work and an evidence packet after it, and I only read the diff when the packet tells me to.

Two of my standing rules shape this: nothing workflow-internal goes into a client repo, commit or PR, and client repos may not get our CI config without the client's agreement.

## Solution

Standard and critical tasks gain four things, in this order:

1. **A contract.** The spec I already approve gains an acceptance-criteria table. Each criterion names the check that proves it. Approving the spec is approving the contract.
2. **Locked tests.** A separate test-author agent, which sees only the contract and the interfaces, writes failing tests for each criterion before any implementation exists. A gate script confirms they fail for the right reason, then records their hashes. From then on the implementer cannot change them; if a test looks wrong it files a dispute and stops.
3. **A gate.** One plain script runs every deterministic check: locked tests unchanged, protected config unchanged, no new suppressions or cheat patterns, lint and types with the repo's own tools, tests, diff coverage. It writes the evidence itself; the agent cannot. Hooks deny edits to locked tests, protected config and the evidence, and stop the session from ending until the gate has passed for the current tree or the agent has escalated.
4. **A local evidence packet.** The gate renders a packet from its evidence: the acceptance-criteria matrix, the gate log, coverage, review results, disputes, what was not verified, and cost. It lives outside the repo and is shown to me only. The PR stays plain, client-facing prose.

The stage-1 review list stays as it is; slice 2b replaces it with a find, verify and rank review workflow. Trivial tasks run the gate's cheap checks and nothing else new.

## User Stories

1. As the engineer, I want the spec I approve to contain a numbered acceptance-criteria table, so that approving the spec is approving exactly what will be proven.
2. As the engineer, I want each acceptance criterion to name its check (a test node id, an eval, or "manual" with a reason), so that no criterion is unverifiable by accident.
3. As the engineer, I want "manual" criteria to appear in the packet's not-verified section, so that I know what I still have to check myself.
4. As the engineer, I want the contract to describe behaviour, not implementation, so that the implementer keeps design freedom and the tests don't lock in internals.
5. As the engineer, I want a test author with a clean context to write the failing tests from the contract and interfaces only, so that the tests cannot mirror the implementation.
6. As the engineer, I want the test author to be allowed to add minimal interface stubs that raise `NotImplementedError`, so that tests fail on an assertion rather than an import error.
7. As the engineer, I want the gate to refuse to lock tests that fail for the wrong reason (import, syntax or collection errors), so that red really means "behaviour missing".
8. As the engineer, I want the gate to refuse to lock tests that already pass, so that a test that proves nothing is caught before implementation.
9. As the engineer, I want locking to record a hash of each locked test file in a contract record outside the repo, so that any later change is detectable.
10. As the engineer, I want a bug-fix task's reproduction test to go through the same lock, so that the regression test is proven red before the fix.
11. As the engineer, I want the implementer to be blocked from editing, moving or deleting locked test files, through the file tools and through common shell forms, so that the dominant cheating mode is prevented, not just detected.
12. As the engineer, I want protected config (pytest, coverage, ruff, mypy, `conftest.py`, CI files, the gate's own config) to be hashed at lock time and flagged if changed, so that weakening the harness shows up.
13. As the engineer, I want the implementer, when it thinks a locked test is wrong, to write a dispute and stop with a `NEEDS-INPUT:` line, so that it has a legitimate exit instead of an incentive to cheat.
14. As the engineer, I want disputes in the standard tier to come to me in 2a (the arbiter agent comes later), so that only I or the test author ever change a locked test.
15. As the engineer, I want any amendment of a locked test to go through the test author and a re-lock, and to be listed in the packet, so that every test change is visible.
16. As the engineer, I want the agent to run the gate itself as a visible command and read its output, so that failures feed back into the work instead of hiding inside a hook.
17. As the engineer, I want gate failures to print the first actionable lines and a suggested next step, so that the agent fixes the cause rather than grinding.
18. As the engineer, I want the gate to stop after three failed attempts and write a blocker note of what was tried, so that repeated test feedback does not push the agent into hacks.
19. As the engineer, I want the gate's diff scan to flag new `skip`, `xfail`, `noqa`, `type: ignore`, `pragma: no cover`, swallowed exceptions, environment sniffing in source, and new equality or truthiness overrides, so that the known cheat patterns are caught deterministically.
20. As the engineer, I want the gate to flag test functions with no assertion and tautological assertions in added tests, so that empty tests don't count as proof.
21. As the engineer, I want the gate to flag expected literals from locked tests appearing as new literals in source, so that special-casing test inputs is visible.
22. As the engineer, I want lint, format and type checks to run only with tools the repo already configures, so that the gate never imposes our standards on a client repo.
23. As the engineer, I want the gate to run the affected tests first and then the suite the repo's gate config names, so that feedback is fast and the final run is complete.
24. As the engineer, I want diff coverage reported against a threshold when the repo has coverage installed, and reported as "not measured" otherwise, so that missing tooling is visible rather than silently passing.
25. As the engineer, I want evidence keyed by the git tree hash, so that evidence for an older tree can never pass for the current one.
26. As the engineer, I want the evidence written only by the gate, in a directory outside the repo that the hooks protect, so that the agent cannot forge a pass.
27. As the engineer, I want the session blocked from ending while a staff task is active without passing evidence for the current tree, a dispute, a blocker, or a `NEEDS-INPUT:` message, so that "done" without proof is impossible.
28. As the engineer, I want the hooks to do nothing at all in sessions with no active staff task, so that my other work pays no latency and sees no denials.
29. As the engineer, I want the "no active task" check to happen before any interpreter starts, so that the hooks cost near-zero on every tool call outside staff tasks.
30. As the engineer, I want ruff format and check to run after each Python edit only when the repo configures ruff, so that edits stay clean without imposing ruff on repos that don't use it.
31. As the engineer, I want package installs during an active task to ask me unless the package is listed in the contract's allowed new dependencies, so that hallucinated or squatted packages don't slip in.
32. As the engineer, I want the packet's acceptance matrix, gate log and coverage rendered by the gate from its evidence, never typed by the agent, so that the facts in the packet are trustworthy.
33. As the engineer, I want the agent's own sections of the packet (summary, decisions, review results, not verified, assumptions) clearly labelled as agent-written, so that I know which parts are claims and which are measurements.
34. As the engineer, I want the packet to state tokens, wall time, gate attempts and fix rounds, so that I can track cost per tier.
35. As the engineer, I want the packet to record the client CI result for the PR once it exists, so that an independent run of the tests backs the local evidence.
36. As the engineer, I want the packet's not-verified section to say plainly that the evidence is local and what the hooks cannot prevent, so that the weaker anti-forgery is never hidden.
37. As the engineer, I want the packet to list the hunks to read for critical tasks, so that critical review stays focused.
38. As the engineer, I want the packet stored outside the repo per repo and task, so that it survives worktree removal and never reaches a client.
39. As the engineer, I want the PR body to stay plain client-facing prose with no packet content, so that my standing rule holds.
40. As the engineer, I want the gate's per-repo config in a git-excluded file that `stack.sh` excludes, so that client repos get no workflow files.
41. As the engineer, I want the gate to refuse to run without its per-repo config and say how to create it, with a template example, so that a missing config is a clear stop, not a silent default.
42. As the engineer, I want the gate to run without installing anything into the client's environment, so that it works in restricted client setups.
43. As the engineer, I want the trivial tier to run the gate's cheap checks (suppression scan, lint and tests) before its commit, with no contract, lock or packet, so that trivial stays fast.
44. As the engineer, I want the router's standard and critical steps reordered to spec with contract, approval, test author, lock, implement, gate, reviews, gate again, packet, then ask before push, so that the pipeline runs in one predictable order.
45. As the engineer, I want the active-task marker set at lock and cleared after the packet, so that the hooks guard exactly the implementation window.
46. As the engineer, I want questions to me during an active task to start with `NEEDS-INPUT:`, so that the stop hook lets the session pause for me.
47. As the engineer, I want the sandbox enabled per repo through `stack.sh` (offered, default yes), with writes limited to the repo, the staff state directory and temp, and network limited to the package indexes and GitHub, so that out-of-project writes and egress are enforced at the OS level for shell commands.
48. As the engineer, I want the sandbox's limits stated in the packet (Bash only; file tools, web fetch, hooks and MCP servers are outside it), so that I don't over-trust it.
49. As the engineer, I want reusable skill-reviewer and hook-reviewer agents built first, so that every skill, agent and hook in this stage gets a specialised write and a separate review with a docs fact-check.
50. As the engineer, I want a fixture repo with one planted cheat per anti-gaming row, run by the gate's tests, so that each prevention or detection is proven to work.
51. As the engineer, I want hook latency measured once with debug timings, so that I know the cost of the hooks on active and inactive sessions.
52. As the engineer, I want CI for this repo (plugin validation and every self-test) written now, so that it runs as soon as the repo has a remote.
53. As the engineer, I want ten real tasks logged before standard drops to contract-plus-packet review, and two escaped defects in those ten to send it back to reading diffs, so that trust is earned with data.
54. As the engineer, I want a standard-tier cost target of a $7 median and 12 minutes median after 2a, so that the extra steps don't make the workflow worth bypassing.
55. As a future maintainer, I want every stage-2 backlog item either built here, assigned to 2b or stage 3, or skipped with a reason, so that nothing from the design docs is dropped silently.

## Implementation Decisions

**Slicing.** Stage 2 ships as 2a (this spec) and 2b (find, verify and rank review workflow, critic panel, review-relevant checklist subset). 2b gets its own grilling after 2a has run on real tasks. Facts for 2b from the 2026-11-27 docs check: plugin workflows exist (a `workflows/` directory, invoked namespaced, background and resumable within a session, per-agent JSON `schema`); whether a workflow agent can target a plugin agent type or run a bundled skill is not documented.

**Gate script.** One self-contained Python script in the plugin, run through `uv run --script` with an inline metadata block requiring Python 3.11 or later (the machine's `/usr/bin/python3` is 3.9, which lacks `tomllib`, and hooks don't see shell functions). Standard library only, so no client dependencies and no install. Subcommands:

- `lock <task>`: read the draft contract, run the listed tests, require each to fail for the right reason (assertion failure or `NotImplementedError`; not collection, import or syntax errors; not passing), hash locked test files and protected config, write the contract record to the state directory, set the active-task marker.
- `verify <task>`: run the checks below cheapest first, write evidence keyed by tree hash, count attempts, write a blocker note after the third failure.
- `packet <task>`: render the packet from the contract record, evidence and the agent's notes file, then clear the active-task marker.
- `hook <event>`: the logic behind every hook, reading the hook payload from stdin.
- A trivial mode of `verify` that runs only checks 3 to 5 with no contract.

**Gate checks, cheapest first (v1).**

1. Locked-test hashes unchanged.
2. Protected-config hashes unchanged, else flagged with the diff.
3. Diff scan for suppressions and cheat patterns: `skip`, `xfail`, `noqa`, `type: ignore`, `pragma: no cover`, `except ...: pass`, environment sniffing in source (`"pytest" in sys.modules`, `TESTING` branches), new `__eq__`, `__ne__`, `__hash__` or `__bool__` in source, added test functions without an assertion, `assert True`, and expected literals from locked tests appearing as new source literals.
4. Format, lint and typecheck on changed files, only for tools the repo configures.
5. Tests: affected first, then the suite from the gate config.
6. Diff coverage against the configured threshold, when coverage is available; otherwise "not measured".

Built in ticket 02 (trivial mode), after a code review that reproduced bypasses: file names come from `-z` lists and hunks from per-file diffs with `--text --no-textconv`, so odd paths, faked headers and `-diff` attributes can't hide changes; files with staged and unstaged changes that differ, changed tool config (a fixed list in trivial mode), and git-ignored files Python or pytest load on their own (`conftest.py`, `sitecustomize.py`, `.pth`) are flagged. Known limits of trivial mode: the gate config itself is git-ignored and unprotected until `lock` hashes it; the pattern scan is regex and AST based and can be dodged by code it doesn't model; listing ignored files walks ignored folders, which may be slow in large repos.

`lock` as built (ticket 03), after a code review that reproduced eleven bypasses: results come from a small pytest plugin the gate loads with `-p`, which writes one JSON record per test phase, so faked or truncated terminal lines can't decide anything. A test locks only if every call phase fails on an assertion raised in a test file (helpers included) or on `NotImplementedError` raised outside the tests, with clean setup and teardown, no skipped, xfailed or passing variant, and the trivial scan clean over the locked test functions (tautologies, no assertion, skips, direct raises of `AssertionError` or `NotImplementedError`). The record hashes every file under the test roots plus the protected config. `--amend` still requires the tests to run (passing is allowed by then) and records file and contract-field changes. Known limits: the plugin needs pytest in the gate's environment (a test command that runs pytest inside a container won't load it); `pytest.fail("DID NOT RAISE")` and assertions unrelated to the behaviour are left to the contract review; a `conftest.py` can still rewrite outcomes, though it is hashed; deleting the active-task marker would switch the hooks off, so the hooks (ticket 05) must protect the state directory and the Stop hook must not trust a missing marker alone.

`verify <task>` as built (ticket 04): it runs only for the task named in the worktree's active-task marker. Checks 1 and 2 compare the hashes recorded at lock with the files now; if either fails, nothing else runs, so commands from changed config are never executed. Checks 3 and 4 reuse the trivial mode against the commit at lock time. The expected-literal part of check 3 is a warning shown in the output and the evidence, not a failure, because the user story asks for it to be visible and legitimate code often shares small numbers with tests; it only looks at comparisons. Check 5 runs the locked tests first through the report plugin (every phase of every variant must pass, no xfail), then the configured suite. Check 6 runs only when `coverage_threshold` is set: the suite runs once under pytest-cov with a JSON report, and diff coverage is executed added lines over measurable added lines in changed source files; a changed file no test imports counts all its added code lines as missed. Without the key or without pytest-cov it says "not measured". Evidence is written to `evidence/<tree>.json`, where the tree is `git add -A` plus `git write-tree` on a copy of the index, so evidence for one tree can't stand for another; if the tree changes while the gate runs, the run fails. Attempts count in `attempts.json`; a pass resets the run of failures, and the third failure in a row writes `blocker.md` with what failed each time. The dispute file the gate points to is `.scratch/<task>/dispute.md`. A code review reproduced three passes with wrong code and two smaller faults, all fixed: pytest config (`pytest.ini`, `.pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml` and the other tool config) is now protected at any depth and also when git-ignored; every git, tool and test command runs with `GIT_*`, `PYTHON*`, `PYTEST_*`, `COV_*` and `COVERAGE_*` removed from the environment, because the agent is the caller (so a user's own `PYTEST_ADDOPTS` is ignored too); files marked skip-worktree or assume-unchanged are flagged, since git diff and git add can't see them (a sparse checkout therefore fails the gate); a blocker note stops further `verify` runs until the user deletes it; and a record missing a key stops with exit 2. Known limits: git-ignored files other than config and autoloaded files are not part of the tree hash; `.pth` files inside a virtualenv are not checked; code under test could still forge the plugin's report in-process; pytest-rerunfailures' `rerun` outcome would read as a failure; `STAFF_STATE_DIR` is read from the environment; the hooks read it from Claude Code's own environment, which the agent can't change, and deny any shell command that names it, so the agent can't lock or verify against a state directory the hooks don't watch.

Tool hooks as built (ticket 05): `hooks/hooks.json` runs `hooks/guard.sh` in exec form for PreToolUse on Edit, Write, NotebookEdit, Bash, PowerShell and Monitor (with `onFailure: "block"`, so a crash or timeout blocks the call) and for PostToolUse on Edit and Write. The guard is a shell loop that exits unless some marker exists in the state directory's `active/` folder; only then does it start the gate's `hook` subcommand, which applies each rule only to paths in a worktree whose task is active. File tools are denied for locked tests, protected config (the recorded files, plus any new file matching the protected globs, such as a new `tests/pytest.ini` or `conftest.py`) and gate-owned paths (the state directory and the plugin itself). Shell commands are split into segments; a segment is denied when a writing command (`sed -i`, `mv`, `rm`, `tee`, `git checkout` or `restore`, and so on), a redirect target or a copy destination names one of those paths, or inline interpreter code mentions one; `--no-verify` and `git commit -n` are denied; installs whose packages are not in the contract's allowed new dependencies, or that come from a file, path or other index, become a question. Every shell reason says the check is best effort. PostToolUse runs the repo's own format and lint commands when they are ruff, and feeds failures back to Claude. A live headless run (2026-11-27, auto mode) confirmed that the deny holds for Edit, for Bash, and for a subagent's Edit. Latency per matching tool call: about 10 ms with no active task, about 190 ms with one. The hook review reproduced state-directory bypasses (`cd` then `rm`, removing a parent, globs, find's delete action, inline code containing `;`, case variants on macOS) and a few false or missed git-hook checks. After the fixes, paths are compared by file identity (device and inode of the nearest existing ancestor), so symlinks, `..` and other letter cases resolve to the protected file; `cd` is followed between segments; globs are expanded; removing a folder that contains the state directory or the plugin is denied; a writing command that names the staff data directory or the plugin is denied as text; `git commit` option clusters are parsed so `-n` inside a message no longer counts, and `core.hooksPath` is denied; an editable install of anything but the project itself asks; and a missing `uv` blocks with a clear message rather than `exec: uv: not found`. Known limits: shell checks miss indirection (variables, scripts written then run, other languages); only Python installers are checked; a missing marker switches the hooks off, so deleting it is denied and the Stop hook (ticket 06) must also check for a lock record without a packet; with a task active anywhere on the machine, every matching tool call in every session pays the Python start.

Stop hook as built (ticket 06): `hooks.json` runs the guard for Stop with no matcher. The guard starts Python when a marker exists or, for Stop only, when a lock record has no `packet.md` beside it (the packet, ticket 07, writes that file), so deleting the marker doesn't end a task. The gate finds the session's worktree by walking up from the payload's `cwd` to the first directory with gate state, then falls back to the git top level. For each unfinished task there it allows the stop when the evidence file for the current tree says pass, when `blocker.md` exists, or when `.scratch/<task>/dispute.md` is a non-empty file written after the last lock; a re-lock after the user's ruling closes the dispute. A last assistant message starting with `NEEDS-INPUT:` (the payload's `last_assistant_message`) always allows. Otherwise it blocks with a reason for Claude; with `stop_hook_active` true it lets the session end and shows the reasons to the user as a `systemMessage`. Files marked skip-worktree or assume-unchanged block, since the tree hash can't see their edits, and the tree hash now runs with `core.fsmonitor` off. Any error inside the check blocks rather than crashing, because a crashed or timed-out Stop hook lets the stop through (`onFailure` doesn't apply to Stop). Without `uv` the guard blocks once and then lets the session end. The hook review reproduced four bypasses before these fixes: `cd .git`, a nested repo under `.scratch/`, a dispute that outlived its ruling (or an empty directory named `dispute.md`), and a skip-worktree edit. Known limits: Claude Code's own cap of eight Stop continuations in a row, and the spec's second-stop rule, mean the hook can delay but never force work; flooding the worktree so `git add -A` outlasts the 60 s timeout lets a stop through; an abandoned locked task blocks each stop in its worktree once until the user drops it with `packet <task> --drop`.

`packet <task>` as built (ticket 07): it renders only when the evidence for the current tree passed against the lock record as it is now (evidence stores the record's hash, so a pass from before a re-lock doesn't count), or when the user passes `--drop REASON`. A blocked or disputed task gets no packet and stays active, with its hooks on; the Stop hook already lets that session pause. The agent's sections come from `.scratch/<task>/packet-notes.md` (`## Summary` required; Review results, Decisions, Not verified and assumptions, Read these hunks for critical tasks, Fix rounds), and every agent-written block, the open dispute included, is shown inside a fenced block under an "agent-written" label, so it can't pose as a heading or a table row; contract text in tables is put on one line with pipes escaped. Measured sections (acceptance matrix, gate log with tree hash, diff coverage, amendments, manual criteria, gate warnings, cost) come only from the record, the evidence and `attempts.json`, and the not-verified section always states the limits of local evidence, the hooks and the sandbox. Tokens are summed from the Claude Code transcripts the PreToolUse hook saw during the task (and their subagent transcripts), counting each API response once; the transcript format is internal, so this is best effort. The packet goes to `packet.md` in the task's state folder with `packet.json` (tree, result, sha256), the sha256 is printed, and the marker is cleared. `--ci <pr>` checks with `gh pr view` that the PR head has exactly the packet's tree, then writes `gh pr checks` output to `ci.md`; it refuses if `packet.md` no longer matches its hash. The PreToolUse hook denies the agent's `--drop` (and its prefixes; argparse abbreviations are off). The review reproduced seven faults, all fixed: a dispute or self-made blocker ended the task and switched the hooks off; agent text and contract text could forge headings and table cells; `--dr` slipped past the drop deny; `--ci` accepted any PR and could be truncated by a heading in the dispute; one test's failure marked a test with a prefix-sharing name as failed; stale evidence counted after an amendment; malformed evidence crashed a drop. While testing, a flaky failure showed that Python can reuse a stale `.pyc` when a source file keeps its size within the same second, so `lock` and `verify` now point the commands they run at the gate's own bytecode cache (`PYTHONPYCACHEPREFIX` under the state folder) and clear the repo's entries in it before each run; installed packages, virtualenvs inside the worktree included, stay cached, because a fresh cache per run cost about 1.7 s per Python process. A test with the same size and mtime but different code failed the gate before this change. Known limits: once the marker is cleared nothing guards the state folder, so `packet.md` and `packet.json` could both be edited afterwards; the printed hash in the session is the check.

Migration checks and eval wiring are later stages (S3 eval wiring is stage 3). Each failure prints the first actionable lines and a next step.

**State layout.** Gate-owned state lives outside the repo under the staff data directory (`~/.local/share/staff/`), per repo and per task: contract record, evidence, attempts, blocker note, rendered packet, raw test output. Agent-writable task files (draft contract, dispute, packet notes) live in the repo's excluded `.scratch/` area next to the spec, so the agent never needs write access outside its working directories. The active-task marker is keyed by the worktree's top-level path, so worktrees of one repo don't share a task by accident.

**Contract.** `staff:to-spec` gains an acceptance-criteria table in the spec and writes a draft contract file next to it: goal, non-goals, criteria (id, statement, check type `test`, `eval` or `manual`, reference), invariants, failure modes, slices, allowed new dependencies. The router asks me to approve the spec; approval is the contract gate. Lock copies the draft into the state directory, and from then on that copy is authoritative.

Shape of the draft contract (from the blueprint, trimmed to 2a's fields):

```jsonc
{
  "id": "2026-11-27-example",
  "tier": "standard",
  "goal": "...",
  "non_goals": ["..."],
  "acceptance": [
    {"id": "AC1", "statement": "...", "verify": {"type": "test", "ref": "tests/x/test_y.py::test_z"}},
    {"id": "AC2", "statement": "...", "verify": {"type": "manual", "reason": "..."}}
  ],
  "invariants": ["..."],
  "failure_modes": ["..."],
  "slices": [{"id": "S1", "acs": ["AC1"]}],
  "allowed_new_deps": []
}
```

The lock adds `locked_tests` and `protected_config` hash maps to the state-directory copy only.

**Test author.** A new plugin agent with a clean context and a narrow tool set. Input: the contract and the relevant interfaces. It writes failing tests per criterion and may add interface stubs that raise `NotImplementedError`; it never writes implementation. The implementer (`staff:implement` or `staff:implement-spec`) starts only after a successful lock. Amending a locked test means: dispute, my ruling, the test author edits, re-lock; the packet lists every amendment.

**Hooks.** Plugin hooks call `staff-gate hook <event>`, guarded by a shell check that exits immediately when no active-task marker exists for the session's working directory, so the interpreter never starts outside staff tasks.

- PreToolUse on file tools: deny edits to locked tests, protected config and the gate's state directory.
- PreToolUse on Bash: deny in-place edits, redirects, moves, deletes and `git checkout` or `git restore` that target locked paths or the state directory; deny `--no-verify`; turn package installs into a question unless the package is in the contract's allowed new dependencies. Best-effort, as the docs say Bash rules match command text, not every form of the program.
- Stop: block with a reason unless evidence passes for the current tree hash, a dispute or blocker exists, or the last assistant message starts with `NEEDS-INPUT:`. Respect `stop_hook_active` so a second block in a row explains and lets the session stop rather than looping.
- PostToolUse on Python edits: ruff format and check on the edited file when the gate config says the repo uses ruff (S4).

Whether a PreToolUse deny holds in auto mode and inside subagents is not confirmed by the docs; the fixture tests and the pilot must show it.

Hook docs facts found while testing the reviewer agents (2026-11-27), to apply when building the hooks: a hook that crashes, times out or can't start is a non-blocking error and lets the action through, unless the handler sets `onFailure: "block"` (Claude Code v2.1.295 or later; ignored on Stop). Use exec form (`command` plus `args`) for `${CLAUDE_PLUGIN_ROOT}` paths, since the plugin path can contain spaces. A handler-level `if` permission rule filters tool events before the command starts, and a hook with `if` on a non-tool event never runs. `${CLAUDE_PLUGIN_DATA}` is a documented per-plugin data directory; weigh it against `~/.local/share/staff/` for gate state. PreToolUse's top-level `decision`/`reason` are deprecated in favour of `hookSpecificOutput.permissionDecision`.

**Per-repo gate config.** A small TOML file in the client repo, git-excluded by `stack.sh` (added to its exclude list and to the router's check). Keys: test command, affected-test command or strategy, source and test roots, protected config globs, coverage threshold, which lint, format and type tools the repo uses. The Python template ships a commented example. No config means the gate stops and says how to create one.

**Router.** Standard: to-spec with acceptance table and draft contract, approval, test author, lock, implement, `verify` until pass or blocker, stage-1 reviews, `verify` again after fixes, packet, ask before push and PR. Critical keeps grill-me, to-tickets, implement-spec, the critical review list and the read-these-hunks list, in the same pipeline. Trivial adds the trivial-mode `verify` before its commit. Questions during an active task start with `NEEDS-INPUT:`.

**Packet.** Rendered by the gate into the state directory and printed in the terminal. Sections follow blueprint §8: summary, acceptance matrix, gate log with tree hash, test strength (diff coverage; mutation and property tests are "not measured" until stage 3), review results, test amendments and disputes, read-these hunks (critical), decisions, not verified and assumptions, cost. Measured sections come from evidence; agent sections come from the notes file and are labelled as agent-written. Once a PR exists, the client CI result from `gh pr checks` is added on request.

**Sandbox.** `stack.sh` offers it per repo, default yes, writing to the repo's local settings: enabled, writes allowed to the repo, the staff state directory and temp, network allowed to the Python package indexes and GitHub. It applies to Bash and its child processes only. Behaviour in headless `claude -p` is not documented and gets tested in the pilot.

**Reviewer agents.** Two plugin agents, skill-reviewer and hook-reviewer, built before anything else in 2a. Each takes a changed skill, agent or hook and checks it against the official docs: every frontmatter key and setting fact-checked, triggering, tool scope, failure modes.

**Backlog placement.** In 2a: S4 ruff hook, S8 CI for this repo, S10 `plugin-dev` toolkit for hook authoring, S11 hook latency, reviewer agents, planted-cheat fixture, sandbox. In 2b: critic panel, review-relevant checklist subset, the review workflow with verifier and arbiter agent. Stage 3: S1 `/staff:learn` and its auto-detection, S2, S3 eval wiring, S5 `/staff:init`, S6 ADRs and glossary, S7 plugin evals, S9 vendored re-scan in CI, holdout tests, mutation testing, property-test requirements, cross-model reviewer, migration checks, the Django template, marketplace commit pinning. TaskCompleted per-slice hook: stage 3 (the Stop hook covers 2a).

**Rejected.** Evidence packet in the PR body: breaks the no-workflow-internals rule. CI re-running the gate as the authority: needs our CI config in client repos; client CI re-running the tests, recorded in the packet, is the independent check instead, with the residual forgery risk stated in the packet.

## Testing Decisions

- One seam: the gate script's command line. Hooks call the same script, so hook logic is tested through `hook <event>` with recorded stdin payloads. Good tests drive the CLI and assert on exit codes, printed lines and the files it writes; they never import internals.
- A planted-cheat fixture: the gate's tests build a throwaway git repo with a tiny Python package, pytest, a gate config and a contract, then apply one planted change per anti-gaming row (edited locked test, deleted test, new `skip`, new `noqa`, swallowed exception, environment sniffing, `__eq__` override, assertion-free test, special-cased literal, lowered coverage threshold, forged evidence write, `--no-verify`). Each must be denied by a hook payload or flagged by `verify`. Clean changes must pass. Lock must reject tests that pass, error on import or fail to collect.
- Stop-hook cases: active task without evidence blocks; evidence for an older tree blocks; a dispute, a blocker or a `NEEDS-INPUT:` last message allows; `stop_hook_active` allows with an explanation; no active task exits at the shell guard.
- Prior art: `stack.sh --self-test` and `staff_log.py --self-test` (assert-based, no test framework, run in CI for this repo). The gate's tests follow that style or plain pytest run by `uv`, whichever keeps the gate dependency-free.
- No automated seam for router and skill text. Those are checked by the reviewer agents and by pilot tasks: first one standard task on the AgencyOS pilot worktree, then the ten-task proof.
- Hook latency (S11): one measured session with debug hook timings, active and inactive, recorded in the spec's verification notes.

## Out of Scope

- The review workflow with finding verifier, arbiter and critic panel (2b).
- Holdout tests, mutation testing, property-test requirements, cross-model review, migration checks, eval wiring (stage 3).
- CI config in client repos, and the packet in PR bodies (rejected above).
- `/staff:init`, `/staff:learn`, the Django template, marketplace pinning, plugin evals (stage 3).
- Auto-merge or earned auto-ship (later; needs the metrics first).

## Further Notes

- Order of work: merge `stage1.1` after its pilot task; reviewer agents; gate `lock` and `verify` with the fixture; hooks; packet; router and skill changes; sandbox and `stack.sh` changes; this repo's CI; latency measurement; pilot.
- Cost baseline from pilot 2: trivial about $1 and 2 minutes, standard about $5 and 8 minutes, critical about $11 and 33 minutes, reviews about 70% of cost. Targets after 2a: standard median at most $7 and 12 minutes. All numbers are guesses to adjust from real data.
- Proof bar: ten real tasks logged before standard drops to contract-plus-packet review; two escaped defects in those ten return it to diff reading.
- Open facts the pilot must settle: PreToolUse deny in auto mode and subagents; sandbox in headless runs. Settled by pilot 3 (2026-11-27): a general-purpose subagent can run the bundled `security-review` skill.
- Pilot 3 showed tests and implementation written before any red run in the standard tier; the lock step's red check is what fixes that.
- Client-repo specs always go through the configured local-markdown tracker; this repo keeps its specs in `docs/superpowers/specs/` because it is the workflow's own repo.
