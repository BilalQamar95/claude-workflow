# Reviews before the PR

Run these after the tier's implement step, on committed work. `<base>` is the default branch. Run each review, wait for its result, then fix real findings, rerun the project tests and commit the fixes. At most 2 review→fix rounds per tier: after the second, stop and list what is left for the user.

## standard

1. `/simplify` with target `<base>...HEAD`.
2. `/code-review medium` with target `<base>...HEAD`.
3. `/pr-review-toolkit:review-pr errors tests types comments`. It looks for uncommitted changes and an open PR by itself, so tell it to review `git diff <base>...HEAD`.
4. `/security-review`.
5. Codex, targeted checks, then the secret scan (below).

## critical

1. `/simplify` with target `<base>...HEAD`.
2. `/code-review xhigh` with target `<base>...HEAD` (the design's `ultra` level no longer exists; `max` only when the user asks).
3. `/pr-review-toolkit:review-pr errors tests types comments`, scoped as in standard.
4. `/security-review`.
5. `/claude-security:claude-security scan my branch --base <base>`. It scans committed changes only and asks before spending: let it ask. Its `CLAUDE-SECURITY-<timestamp>/` report folder has its own `.gitignore`; never `git add` it.
6. Codex, targeted checks (also offer `/insecure-defaults:audit`), then the secret scan.

## Codex

Run only if the project's `CLAUDE.local.md` has the exact line `Codex review: allowed` (the client permits sending code to OpenAI): `grep -sqxF 'Codex review: allowed' CLAUDE.local.md`. Then ask the user to run `/codex:adversarial-review --base <base>` and to tell you when its findings are in. Otherwise print `codex skipped: not allowed for this repo`.

## Targeted checks

Read `git diff --stat <base>...HEAD` and the touched paths. If a named plugin is not installed, say so and skip that check.

- Dependency manifests or lockfiles touched (`package.json`, `*.lock`, `*-lock.*`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `go.sum`, `Cargo.toml`, `Gemfile`, ...): run the `supply-chain-risk-auditor:supply-chain-risk-auditor` skill. Give it `~/.local/share/staff/supply-chain/<repo>/` as its output dir, never a path in the repo. It queries package registries over the network.
- Settings, config, auth, crypto, deserialization or risky calls touched (shell exec, `eval`, `pickle`, unsafe YAML load, TLS verify off, ...): run the `sharp-edges:sharp-edges` skill on those files.
- Critical tier, or a new service or config surface: offer `/insecure-defaults:audit <path>`. It runs many agents, so run it only if the user says yes.
- Refactor task, more than 400 changed lines in the diff, any touched file over 1000 lines, or the user asks: run `staff:thermo-nuclear-code-quality-review` on `<base>...HEAD` and the touched files. Report its findings. Restructure beyond the diff only with the user's OK.

## Secret scan

Before any push or PR, if `gitleaks` is on PATH: `gitleaks git --no-banner --redact --log-opts="<base>..HEAD"`. A non-zero exit means findings: stop and show them to the user. Write no report file into the repo. If `gitleaks` is missing, say `gitleaks not installed: secret scan skipped`.
