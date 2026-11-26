# Staff-AI-engineer workflow — goal

Approved 2026-11-25. Inputs: four planning docs kept outside this repo (blueprint, bill of materials, knowledge traceability, ship checklist), treated as suggestions, not a spec.

## Goal (~6 weeks)

1. **Week 1 — daily driver on client work.**
   - One methodology spine; no competing session-start injections.
   - Third-party skills pinned and vetted.
   - Secure defaults.
2. **By week 6 — review by exception.**
   - Standard tier: approve a contract (before) and an evidence packet (after), not the diff.
   - Critical tier: still read the flagged hunks.

**Hedge:** gates are plain scripts plus CI config, so they keep working if the client environment turns out to be restricted. Expectation is that Claude is allowed on client code.

**Measured by** (logged from day 1):
- lead time per task
- escaped defects per PR
- review minutes per PR

## Non-goals

- The 383-item ship checklist upfront.
- Building a tool where an existing one does the job.
- Windows support.
- A self-hosted agent runner.

## Anti-goals

- More time spent on the workflow than on the job.
- A workflow slow or noisy enough that it gets bypassed.

## Stack

Python / FastAPI / SQLAlchemy / LangGraph profile first.

## Home

This repo (`claude-workflow`): a versioned plugin, vendored skills and a setup script, installable on the work machine. Ships in stages; each stage is usable on its own.
