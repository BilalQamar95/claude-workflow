# Stage 1 — week-1 daily driver: design

Status: approved 2026-11-25 · Pilot repo: new small FastAPI + SQLAlchemy + LangGraph repo scaffolded from `templates/python/` (also the stage-2 gate testbed) · Goal: [2026-11-25-staff-workflow-goal.md](2026-11-25-staff-workflow-goal.md)

## Intent

Make Claude Code a dependable daily driver for client work in week 1. Later stages (contract, locked tests, gate, evidence packet) need a home to plug into, and this stage builds it. Value comes from removing friction and conflicts, not from building machinery.

## Goals

1. One spine: a thin `/staff:build` router over vendored Pocock primitives. Superpowers is disabled.
2. No competing session-start injections. Startup context is measured before and after.
3. Every third-party skill is pinned and has been read. Plugin updates go through `stable`, not `latest`.
4. Secure defaults: no telemetry leaves the machine, and web-scraping tools need approval before use on client repos.
5. Metrics are logged from day 1: lead time, review minutes and escaped defects. Ponytail's existing local ledger covers agent cost and time.
6. A Python/FastAPI/LangGraph project template: CLAUDE.md, path-scoped rules, and library skills.

## Non-goals (this stage)

- Contract, locked tests, `staff-gate`, evidence packet, review workflow with verifier. Those are stage 2+.
- hookify rule pack and semgrep rules. They come with the gate.
- `.ai/` knowledge base, trace tooling, `doctor`.
- Trail of Bits skills, claude-security, the cloudflare audit, Graphify. Each gets added when a stage or repo needs it.
- The BOM's baseline A/B fixture repo. Real-task metrics replace it for now.

## Anti-goals

- Week 1 eats the job: stage 1 must be buildable in about one focused session.
- A router that adds ceremony to trivial tasks.

## Constraints

- macOS (zsh). The docs' Windows assumptions are dropped.
- User-global settings live in `~/.claude/settings.json`. Edit it with `jq`, take a timestamped backup first, and never overwrite it blindly.
- Auto permission mode stays as the user configured it.
- Client code may later run in a restricted environment. Nothing in stage 1 may depend on a hosted service beyond Anthropic and GitHub.
- Licences: Pocock is MIT and superpowers is MIT. Vendored copies keep their LICENSE file.

## Approaches considered (spine)

| Option | Trade-off | Verdict |
|---|---|---|
| A. Keep superpowers | Coherent and already installed, but its SessionStart bootstrap forces brainstorm, plan and subagents on every task. Stage-2 gates would have to bolt onto a flow we don't own. | Rejected |
| B. Pocock primitives only | Low ceremony, but nothing routes by risk, and the stage-2 gates have no orchestrator to attach to. | Rejected |
| **C. Thin `staff` orchestrator over Pocock** | We own a small router, and it is the slot where stage-2 gates go. Superpowers is disabled, but two of its skills are vendored. | **Chosen by user** |

## Design

### Repo layout (`claude-workflow`)

```
.claude-plugin/marketplace.json        local marketplace exposing plugins/staff
plugins/staff/
  .claude-plugin/plugin.json
  skills/
    build/SKILL.md                     tier router (user-invoked only)
    log/SKILL.md                       metrics entry at merge / on escaped defect
    <vendored skills>/                 see "Vendored skills"
  scripts/staff_log.py                 appends metrics JSONL; has an assert self-test
VENDORED.md                            per skill: source repo, commit SHA, path, review date, local edits
scripts/setup.sh                       idempotent machine setup (settings merge, plugin toggles, checks)
templates/python/                      CLAUDE.md, .claude/rules/{api,db,agents,tests}.md, .claude/settings.json
docs/                                  existing docs + specs
```

### Vendored skills (pinned at a reviewed commit)

- **From mattpocock/skills:** `grill-me`, `grilling`, `to-spec`, `to-tickets`, `implement`, `implement-spec`, `tdd`, `code-review`, `handoff`, `setup-matt-pocock-skills`.
- **From obra/superpowers:** `systematic-debugging`, `verification-before-completion`.
- **Rules:**
  - Copy each skill as-is and record it in `VENDORED.md`.
  - If a local edit is needed, for example to fix a cross-skill reference, keep it minimal and list it in `VENDORED.md`.
  - Bumping a skill means re-reading the upstream diff first.
- **Not vendored, with reasons:**
  - Pocock `diagnosing-bugs` overlaps `systematic-debugging`; one is enough.
  - `wayfinder` and `software-factory` are in-progress and too large; revisit at stage 3.
  - `triage` needs label setup that isn't worth doing yet.

### `/staff:build` router

`disable-model-invocation: true`. It takes a task description and picks a tier.

