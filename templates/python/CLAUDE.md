# <Project name>

<!-- Fill in every <...>. Keep this file at or under 120 lines. Maintainer notes go in HTML comments. -->

## Commands
- Setup: `uv sync`
- Run: `uv run fastapi dev app/main.py`
- Fast tests: `uv run pytest -q -m "not slow"`
- Lint/format: `uv run ruff check . && uv run ruff format --check .`
- Types: `uv run mypy app`
- Migrations: `uv run alembic revision --autogenerate -m "<msg>"`, then REVIEW it; `uv run alembic check`
- Definition of done: tests, lint and types pass. Nothing else counts as done.

## Map
- `app/api/` routers (thin: parse, authorize, call service) -> `app/services/` (business rules, transactions) -> `app/repositories/` (SQLAlchemy only)
- `app/agents/` LangGraph graphs, `app/llm/` provider clients, `app/workers/` queue tasks
- <Add architecture notes or a link to a doc. Read it before any cross-module change.>

## Invariants
- Auth dependency is attached at router level; routes never opt in individually.
- Every route declares `response_model`; never return ORM objects.
- Tenant isolation is enforced in one place (<RLS or a repository filter>); never hand-filter tenant_id in handlers.
- Relationships default to `lazy="raise"`; load explicitly.
- Every LLM/HTTP call has a timeout; must-happen work goes to the queue, never `BackgroundTasks`.

## Critical paths
<!-- /staff:build treats any task touching a match as critical. Edit to fit this repo. -->
- `app/auth/**`
- `app/**/tenancy*`
- `alembic/versions/**`
- `app/billing/**`
- `app/agents/**`
- `app/llm/**`
- `app/**/prompts/**`
- `app/**/tools/**`

## How work happens here
- Any change: `/staff:build <task>`. It picks the tier (trivial, standard, critical) from the paths above.
- After merge: `/staff:log merge --pr <n> --tier <tier>`.
- Ending or switching context: `/staff:handoff`.
- Path-scoped rules live in `.claude/rules/`. Read the matching rule before creating a new file in that area.

## Gotchas
<!-- Only things no check can catch. -->
- Alembic autogenerate renders column renames as drop+add. Rewrite as `op.alter_column(new_column_name=...)`.
