# Stage 1 — Week-1 Daily Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this repo a local Claude Code marketplace whose `staff` plugin, settings script and Python template turn the machine into the week-1 daily driver.

**Architecture:**
- `claude-workflow` hosts a local marketplace with one plugin, `staff`. The plugin holds the `/staff:build` tier router, `/staff:log` metrics and vendored Pocock and superpowers skills pinned by SHA.
- `scripts/setup.sh` applies user-global settings through `jq` (with a backup) and the `claude plugin` CLI.
- `templates/python/` seeds client repos. A small FastAPI pilot repo proves the flow end to end.

**Tech Stack:** Claude Code 2.1.332 plugins/skills, zsh, jq, Python 3.11 (stdlib only for `staff_log.py`), uv, gh, FastAPI + SQLAlchemy + LangGraph (pilot only).

**Spec:** `docs/superpowers/specs/2026-11-25-stage1-daily-driver-design.md` (goal: `docs/superpowers/specs/2026-11-25-staff-workflow-goal.md`)

## Global Constraints

- macOS, zsh. No Windows support.
- `~/.claude/settings.json` is edited only through `jq`, after writing `~/.claude/settings.json.bak-<YYYYmmdd-HHMMSS>`. Keys the script doesn't name are left untouched.
- Pocock source: `mattpocock/skills` @ `d65391149dbb5fe76478e76fa8d5122b2aa5a70e` (MIT).
- Superpowers source: `obra/superpowers` @ `22f0b463e7a5e579904dd6211a520321035526f7` (MIT).
- Each vendored source keeps its LICENSE file.
- `/staff:build` SKILL.md is under 80 lines and has `disable-model-invocation: true`.
- Template sizes: `CLAUDE.md` is at most 120 lines. Each `.claude/rules/*.md` is at most 30 lines.
- Metrics go to `${STAFF_METRICS:-$HOME/.local/share/staff/metrics.jsonl}`, never inside a repo.
- No hosted services beyond Anthropic and GitHub.
- No telemetry leaves the machine.
- `autoUpdatesChannel` = `stable`.
- `env.CAVEMAN_DEFAULT_MODE` = `lite`.
- Enable: `pyright-lsp@claude-plugins-official`, `pr-review-toolkit@claude-plugins-official`, `staff@claude-workflow`.
- Disable: `superpowers@claude-plugins-official`, `impeccable@impeccable`, `playwright@claude-plugins-official`, `frontend-design@claude-plugins-official`.
- Commits use conventional prefixes (`feat:`, `chore:`, `docs:`).

## Review Focus

1. **Name collision.** Vendored Pocock `code-review` and `tdd` share names with the bundled `/code-review` and the `code-review` plugin.
   - Expected: every in-skill reference to a sibling skill resolves to `staff:<name>`.
   - Test: Task 2 Step 4 grep.
2. **`setup.sh` run twice, or run when a plugin is already in the target state.**
   - Expected: a second run changes nothing except adding a new backup, and prints no errors.
   - Test: Task 6 Step 4.
3. **`settings.json` contains keys the script doesn't know about** (`statusLine`, `pluginConfigs`, `modelSettings`).
   - Expected: those keys are preserved byte-for-byte.
   - Test: Task 6 Step 4 jq diff.
4. **`staff_log merge` gets an unmerged PR, a PR with zero commits, or a squash-merged PR.**
   - Expected:
     - Unmerged: exit 1 and append nothing.
     - Zero commits: lead time is measured from `createdAt`.
     - Squash-merged: works the same way, because the timing data comes from `gh` JSON, not git topology.
   - Test: Task 4 self-test cases.
5. **A vendored skill folder ships executables or network calls.**
   - Expected: every non-`.md` file and every `curl`/`http` line is listed in `VENDORED.md` with a verdict before it goes into the plugin.
   - Test: Task 2 Step 3.

---

### Task 1: Repo scaffold + local marketplace + empty `staff` plugin

