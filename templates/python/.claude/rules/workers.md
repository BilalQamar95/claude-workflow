---
paths:
  - "**/tasks.py"
  - "**/workers/**"
  - "**/celery*.py"
---
# Worker and queue rules (Celery or another queue; FastAPI and Django alike)
- Tasks are idempotent: a rerun with the same idempotency key is a no-op. Store the key with the side effect.
- Enqueue only after the DB transaction commits (`transaction.on_commit` in Django, an after-commit hook in SQLAlchemy). Never enqueue inside an open transaction.
- Pass ids and plain values as arguments, never ORM objects. Include the tenant id; the task re-loads and re-scopes by tenant.
- Retries are bounded, with exponential backoff and jitter. Retry only transient errors.
- Set `acks_late=True` for work that must not be lost, together with idempotency.
- Every task has a soft and a hard time limit.
- Poison messages go to a dead-letter queue or a failed state after the last retry, with an alert. Never retry forever.
