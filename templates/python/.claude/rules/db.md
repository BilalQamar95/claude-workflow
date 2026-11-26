---
paths:
  - "app/models/**"
  - "app/repositories/**"
  - "alembic/versions/**"
---
# DB rules (SQLAlchemy and Alembic; the money, time, constraint and timeout lines apply to Django ORM too)
- Money is `Decimal` (`Numeric` in the DB), never float. Datetimes are tz-aware UTC.
- Invariants live in DB constraints (unique, check, foreign key, not null), not only in app code.
- Migrations and app connections set `lock_timeout` and `statement_timeout`.
- One session per request. Never share a session across `asyncio.gather` tasks; open one per task.
- Relationships default to `lazy="raise"`. Load with `selectinload`/`joinedload`, and `raiseload("*")` on hot paths.
- Only repositories touch SQLAlchemy. Services own transactions; repositories do not commit.
- Bulk `update()`/`delete()` statements skip ORM events and session state. Expire or refresh afterwards.
- Lock rows with `with_for_update()` in a fixed order to avoid deadlocks. Keep transactions short.
- Never filter tenant_id by hand in handlers. Use the single tenancy mechanism.
- Schema changes need a reviewed Alembic migration: expand, deploy, then contract. Never drop or rename in one step.
- Create indexes with `postgresql_concurrently=True` inside `op.get_context().autocommit_block()`.
- Backfill large data through the queue, not inside the migration.
