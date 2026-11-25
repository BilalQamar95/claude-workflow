# Python/FastAPI client-repo template

For FastAPI, SQLAlchemy and LangGraph projects. Setup, in order:

1. Copy the template files (`CLAUDE.md`, `.claude/`) into the root of the client repo.
2. Install the official FastAPI skill: `uvx library-skills --claude`
3. Install langchain-skills pinned to a commit, never a branch. SHA used: `<record the SHA here>`
4. In Claude Code, run `/staff:setup-matt-pocock-skills` and pick the local-markdown tracker. It writes the `## Agent skills` section; do not write it by hand.
5. Fill in Commands, Map and Critical paths in `CLAUDE.md`. Keep it at or under 120 lines.

Then start work with `/staff:build <task>`.
