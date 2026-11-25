---
paths:
  - "app/api/**"
---
# API rules
- Routers are thin: parse, authorize, call a service. No business logic or SQL here.
- Attach the auth dependency at router level, never per route.
- Split schemas into Create, Update, Read. All use `model_config = ConfigDict(extra="forbid")` for input.
- Every route sets `response_model`. Never return ORM objects.
- One error envelope for all errors: `{"error": {"code", "message"}}`. Raise `HTTPException` or a domain error mapped by a handler.
- Status codes: 201 on create, 204 on delete, 404 for missing or not-yours (never 403 leaking existence), 409 on conflict, 422 from validation.
- Paginate every list endpoint (`limit`, `cursor`). Cap `limit`.
- Inject the DB session with `Depends`; never create sessions inside handlers.
- Async handlers must not call blocking code. Use `run_in_threadpool` or a sync `def` route.
