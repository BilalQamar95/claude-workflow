---
name: to-spec
description: "Turn the current conversation into a spec and publish it to the project issue tracker: no interview, just synthesis of what you've already discussed."
disable-model-invocation: true
---

This skill takes the current conversation context and codebase understanding and produces a spec. Do NOT interview the user; just synthesize what you already know.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/staff:setup-matt-pocock-skills`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams match their expectations.

3. Write the spec using the template below, then publish it to the project issue tracker. Apply the `ready-for-agent` triage label - no need for additional triage.

4. Write the draft contract (below) next to the spec, at `.scratch/<feature-slug>/contract.json`. Its `id` is the feature slug: lowercase letters, digits, `.`, `_` or `-`, starting with a letter or digit. It lives in `.scratch/` whatever the tracker, because it is a workflow file and never gets committed. A separate test-author agent writes the tests from it, and the gate locks them before any implementation exists, so the criteria are what "done" means for this task.

<contract-template>

```json
{
  "id": "<feature-slug>",
  "tier": "standard or critical, as the router classified it",
  "goal": "One sentence: what the change achieves for the user.",
  "non_goals": ["What this task deliberately leaves out."],
  "acceptance": [
    {"id": "AC1", "statement": "Observable behaviour, testable from outside.",
     "verify": {"type": "test", "ref": "tests/path/test_file.py::test_name"}},
    {"id": "AC2", "statement": "Something no automated test can show.",
     "verify": {"type": "manual", "reason": "Why it can't be automated, and how the user checks it."}}
  ],
  "invariants": ["What must stay true, such as existing behaviour that must not change."],
  "failure_modes": ["How it can fail, and what it should do then."],
  "slices": [{"id": "S1", "acs": ["AC1"]}],
  "allowed_new_deps": []
}
```

</contract-template>

- One criterion per behaviour, each matching a row of the spec's acceptance table. Prefer `test`; use `manual` only when a test can't show it, because manual criteria end up in the packet as things the user must check. At least one criterion must be a `test`, or there is nothing to lock.
- A `test` ref names a test that doesn't exist yet, with a name that describes the behaviour (it is committed to the client's repo, so no criterion ids or workflow terms), under the repo's test roots (`test_roots` in `.staff-gate.toml`), at the seam agreed in step 2.
- Behaviour that already works before the change is not a criterion: its test would pass at lock, and the lock rejects any criterion whose test doesn't fail first. List it in `invariants` instead; an existing test for it under the test roots is still locked and runs on every `verify`.
- `allowed_new_deps` lists every package the implementation may add. Installing anything else during the task asks the user.
- For a bug, the first criterion is the reported failure, stated as the correct behaviour, so its test reproduces the bug.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Acceptance Criteria

A table with one row per criterion in the draft contract: `ID | Statement | Check (test ref, or manual and why)`. These rows define done for the task, so word each as behaviour a user or caller can observe.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
