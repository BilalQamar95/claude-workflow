---
paths:
  - "app/models/**"
  - "app/repositories/**"
  - "alembic/versions/**"
---
# DB rules
- One session per request. Never share a session across `asyncio.gather` tasks; open one per task.
- Relationships default to `lazy="raise"`. Load with `selectinload`/`joinedload`, and `raiseload("*")` on hot paths.
- Only repositories touch SQLAlchemy. Services own transactions; repositories do not commit.
- Bulk `update()`/`delete()` statements skip ORM events and session state. Expire or refresh afterwards.
- Lock rows with `with_for_update()` in a fixed order to avoid deadlocks. Keep transactions short.
- Never filter tenant_id by hand in handlers. Use the single tenancy mechanism.
- Schema changes need a reviewed Alembic migration: expand, deploy, then contract. Never drop or rename in one step.
- Create indexes with `postgresql_concurrently=True` inside `op.get_context().autocommit_block()`.
- Backfill large data through the queue, not inside the migration.
