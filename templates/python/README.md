# Python/FastAPI client-repo template

For FastAPI, SQLAlchemy and LangGraph projects. The rules are FastAPI-flavoured; `workers.md`, `tests.md` and the basics in `db.md` say where they also fit Django. Setup, in order:

1. Copy the template files into the root of the client repo and keep them, and the workflow files, out of its git history. Use `.git/info/exclude`, not `.gitignore`, unless the client team explicitly adopts these files:
   ```bash
   cp -R <this-template-dir>/CLAUDE.md <this-template-dir>/.claude <this-template-dir>/.staff-gate.toml <client-repo>/
   cd <client-repo>
   ex="$(git rev-parse --git-common-dir)/info/exclude"; mkdir -p "$(dirname "$ex")"
   [ -z "$(tail -c1 "$ex" 2>/dev/null)" ] || echo >> "$ex"
   for p in CLAUDE.md .claude/rules/ .claude/settings.json CLAUDE.local.md .claude/settings.local.json .scratch/ docs/agents/ GLOSSARY.md GLOSSARY-MAP.md docs/adr/ .staff-gate.toml; do grep -sqxF "$p" "$ex" || echo "$p" >> "$ex"; done
   ```
   Exclude only hides untracked files: if the client repo already tracks `CLAUDE.md` or `.claude/`, ask before overwriting. `docs/adr/` and `GLOSSARY.md` are excluded too: if the client repo already tracks its own ADRs or glossary there, tracked files are unaffected, but new hand-written ADRs there won't show in `git status`, so check before excluding.
2. Load this repo's stack skills (FastAPI via library-skills, LangChain/LangGraph/LangSmith skills, Pydantic, Neo4j, Redis, Docker and more, each pinned in `stacks/manifest.tsv`). Install the repo's dependencies first, then preview and run from the workflow checkout:
   ```bash
   <workflow-repo>/scripts/stack.sh --dry-run <client-repo>
   <workflow-repo>/scripts/stack.sh <client-repo>
   ```
   It asks y/N per match (community sources default to N), installs at local scope, and git-excludes everything it writes plus the workflow files `/staff:build` writes. It also offers the Bash sandbox (default yes), limiting shell writes to the repo, temp, the staff state directory and uv's cache, with PyPI and GitHub pre-allowed and other hosts prompting. Run it even with no stack matches: the router stops until those excludes exist.
3. To allow Codex in this repo, do both: add the line `Codex review: allowed` to `CLAUDE.local.md`, and run `claude plugin enable codex@openai-codex --scope local` (writes `.claude/settings.local.json`, excluded in step 1). Setup turns Codex off user-wide because its rescue command and agent can send code to OpenAI on their own; without both, no Codex runs.
4. In Claude Code, run `/staff:setup-matt-pocock-skills` and pick the local-markdown tracker. Have it write the `## Agent skills` section into `CLAUDE.local.md` (not `CLAUDE.md`); do not write it by hand.
5. Fill in Commands, Map and Critical paths in `CLAUDE.md`. Keep it at or under 120 lines.
6. Edit `.staff-gate.toml` to match the Commands section: the test command, and only the format, lint and type tools this repo already uses. `/staff:build` runs its gate with it and stops if the file is missing.

In a git worktree, create the worktree's own virtualenv; do not reuse the main tree's `.venv`, because an editable install there imports main-tree code.

Then start work with `/staff:build <task>`.

Habits:
- Teach mode: `/output-style Explanatory` (or `Learning`) saves `outputStyle` to `.claude/settings.local.json` for this repo only. For every repo, run setup with `STAFF_OUTPUT_STYLE=Explanatory`.
- Caveman: never run `caveman-compress` on `CLAUDE.md` or the rules files. Install caveman at default lite; `--minimal` is not used.
- Pilot: run ten real tasks in a repo before trusting a tier there, then review them with the metrics in `~/.local/share/staff/metrics.jsonl`.
- Untrusted repos (a new client repo, an outside branch): read its `.claude/`, `.mcp.json` and `CLAUDE.md` before accepting the trust prompt. For a first look, start with `claude --bare`, which skips hooks, plugin sync and CLAUDE.md discovery.
- Full scans: before a release and at least quarterly, `/claude-security:claude-security scan this whole repository`. Quarterly, also the cloudflare security-audit skill (not installed by setup).