**Files:**
- Create: `.gitignore` (`.DS_Store`, `__pycache__/`)
- Create: `.claude-plugin/marketplace.json`: `name: "claude-workflow"`, one plugin `{"name":"staff","source":"./plugins/staff","description":"Staff-AI-engineer workflow: tier router, metrics, vendored skills"}`. Copy the format from `~/.claude/plugins/marketplaces/ponytail/.claude-plugin/marketplace.json`.
- Create: `plugins/staff/.claude-plugin/plugin.json`: `{"name":"staff","version":"0.1.0","description":"...","license":"MIT"}`
- Create: `README.md`. Five lines: what the repo is, `scripts/setup.sh`, and links to the goal, design and plan docs.

**Interfaces:**
- Produces: marketplace name `claude-workflow`; plugin id `staff@claude-workflow`; skills dir `plugins/staff/skills/`.

- [ ] **Step 1:** Write the files above.
- [ ] **Step 2:** Run `claude plugin validate .` and `claude plugin validate plugins/staff`. Expected: both pass. If either fails, fix the JSON and do not continue until both pass.
- [ ] **Step 3:** Commit everything, including the existing `docs/`:

```bash
git add .gitignore .claude-plugin plugins README.md docs
git commit -m "chore: scaffold claude-workflow marketplace and staff plugin"
```

### Task 2: Vendor and review third-party skills

**Files:**
- Create: `plugins/staff/skills/{grill-me,grilling,to-spec,to-tickets,implement,implement-spec,tdd,code-review,handoff,setup-matt-pocock-skills}/`. Each is a full folder copy from Pocock `skills/{productivity,engineering}/<name>/`.
- Create: `plugins/staff/skills/{systematic-debugging,verification-before-completion}/`, copied from superpowers `skills/<name>/`.
- Create: `plugins/staff/licenses/{mattpocock-skills,obra-superpowers}.LICENSE`
- Create: `VENDORED.md`. It contains a table with columns `skill | source repo | SHA | upstream path | reviewed (date) | local edits | non-md files`. Below the table, add a "How to bump" section with the exact clone and checkout commands.

- [ ] **Step 1:** In the scratchpad, run `git clone https://github.com/mattpocock/skills && git -C skills checkout d65391149dbb5fe76478e76fa8d5122b2aa5a70e`. Do the same for `obra/superpowers` @ `22f0b463e7a5e579904dd6211a520321035526f7`.
- [ ] **Step 2:** Copy the 12 skill folders and the two LICENSE files into the paths above.
- [ ] **Step 3: Review every copied file in full.** Then run:

```bash
find plugins/staff/skills -type f ! -name '*.md'
grep -rnE 'curl|wget|https?://|eval|exec' plugins/staff/skills
```

  Record each hit and a verdict in `VENDORED.md`. Hits from prompt-only skills are acceptable. Delete any executable a skill doesn't need, and record the deletion.
- [ ] **Step 4: Fix cross-skill references** so that sibling calls such as `Skill tool with "tdd"`, `"code-review"` and `/setup-matt-pocock-skills` point to `staff:tdd`, `staff:code-review` and `/staff:setup-matt-pocock-skills`. List each edit under "local edits" in `VENDORED.md`. Verify:

```bash
grep -rnE '(Skill tool with|call|run) .?"?/?(tdd|code-review|grilling|to-spec|to-tickets|implement|setup-matt-pocock-skills)\b' plugins/staff/skills | grep -v 'staff:'
```

  Expected: no output.
- [ ] **Step 5:** Run `claude plugin validate plugins/staff` (expected: pass), then `claude plugin details plugins/staff` and note the projected token cost in `VENDORED.md`.
- [ ] **Step 6:** Commit with `feat: vendor pinned Pocock and superpowers skills into staff`.

### Task 3: `/staff:build` tier router

**Files:**
- Create: `plugins/staff/skills/build/SKILL.md`

**Interfaces:**
- Consumes (Task 2): `staff:grill-me`, `staff:to-spec`, `staff:to-tickets`, `staff:implement`, `staff:implement-spec`, `staff:tdd`, `staff:code-review`, `staff:systematic-debugging`, `staff:verification-before-completion`. Also bundled `/code-review`, `/security-review` and `/codex:adversarial-review`.
- Consumes (Task 5): the `## Critical paths` glob list in the project `CLAUDE.md`.
- Produces: `/staff:build <task>`. Stage 2 will replace the step lists inside `standard` and `critical`; the tier names stay.

