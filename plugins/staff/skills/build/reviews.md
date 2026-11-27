# Reviews before the PR

Run these after the tier's implement step, on committed work. `<base>` is the default branch. Run the tier's whole list through to the secret scan in one go: a review's report is input for the next step, never the end of your turn, so don't stop to ask whether to continue. Stop only where a step says to ask the user. While a gate task is locked, every such question starts with `NEEDS-INPUT:`, or the Stop hook blocks it.

Fix rounds, at most 2:
1. Round 1: after each review, fix its real findings, rerun the project tests and commit the fixes, then go to the next step.
2. Round 2: once the list is done, if any round-1 fix changed behaviour, rerun the tier's `/code-review` level once on `<base>...HEAD` and fix what it finds.
3. Then stop fixing: list anything still open for the user.

## standard

1. `/simplify` with target `<base>...HEAD`.
2. `/code-review medium` with target `<base>...HEAD`.
3. pr-review-toolkit agents via the Agent tool, each briefed "review only `git diff <base>...HEAD`": `pr-review-toolkit:silent-failure-hunter` and `pr-review-toolkit:pr-test-analyzer`; add `pr-review-toolkit:type-design-analyzer` if types changed and `pr-review-toolkit:comment-analyzer` if comments or docstrings changed.
4. `/security-review`, in a subagent (below).
5. Codex, targeted checks, then the secret scan (below).

## critical

1. `/simplify` with target `<base>...HEAD`.
2. `/code-review xhigh` with target `<base>...HEAD` (the design's `ultra` level no longer exists; `max` only when the user asks).
3. pr-review-toolkit agents, as in standard.
4. `/security-review`, in a subagent (below).
5. `/claude-security:claude-security scan my branch --base <base>`. It scans committed changes only and asks before spending: let it ask. Its `CLAUDE-SECURITY-<timestamp>/` report folder is excluded by `stack.sh` (checked in step 3 of the router); never `git add` it.
6. Codex, targeted checks (also offer `/insecure-defaults:audit`), then the secret scan.

## /security-review

Its prompt makes the report your final reply, which ends the turn. So run it through the Agent tool: a `general-purpose` subagent briefed "Call the Skill tool with `security-review` and return its report verbatim. Change no files." Then fix its findings and carry on with the next step.

## Codex

Codex is off user-wide; a repo enables it with `claude plugin enable codex@openai-codex --scope local` (see the template README). Run only if the project's `CLAUDE.local.md` has the exact line `Codex review: allowed` (the client permits sending code to OpenAI): `grep -sqxF 'Codex review: allowed' CLAUDE.local.md`. Then ask the user to run `/codex:adversarial-review --base <base>` and to tell you when its findings are in. Otherwise print this exact line on its own, not a paraphrase: `codex skipped: not allowed for this repo`

## Targeted checks

Read `git diff --stat <base>...HEAD` and the touched paths. If a named plugin is not installed, say so and skip that check. Then print four lines verbatim, one per check, not merged into prose: `targeted checks: supply-chain <ran|not triggered>`, then the same for `sharp-edges`, `insecure-defaults` and `thermo-nuclear`.

- Dependency manifests or lockfiles touched (`package.json`, `*.lock`, `*-lock.*`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `go.sum`, `Cargo.toml`, `Gemfile`, ...): run the `supply-chain-risk-auditor:supply-chain-risk-auditor` skill. Give it `~/.local/share/staff/supply-chain/<repo>/` as its output dir, never a path in the repo. It queries public package registries and GitHub over the network: if the repo uses a private package index, skip it and ask.
- Settings, config, auth, crypto, deserialization or risky calls touched: run the `sharp-edges:sharp-edges` skill on those files if the diff touches `[tool.*]`, `[build-system]` or `[project.optional-dependencies]` in `pyproject.toml`, `settings.py` or `settings/*.py`, `docker-compose*` or `compose*.y*ml`, `Dockerfile`, `*.ini`, `*.cfg`, `.env.example`, CI workflows, auth or crypto code, or a risky call (shell exec, `eval`, `pickle`, unsafe YAML load, TLS verify off, ...). Any repro code goes under `$TMPDIR`, never in the repo.
- Critical tier, or a new service or config surface: offer `/insecure-defaults:audit <path>`. It runs many agents, so run it only if the user says yes.
- Refactor task, more than 400 changed lines in the diff, any touched file over 1000 lines, or the user asks: run `staff:thermo-nuclear-code-quality-review` on `<base>...HEAD` and the touched files. Report its findings. Restructure beyond the diff only with the user's OK.

## Secret scan

Before any push or PR, if `gitleaks` is on PATH: `gitleaks git --no-banner --redact --log-opts="<base>..HEAD"`. A non-zero exit means findings: stop and show them to the user. Write no report file into the repo. If `gitleaks` is missing, say `gitleaks not installed: secret scan skipped`.
