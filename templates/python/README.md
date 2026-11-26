# Python/FastAPI client-repo template

For FastAPI, SQLAlchemy and LangGraph projects. The rules are FastAPI-flavoured; `workers.md`, `tests.md` and the basics in `db.md` say where they also fit Django. Setup, in order:

1. Copy the template files into the root of the client repo and keep them, and the workflow files, out of its git history. Use `.git/info/exclude`, not `.gitignore`, unless the client team explicitly adopts these files:
   ```bash
   cp -R <this-template-dir>/CLAUDE.md <this-template-dir>/.claude <client-repo>/
   cd <client-repo>
   ex="$(git rev-parse --git-common-dir)/info/exclude"; mkdir -p "$(dirname "$ex")"
   [ -z "$(tail -c1 "$ex" 2>/dev/null)" ] || echo >> "$ex"
   for p in CLAUDE.md .claude/rules/ .claude/settings.json CLAUDE.local.md .scratch/ docs/agents/ GLOSSARY.md GLOSSARY-MAP.md docs/adr/; do grep -sqxF "$p" "$ex" || echo "$p" >> "$ex"; done
   ```
   Exclude only hides untracked files: if the client repo already tracks `CLAUDE.md` or `.claude/`, ask before overwriting. `docs/adr/` and `GLOSSARY.md` are excluded too: if the client repo already tracks its own ADRs or glossary there, tracked files are unaffected, but new hand-written ADRs there won't show in `git status`, so check before excluding.
2. Load this repo's stack skills (FastAPI via library-skills, langchain-skills, Pydantic, Neo4j, Redis, Docker and more, each pinned in `stacks/manifest.tsv`). Install the repo's dependencies first, then preview and run from the workflow checkout:
   ```bash
   <workflow-repo>/scripts/stack.sh --dry-run <client-repo>
   <workflow-repo>/scripts/stack.sh <client-repo>
   ```
   It asks y/N per match (community sources default to N), installs at local scope, and git-excludes everything it writes.
3. To allow Codex reviews in this repo, add the line `Codex review: allowed` to `CLAUDE.local.md`. Without it the router skips Codex.
4. In Claude Code, run `/staff:setup-matt-pocock-skills` and pick the local-markdown tracker. Have it write the `## Agent skills` section into `CLAUDE.local.md` (not `CLAUDE.md`); do not write it by hand.
5. Fill in Commands, Map and Critical paths in `CLAUDE.md`. Keep it at or under 120 lines.

In a git worktree, create the worktree's own virtualenv; do not reuse the main tree's `.venv`, because an editable install there imports main-tree code.

Then start work with `/staff:build <task>`.

Habits:
- Teach mode: `/output-style Explanatory` (or `Learning`) saves `outputStyle` to `.claude/settings.local.json` for this repo only. For every repo, run setup with `STAFF_OUTPUT_STYLE=Explanatory`.
- Pilot: run ten real tasks in a repo before trusting a tier there, then review them with the metrics in `~/.local/share/staff/metrics.jsonl`.
- Untrusted repos (a new client repo, an outside branch): read its `.claude/`, `.mcp.json` and `CLAUDE.md` before accepting the trust prompt. For a first look, start with `claude --bare`, which skips hooks, plugin sync and CLAUDE.md discovery.
- Full scans: before a release and at least quarterly, `/claude-security:claude-security scan this whole repository`. Quarterly, also the cloudflare security-audit skill (not installed by setup).