- [ ] **Step 1:** Write the SKILL.md.
  - Frontmatter: `name: build`, a one-line description, `disable-model-invocation: true`.
  - Body, in order:
    1. **Classify the tier.** Check likely-touched paths against the `## Critical paths` globs in the project CLAUDE.md. If any path matches, the tier is critical. The model may raise a tier, never lower it. `trivial` = one file, no behaviour change, no critical path.
    2. **Bug path.** If the task is a bug, run `staff:systematic-debugging` first. The regression test must fail before the fix.
    3. **trivial:** implement → project test command → `/code-review low`.
    4. **standard:** `staff:to-spec` → `staff:implement` → `staff:verification-before-completion` → open a PR with `gh pr create`.
    5. **critical:** `staff:grill-me` → `staff:to-spec` → `staff:to-tickets` → `staff:implement-spec` → `/code-review high` + `/security-review` + `/codex:adversarial-review` → PR. The PR body has a "Read these hunks" list of diff hunks in critical paths.
    6. **End.** State the tier used and the PR link, then tell the user to run `/staff:log merge --pr <n> --tier <tier>` after merge.
  - If there is no `## Critical paths` section, say so and treat the task as standard.
- [ ] **Step 2:** Verify:
  - `wc -l plugins/staff/skills/build/SKILL.md` is under 80.
  - `claude plugin validate plugins/staff` passes.
- [ ] **Step 3:** Commit with `feat: add /staff:build tier router`.

### Task 4: `/staff:log` metrics

**Files:**
- Create: `plugins/staff/scripts/staff_log.py`. Stdlib only, with a `--self-test` flag.
- Create: `plugins/staff/skills/log/SKILL.md`. User-invoked. It collects `review_min` from the user, then runs the script via `${CLAUDE_PLUGIN_ROOT}/scripts/staff_log.py`.

**Interfaces:**
- Produces, in `staff_log.py`:
  - `lead_time_hours(pr: dict) -> float`. `pr` is the output of `gh pr view N --json number,createdAt,mergedAt,commits`. Start = earliest `commits[].authoredDate`, or `createdAt` if there are no commits. End = `mergedAt`. Raises `ValueError("PR not merged")` when `mergedAt` is null.
  - `append_record(record: dict, path: Path) -> None`. Creates parent dirs and appends one JSON line.
  - CLI `merge --pr N --tier {trivial,standard,critical} --review-min M [--repo-dir .]` → `{"date","repo","pr","tier","lead_time_h","review_min","escaped_defect":false}`. `repo` comes from `gh repo view --json nameWithOwner`.
  - CLI `defect --pr N [--repo-dir .] [--note TEXT]` → `{"date","repo","pr","escaped_defect":true,"note"}`.
  - Exit code: 1 with a message on stderr if `gh` fails or the PR is unmerged. Nothing is appended in that case.

- [ ] **Step 1: Write the self-test cases first**, as asserts under `--self-test`, using fixture dicts:
  - Commits authored 2026-11-20T10:00:00Z and 2026-11-20T12:00:00Z, merged 2026-11-21T10:00:00Z → `24.0`.
  - Zero commits, createdAt 2026-11-20T10:00:00Z, merged 2026-11-20T16:30:00Z → `6.5`.
  - `mergedAt: None` → raises `ValueError`.
  - `append_record` into a temp dir with two records → the file has 2 lines, each valid JSON.
- [ ] **Step 2:** Run `python3 plugins/staff/scripts/staff_log.py --self-test`. Expected: it fails, because the functions don't exist yet.
- [ ] **Step 3:** Implement the functions and the CLI (`argparse` subcommands; `subprocess.run(["gh", ...], check=True)`).
- [ ] **Step 4:** Run `python3 plugins/staff/scripts/staff_log.py --self-test`. Expected: `self-test ok`.
- [ ] **Step 5:** Write `skills/log/SKILL.md` (under 30 lines). Ask for review minutes when they weren't given, run the merge or defect subcommand, and echo the appended line.
- [ ] **Step 6:** Commit with `feat: add /staff:log metrics`.

