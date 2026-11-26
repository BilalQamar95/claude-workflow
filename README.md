# claude-workflow

A local Claude Code marketplace hosting one plugin, `staff`, a staff-AI-engineer workflow.
Run `scripts/setup.sh` to register the marketplace and install the plugin, then run `gh auth login`.
Run `scripts/setup.sh` from a dedicated clean clone checked out on `main` (or a tag), and do workflow development in a different clone. The installed `staff` plugin runs from the checkout that setup.sh registered, so whatever branch is checked out there is live in every client session.
Goal: [docs/superpowers/specs/2026-11-25-staff-workflow-goal.md](docs/superpowers/specs/2026-11-25-staff-workflow-goal.md)
Design: [docs/superpowers/specs/2026-11-25-stage1-daily-driver-design.md](docs/superpowers/specs/2026-11-25-stage1-daily-driver-design.md)
Plan: [docs/superpowers/plans/2026-11-25-stage1-daily-driver.md](docs/superpowers/plans/2026-11-25-stage1-daily-driver.md)
