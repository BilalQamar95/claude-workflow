# Stage 1 — week-1 daily driver: design

Status: approved 2026-11-25 · Pilot repo: AgencyOS (Django/DRF/Celery/LangGraph), worked in a git worktree; the new FastAPI pilot repo was dropped · Goal: [2026-11-25-staff-workflow-goal.md](2026-11-25-staff-workflow-goal.md)

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
- The cloudflare security audit and Graphify. Each gets added when a stage or repo needs it. (Trail of Bits plugins, claude-security and gitleaks moved into stage 1 with the review steps; see Plugin set.)
- The Claude Code sandbox (`sandbox.enabled`, audit W9). User decision 2026-11-26: it moves to stage 2, with the gate, so network and out-of-project writes are enforced together with the other gate checks.
- The BOM's baseline A/B fixture repo. Real-task metrics replace it for now.
- The 383-item ship checklist. It is adopted incrementally per stage, not up front. Stage 2 owns the review-relevant subset, scoped by tags and fed into the review workflow; later stages take the rest.

Deferred to stage 2 from the 2026-11-26 doc audit, so none of it is dropped silently:

- S1 `/staff:learn` loop (regression test, then a hookify, semgrep or ruff rule with a proof test, a rules line last): it needs the gate to land rules into.
- S2 agentic production-failure skill and the six-question workflow-vs-agent rule: custom knowledge, written after the pilot shows which failures recur.
- S3 eval scaffolding for LLM behaviour changes: the langchain `langchain-eval-engineering` skill, DeepEval and the langfuse skill are installable per repo through `stacks/manifest.tsv`; wiring them into the gate is stage 2.
- S4 PostToolUse ruff format and check hook: only safe when the repo has its own ruff config, which the gate's `quality.toml` will say.
- S5 `/staff:init` interview (the D-list and A-list defaults): the template README is filled in by hand until then.
- S6 ADRs and glossary (Pocock `domain-modeling`, `grill-with-docs`): vendored with the contract work that consumes them.
- S7 plugin evals: low value while every staff-authored skill is user-invoked.
- S8 CI for this repo (`claude plugin validate --strict`, the self-tests): about 15 lines of YAML, once the plugin changes less often.
- S9 automated re-scan of vendored skills in CI: comes with S8.
- S10 `plugin-dev` toolkit: needed once hooks and agents are built.
- S11 hook latency: measure once with `--debug` hook timings when the gate adds hooks.
- Stage 1a critic panel (BP:74-78): a panel of critic agents over the contract and review output; it belongs with the review workflow and verifier.
- W24 caveman `--minimal` install: not built; caveman stays at default lite (setup merges the lite setting).

Skipped from the same audit, with the reason:

- K1 BOM "skip ponytail's band": band is local-only (`~/.config/ponytail/band/`), so the BOM's concern does not apply and its ledger is used for cost.
- K2 bundled `/verify`: not in this install; `verification-before-completion` covers it.
- K3 security-guidance as a plugin.json dependency: it is already enabled user-wide.
- K4 lint, type, layering config and git conventions: the client owns these in client repos, and writing them would put workflow config in client PRs; own repos get them in stage 2 through `quality.toml`.
- K5 Pocock `writing-for-agents`, `prototype`, `research`: skill-creator and claude-md-management cover writing, exa, firecrawl and context7 cover research, and nothing needs prototype yet.
- W24 "never run `caveman-compress` on CLAUDE.md or rules": built as a habit line in the template README, not enforced by a hook (a hook belongs with the gate).
- K6 observability standards (health and readiness, OTel, dashboards): product decisions per client that belong to the ship checklist.

## Anti-goals

- Week 1 eats the job: stage 1 must be buildable in about one focused session.
- A router that adds ceremony to trivial tasks.

## Constraints