### Task 5: Python/FastAPI client-repo template

**Files:**
- Create: `templates/python/CLAUDE.md`. At most 120 lines. Based on the knowledge-traceability doc §3, with these changes:
  - Drop `staff gate`/`trace` commands; they're stage 2+.
  - Add a `## Critical paths` section with globs: `app/auth/**`, `app/**/tenancy*`, `alembic/versions/**`, `app/billing/**`, `app/agents/**`, `app/llm/**`, `app/**/prompts/**`, `app/**/tools/**`.
  - Under "How work happens here": `/staff:build`, `/staff:log`, `/staff:handoff`.
- Create: `templates/python/.claude/rules/{api,db,agents,tests}.md`. At most 30 lines each, each with `paths:` frontmatter as listed in design §"Client-repo template". Content comes from KT doc §4 rows, dropping gate references that don't exist yet.
- Create: `templates/python/.claude/settings.json`: `{"permissions":{"ask":["mcp__plugin_firecrawl_firecrawl","mcp__plugin_exa_exa"]}}`. Confirm the exact rule syntax for whole-server MCP matching in the Claude Code permissions docs (`claude-code-guide` agent or Context7).
- Create: `templates/python/README.md`. Setup steps in this order:
  1. Copy the template files.
  2. `uvx library-skills --claude`
  3. Install langchain-skills pinned to a commit. Record the SHA used.
  4. `/staff:setup-matt-pocock-skills` (local-markdown tracker).
  5. Fill in Commands, Map and Critical paths.

- [ ] **Step 1:** Write the files.
- [ ] **Step 2:** Verify:
  - `wc -l` shows CLAUDE.md at most 120 and each rule at most 30.
  - `python3 -m json.tool templates/python/.claude/settings.json` parses.
- [ ] **Step 3:** Commit with `feat: add python/fastapi client-repo template`.

### Task 6: `scripts/setup.sh` (machine settings)

**Files:**
- Create: `scripts/setup.sh` (`#!/bin/zsh`, `set -euo pipefail`)

**Interfaces:**
- Consumes: marketplace from Task 1 (`claude plugin marketplace add "<repo path>"`).

- [ ] **Step 0: Record the baseline before any change.**
  - Try `claude -p "/context"` in a fresh shell in a scratch dir and record the startup token figure. If it fails, ask the user to run `/context` in a fresh session.
  - Record the figure in the design doc under Verification.
  - Save a copy of the current settings: `cp ~/.claude/settings.json "$SCRATCH/settings.before.json"`.
- [ ] **Step 1: Write the script.** In order:
  1. Check prerequisites: `jq`, `claude`, `uv`, `brew`. If `gh` is missing, `brew install gh` and print "run: gh auth login".
  2. Back up `settings.json` with a timestamp.
  3. Apply a single `jq` program that sets `.autoUpdatesChannel="stable"` and `.env.CAVEMAN_DEFAULT_MODE="lite"`, then write it with `mv` from a temp file.
  4. `claude plugin marketplace add "$REPO_ROOT"`, tolerating "already added".
  5. `claude plugin install` for `pyright-lsp@claude-plugins-official`, `pr-review-toolkit@claude-plugins-official` and `staff@claude-workflow`.
  6. `claude plugin disable` for the four plugins listed in Global Constraints, tolerating "already disabled".
  7. claude-mem:
     - Find the setting that disables SessionStart context injection for a project in `~/.claude/plugins/cache/thedotmack/claude-mem/<version>/` (`CLAUDE_MEM_CONTEXT_*` / `CLAUDE_MEM_EXCLUDED_PROJECTS`).
     - Set it in `~/.claude-mem/settings.json` via `jq` for the `claude-workflow` and pilot project names.
     - Set its telemetry decision to declined.
     - Record the exact keys in a comment in the script.
  8. Pin third-party marketplaces: caveman, ponytail, thedotmack, openai-codex and cc-marketplace.
     - Check whether `claude plugin marketplace add` accepts a ref (`owner/repo#<sha>` or a `ref` field). Use the `claude-code-guide` agent or the docs to find out.
     - If it does, re-add each marketplace at its currently installed commit.
     - If it doesn't, append each plugin's installed version to a "Machine plugins" table in `VENDORED.md`.
  9. Print a summary of what changed.
