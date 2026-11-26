# claude-workflow

A local Claude Code marketplace hosting one plugin, `staff`, a staff-AI-engineer workflow.
Run `scripts/setup.sh` to register the marketplace and install the plugin, then run `gh auth login`.
Setup also installs the review and security tools the router uses: claude-security, the Trail of Bits plugins sharp-edges, supply-chain-risk-auditor and insecure-defaults (marketplace pinned to a commit), and gitleaks 8.19+ for the secret scan. Set `STAFF_OUTPUT_STYLE=Explanatory` (or `Learning`) when running it to turn on teach mode for every repo.
Per client repo, run `scripts/stack.sh --dry-run <repo>`, then `scripts/stack.sh <repo>`: it detects the repo's dependencies, offers the matching skills from `stacks/manifest.tsv`, installs the accepted ones at local scope, and git-excludes what it writes. `scripts/stack.sh --self-test` checks its detection and the manifest pins.
Run `scripts/setup.sh` from a dedicated clean clone checked out on `main` (or a tag), and do workflow development in a different clone. The installed `staff` plugin runs from the checkout that setup.sh registered, so whatever branch is checked out there is live in every client session.
Goal: [docs/superpowers/specs/2026-11-25-staff-workflow-goal.md](docs/superpowers/specs/2026-11-25-staff-workflow-goal.md)
Design: [docs/superpowers/specs/2026-11-25-stage1-daily-driver-design.md](docs/superpowers/specs/2026-11-25-stage1-daily-driver-design.md)
Plan: [docs/superpowers/plans/2026-11-25-stage1-daily-driver.md](docs/superpowers/plans/2026-11-25-stage1-daily-driver.md)
