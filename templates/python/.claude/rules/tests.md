---
paths:
  - "tests/**"
---
# Test rules
- Test through the public interface. Do not mock the unit under test; mock only external boundaries (LLM, HTTP, clock).
- API tests use `httpx.AsyncClient(transport=ASGITransport(app=app))`.
- Use a real Postgres via testcontainers, not SQLite, for anything touching models or queries.
- Each test sets up its own data and cleans up. No order dependence.
- A bug fix starts with a test that fails first, then the fix.
- Mark slow tests `@pytest.mark.slow` so the fast suite stays fast.
- Do not edit or weaken an existing test to make it pass. If a test is wrong, say why in the PR.
- LLM calls in tests use recorded or fake responses. Never hit a live provider.
