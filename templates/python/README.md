# Python/FastAPI client-repo template

For FastAPI, SQLAlchemy and LangGraph projects. Setup, in order:

1. Copy the template files into the root of the client repo and keep them, and the workflow files, out of its git history. Use `.git/info/exclude`, not `.gitignore`, unless the client team explicitly adopts these files:
   ```bash
   cp -R <this-template-dir>/CLAUDE.md <this-template-dir>/.claude <client-repo>/
   cd <client-repo>
   printf '%s\n' CLAUDE.md .claude/rules/ .claude/settings.json CLAUDE.local.md .scratch/ docs/agents/ >> "$(git rev-parse --git-common-dir)/info/exclude"
   ```
   Exclude only hides untracked files: if the client repo already tracks `CLAUDE.md` or `.claude/`, ask before overwriting.
2. Install the official FastAPI skill: `uvx library-skills --claude`
3. Install langchain-skills (upstream: `langchain-ai/langchain-skills`) pinned to a commit. The upstream installs from its default branch, so pin through a local checkout used as the marketplace source:
   ```bash
   git clone https://github.com/langchain-ai/langchain-skills ~/.local/share/langchain-skills
   git -C ~/.local/share/langchain-skills checkout 9002566fcf20fb3df65f42da4d316f5643f71c9e
   claude plugin marketplace add ~/.local/share/langchain-skills
   claude plugin install langchain-skills@langchain-skills
   ```
   Pinned SHA: `9002566fcf20fb3df65f42da4d316f5643f71c9e` (upstream HEAD on 2026-11-24). Leave auto-update off. Bump the SHA deliberately.
4. In Claude Code, run `/staff:setup-matt-pocock-skills` and pick the local-markdown tracker. Have it write the `## Agent skills` section into `CLAUDE.local.md` (not `CLAUDE.md`); do not write it by hand.
5. Fill in Commands, Map and Critical paths in `CLAUDE.md`. Keep it at or under 120 lines.

Then start work with `/staff:build <task>`.