- [ ] **Step 2:** Run `zsh scripts/setup.sh`. Expected: exit 0.
- [ ] **Step 3: Assert the settings.**
  - `jq -e '.autoUpdatesChannel=="stable" and .env.CAVEMAN_DEFAULT_MODE=="lite" and .enabledPlugins["superpowers@claude-plugins-official"]==false and .enabledPlugins["staff@claude-workflow"]==true' ~/.claude/settings.json`. Expected: `true`.
  - Unknown keys are preserved: `diff <(jq -S 'del(.autoUpdatesChannel,.env.CAVEMAN_DEFAULT_MODE,.enabledPlugins)' "$SCRATCH/settings.before.json") <(jq -S 'del(.autoUpdatesChannel,.env.CAVEMAN_DEFAULT_MODE,.enabledPlugins)' ~/.claude/settings.json)`. Expected: no output.
- [ ] **Step 4: Check idempotence.**
  - Run `cp ~/.claude/settings.json "$SCRATCH/after1.json"; zsh scripts/setup.sh; diff "$SCRATCH/after1.json" ~/.claude/settings.json`. Expected: exit 0 and an empty diff.
  - Expected: two backups exist.
- [ ] **Step 5:** Commit with `feat: add idempotent machine setup script`.

### Task 7: Pilot repo

**Files:**
- Create a repo at `~/AI and projects/Projects/staff-pilot/` (separate git repo, outside this one):
  - `uv init`
  - deps: `fastapi`, `sqlalchemy[asyncio]`, `aiosqlite`, `langgraph`, `httpx`, `pytest`, `pytest-asyncio`
  - `app/main.py` with `GET /health` returning `{"status":"ok"}`
  - `tests/test_health.py`
  - template files from Task 5 copied in, with Commands, Map and Critical paths filled in

- [ ] **Step 1:** Write `tests/test_health.py`, which asserts `GET /health` returns 200 and `{"status": "ok"}` via `httpx.AsyncClient(transport=ASGITransport(app))`. Run `uv run pytest -q`. Expected: FAIL (no app).
- [ ] **Step 2:** Implement `app/main.py`. Run `uv run pytest -q`. Expected: `1 passed`.
- [ ] **Step 3:** Follow the setup steps in `templates/python/README.md`:
  - library-skills
  - langchain-skills pinned
  - `/staff:setup-matt-pocock-skills` with the local-markdown tracker
- [ ] **Step 4:** `git init`, commit, then `gh repo create staff-pilot --private --source . --push`. Ask the user before creating the remote, because it is outward-facing.

### Task 8: End-to-end verification

- [ ] **Step 1: Check the fresh session.** In a fresh `claude` session in `staff-pilot`:
  - `/context` startup tokens are lower than the Task 6 Step 0 baseline. Record both numbers in the design doc.
  - The superpowers bootstrap is absent.
  - Caveman reports lite.
  - `/staff:build` is listed.
- [ ] **Step 2: Run a real standard-tier task.** `/staff:build "add POST /items and GET /items/{id} backed by async SQLAlchemy (sqlite), 404 on missing id"`. Expected:
  - tier = standard
  - spec written to the local tracker
  - tests written first
  - Pocock code-review ran
  - PR opened
- [ ] **Step 3: Log the merge.** The user merges, then runs `/staff:log merge --pr 1 --tier standard`. Expected: one line in `~/.local/share/staff/metrics.jsonl` with a numeric `lead_time_h`.
- [ ] **Step 4: Write the friction log.** Add "Stage 1 friction log" to the design doc: where the router was slow, noisy or wrong. This is input for stage 2.
- [ ] **Step 5:** Commit in claude-workflow with `docs: record stage-1 verification results`.