- macOS (zsh). The docs' Windows assumptions are dropped.
- User-global settings live in `~/.claude/settings.json`. Edit it with `jq`, take a timestamped backup first, and never overwrite it blindly.
- Auto permission mode stays as the user configured it.
- Client code may later run in a restricted environment. Nothing in stage 1 may depend on a hosted service beyond Anthropic and GitHub.
- Licences: Pocock is MIT and superpowers is MIT. Vendored copies keep their LICENSE file.
- Nothing workflow-internal is committed to or published in a client repo: workflow files are listed in `.git/info/exclude`, PR bodies stay client-facing.

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
scripts/stack.sh                       per-repo stack skills at local scope (has --dry-run and --self-test)
stacks/manifest.tsv                    dependency pattern -> pinned skill or plugin source
templates/python/                      CLAUDE.md, .claude/rules/{api,db,agents,tests,workers}.md, .claude/settings.json
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
- **standard:** `to-spec` (local-markdown tracker only; the GitHub tracker was dropped) → `implement` (uses `tdd` + Pocock `code-review`) → `verification-before-completion` → PR.
- **critical:** `grill-me` → `to-spec` → `to-tickets` → `implement-spec` → critical reviews → PR. The hunk list in critical paths is printed to the terminal, never put in the PR.
- **Reviews** (`build/reviews.md`, on committed work, at most 2 review→fix rounds per tier, then the rest is listed):
  - Standard: `/simplify`, `/code-review medium`, the pr-review-toolkit agents (silent-failure-hunter and pr-test-analyzer always, type-design-analyzer and comment-analyzer when types or comments changed) invoked directly on `git diff <base>...HEAD`, `/security-review`, the gated Codex review, targeted Trail of Bits checks, and the gitleaks secret scan (`gitleaks git --no-banner --redact --log-opts="<base>..HEAD"`, gitleaks 8.19+).
  - Critical: the same with `/code-review xhigh` (the blueprint's "ultra" level no longer exists), plus `/claude-security:claude-security scan my branch --base <base>`, and `/insecure-defaults:audit` offered.
  - Codex is off user-wide, because its rescue command and agent are model-invocable and would send code to OpenAI. A repo enables it with `claude plugin enable codex@openai-codex --scope local` together with the line `Codex review: allowed` in `CLAUDE.local.md`; the router runs the Codex review only with that line.
  - Trail of Bits triggers: `supply-chain-risk-auditor` when a manifest or lockfile changes, `sharp-edges` when settings, config, auth, crypto, deserialization or risky calls change. `staff:thermo-nuclear-code-quality-review` runs on a refactor, more than 400 changed lines, a touched file over 1000 lines, or on request.
  - supply-chain-risk-auditor sends dependency names to public package registries and advisory databases. Accepted: it is the same exposure as `pip install`. Its output goes to `~/.local/share/staff/supply-chain/<repo>/`, outside the client repo.
- **Bugs:** `systematic-debugging` first. The regression test must fail before the fix.
- **End of every tier:** remind the user to run `/staff:log` after merge.

Stage 2 changes `standard` and `critical` to: contract → locked tests → implement → gate → review → evidence. That replaces steps inside the router without changing how the user calls it.

### Plugin set (user-global)

| Action | Plugins |
|---|---|
| Keep enabled | ponytail, caveman (default lite), claude-mem (inbox mode), security-guidance, code-review, context7, skill-creator, claude-md-management, safety-net, firecrawl, exa |
| Disable (stay installed) | superpowers, impeccable, playwright, frontend-design |
| Disable user-wide (stay installed) | `qdrant@synced`, `langfuse@synced` (`scripts/stack.sh` enables them per repo at local scope); `codex@openai-codex` (enabled per repo at local scope, only together with the `Codex review: allowed` marker) |
| Install + enable | `pyright-lsp`, `pr-review-toolkit`, `claude-security` (official marketplace); `sharp-edges`, `supply-chain-risk-auditor`, `insecure-defaults` (`trailofbits` marketplace pinned to `149d7b21f4067765b82e67029730b42d228ef4b4`); `staff` 0.3.0, 16 skills (this repo's local marketplace) |
| Install (binary) | gitleaks 8.19+: Homebrew when it has a bottle for this macOS, otherwise the pinned release tarball, sha256-checked, into `~/.local/bin` |

Notes:
- safety-net covers destructive-command blocking, so dcg is skipped.
- frontend-design is parked with the Next.js phase.
- Stack skills are per repo, not user-wide: `scripts/stack.sh <repo>` maps the repo's dependencies through `stacks/manifest.tsv` (every source pinned to a commit) and installs what the user accepts at local scope, git-excluded. It installs no MCP server; any listed one is manual, with its read-only flag.

### Settings changes (`~/.claude/settings.json`, via `jq`, with backup)

- `autoUpdatesChannel`: `latest` → `stable`.
- `env.CAVEMAN_DEFAULT_MODE = "lite"`.
- claude-mem startup injection is off globally: `CLAUDE_MEM_CONTEXT_OBSERVATIONS="0"`, `CLAUDE_MEM_CONTEXT_SESSION_COUNT="0"`, `CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY="false"`. Capture stays on. `telemetry.json` has `enabled=false`.
- `env.DISABLE_TELEMETRY="1"` and `env.DISABLE_ERROR_REPORTING="1"`.
- `env.DO_NOT_TRACK="1"` for third-party CLIs that honour it (claude-security, the skills CLI). `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is not set: it also turns off auto-updates and the plugin auto-update pass, which would stop `stable` updates and synced plugins.
- `env.CLAUDE_SECURITY_SCAN_TIP="off"`: the router decides when claude-security scans.
- `permissions.deny` merged (existing entries kept): `Read(**/.env)`, `Read(**/.env.*)`, `Read(**/*.pem)`, `Read(**/*.key)`, `Read(~/.ssh/**)`, `Read(~/.aws/**)`. A Read deny also blocks Edit and Write on the path.
- `outputStyle` set from `STAFF_OUTPUT_STYLE` when that variable is set at setup (teach mode, e.g. `Explanatory` or `Learning`); otherwise unchanged.
- `extraKnownMarketplaces.<name>.autoUpdate = false` for every third-party marketplace declared in settings. Setup prints which marketplaces still auto-update, and whether an advisor model is configured (read only).
- `setup.sh` also installs the Karpathy CLAUDE.md to `~/.claude/CLAUDE.md` (pinned SHA and sha256), only if the file is missing, and warns if an existing one differs.
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
  - `workers` (`**/tasks.py`, `**/workers/**`, `**/celery*.py`)

  Content is taken from the knowledge-traceability doc §4.
- **`.claude/settings.json`:** `permissions.ask` for firecrawl and exa MCP tools.
- **Setup steps in the template README:**
  - `scripts/stack.sh <repo>`, which covers the FastAPI skill (library-skills), the cherry-picked LangChain/LangGraph/LangSmith skills (no plugin, no docs MCPs) and the other stack skills, pinned.
  - The Codex opt-in line, teach mode, the ten-task pilot, untrusted-repo and full-scan habits.
  - `/setup-matt-pocock-skills` with the local-markdown tracker by default.

### Metrics

- **Location:** `~/.local/share/staff/metrics.jsonl`. This is outside any repo, so nothing leaks into client code.
- **`/staff:log` at merge appends:** `{date, repo, pr, tier, lead_time_h, review_min, escaped_defect: false}`.
  - `lead_time_h` is computed from git: first branch commit → merge.
  - `review_min` is asked from the user.
- **`/staff:log defect --pr <n>`** marks an escaped defect against the PR that introduced it.
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

1. `claude plugin validate --strict plugins/staff` passes.
2. `staff_log.py` self-test passes (`python3 plugins/staff/scripts/staff_log.py --self-test`).
3. In a fresh session, compare `/context` startup tokens with the pre-change number, recorded in this doc. The user agrees the budget is acceptable.
   - Pre-change baseline (2026-11-25, `claude -p "/context"` in an empty scratch dir, before `setup.sh`): 22k / 300k. Skills 10k, MCP server instructions 3.1k, system prompt 1.9k, custom agents 1.4k, memory files 875, MCP tools 671, messages 4k (deferred tools not counted in the 22k). Measured outside a project repo, so it excludes claude-mem's per-project injection there.
   - Post-change: 21.5k / 300k in a neutral dir (vs the 22k baseline), and 27.5k in AgencyOS (includes its own CLAUDE.md). User sign-off: accepted 2026-11-26.
4. `/staff:build` appears and superpowers' bootstrap no longer injects. Caveman starts at lite.
5. One real task runs end to end on the pilot repo through the standard tier, and a `/staff:log` line lands.
   - Waived by the user on 2026-11-26. The AgencyOS pilot ran the critical tier end to end (stopped before push); there was no merge and no `/staff:log` line. The first real client task after `gh auth login` closes this check.
6. `setup.sh` re-runs cleanly (idempotent) and leaves a backup of settings.json.
7. `scripts/stack.sh --self-test` passes, and `scripts/stack.sh --dry-run <repo>` lists the expected stack rows without writing anything.
8. Pilot: after ten real tasks on a repo, review its `metrics.jsonl` lines before trusting a tier there.