- **Critical paths:** the router checks paths the task will touch against the `## Critical paths` globs in the project CLAUDE.md. The model may raise the tier but never lower it.
- **trivial:** one file, no behaviour change, no critical path. Implement → run tests → bundled `/code-review low`.
- **standard:** `to-spec` (local-markdown tracker, or GitHub if set up) → `implement` (uses `tdd` + Pocock `code-review`) → `verification-before-completion` → PR.
- **critical:** `grill-me` → `to-spec` → `to-tickets` → `implement-spec` → bundled `/code-review high` + `/security-review` + `/codex:adversarial-review` → PR. The packet lists the hunks in critical paths for the user to read.
- **Bugs:** `systematic-debugging` first. The regression test must fail before the fix.
- **End of every tier:** remind the user to run `/staff:log` after merge.

Stage 2 changes `standard` and `critical` to: contract → locked tests → implement → gate → review → evidence. That replaces steps inside the router without changing how the user calls it.

### Plugin set (user-global)

| Action | Plugins |
|---|---|
| Keep enabled | ponytail, caveman (default lite), claude-mem (inbox mode), security-guidance, code-review, codex, context7, skill-creator, claude-md-management, safety-net, firecrawl, exa |
| Disable (stay installed) | superpowers, impeccable, playwright, frontend-design |
| Install + enable | `pyright-lsp`, `pr-review-toolkit` (official marketplace), `staff` (this repo's local marketplace) |

Notes:
- safety-net covers destructive-command blocking, so dcg is skipped.
- frontend-design is parked with the Next.js phase.

### Settings changes (`~/.claude/settings.json`, via `jq`, with backup)

- `autoUpdatesChannel`: `latest` → `stable`.
- `env.CAVEMAN_DEFAULT_MODE = "lite"`.
- claude-mem startup injection: off for workflow-managed repos, using its `CLAUDE_MEM_*` context/exclusion settings. The builder checks the exact key in claude-mem 16.1.5. Telemetry consent is set to declined.
- `enabledPlugins` updated as in the table above.
- Third-party marketplaces (caveman, ponytail, claude-mem, codex) are pinned to a commit if the marketplace source supports a ref. If not, record the installed version in `VENDORED.md` and re-check on bump.

### Client-repo template (`templates/python/`)

- **`CLAUDE.md`:**
  - At most 120 lines.
  - Sections: commands, map, invariants, `## Critical paths` globs (auth, tenancy, migrations, money, prompts/agent tools), gotchas.
  - First line is `@AGENTS.md` only if the repo serves other agents.
- **`.claude/rules/*.md`:** path-scoped, at most 30 lines each:
  - `api` (`app/api/**`)
  - `db` (models/repositories)
  - `agents` (`app/agents/**`, `app/llm/**`)
  - `tests` (`tests/**`)

  Content is taken from the knowledge-traceability doc §4.
- **`.claude/settings.json`:** `permissions.ask` for firecrawl and exa MCP tools.
- **Setup steps in the template README:**
  - `uvx library-skills --claude`, for the official FastAPI skill.
  - langchain-skills installed pinned.
  - `/setup-matt-pocock-skills` with the local-markdown tracker by default.

### Metrics

- **Location:** `~/.local/share/staff/metrics.jsonl`. This is outside any repo, so nothing leaks into client code.
- **`/staff:log` at merge appends:** `{date, repo, pr, tier, lead_time_h, review_min, escaped_defect: false}`.
  - `lead_time_h` is computed from git: first branch commit → merge.
  - `review_min` is asked from the user.
- **`/staff:log --defect <pr>`** marks an escaped defect against the PR that introduced it.
- **Agent cost, turns and minutes per session:** already in ponytail's local ledger (`~/.config/ponytail/band/<project>.csv`). We reuse it rather than duplicating it.

### Machine prerequisites

- `gh` CLI (missing today). Install with Homebrew; the user runs `gh auth login` interactively.
- `uv` for templates (verify present).

## Left to the builder (my calls, marked)

- Exact claude-mem setting key for disabling injection (verify in plugin source).
- Whether the marketplace source accepts a commit ref.
- How vendored skills resolve cross-skill calls under the `staff:` namespace (e.g. `implement` calls "tdd"). Fix with minimal edits recorded in `VENDORED.md` if needed.
- Wording of the router skill. It must stay short: target under 80 lines.

## Verification

1. `claude plugin validate` passes for `plugins/staff`.
2. `staff_log.py` self-test passes (`python3 plugins/staff/scripts/staff_log.py --self-test`).
3. In a fresh session, compare `/context` startup tokens with the pre-change number, recorded in this doc. The user agrees the budget is acceptable.
4. `/staff:build` appears and superpowers' bootstrap no longer injects. Caveman starts at lite.
5. One real task runs end to end on the pilot repo through the standard tier, and a `/staff:log` line lands.
6. `setup.sh` re-runs cleanly (idempotent) and leaves a backup of settings.json.
