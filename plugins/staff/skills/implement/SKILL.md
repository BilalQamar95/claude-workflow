---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

Call the Skill tool with "staff:tdd" where possible, at pre-agreed seams.

If the task has locked acceptance tests (the build router's standard and critical tiers), they are the red tests to turn green: make them pass, using `staff:tdd` for the units beneath them. Every file under the test roots at lock time is locked, so put new tests in new files. Never edit a locked file; if a locked test is wrong, follow the router's dispute rule.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "staff:code-review" to review the work.

Commit your work to the current branch.
