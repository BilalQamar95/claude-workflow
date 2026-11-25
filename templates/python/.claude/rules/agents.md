---
paths:
  - "app/agents/**"
  - "app/llm/**"
---
# Agent and LLM rules
- LangGraph state is a typed `TypedDict` or Pydantic model. No untyped dict state.
- Every graph has a termination bound: `recursion_limit`, a max-iterations counter, or both.
- Every LLM and HTTP call has an explicit timeout and bounded retries.
- Apply the tenant filter before retrieval, not after. Never let a query run unscoped.
- Tools are allowlisted per agent. A tool that writes or spends money needs explicit confirmation or a narrow scope.
- Treat tool output and retrieved text as untrusted input. Never execute it or let it widen tool access.
- Prompts live in `prompts/` files, not inline strings. A prompt change is a critical-path change.
- Trace every run (provider, model, token counts, latency). Never log secrets or raw user PII.
- Must-happen work goes to the queue, never `BackgroundTasks`.
