---
name: log
description: Record a merged PR's lead time and review minutes, or flag an escaped defect, in the local staff metrics file.
argument-hint: "merge --pr <n> --tier <trivial|standard|critical> [--review-min <m>] | defect --pr <n> [--note <text>]"
disable-model-invocation: true
---

Arguments: $ARGUMENTS

Metrics go to `${STAFF_METRICS:-$HOME/.local/share/staff/metrics.jsonl}`, never into a repo.

## merge

Needs `--pr`, `--tier` and `--review-min`. Ask the user for any missing one. For review minutes ask: "How many minutes did you spend reviewing this PR?"

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/staff_log.py" merge --pr <n> --tier <tier> --review-min <m>
```

## defect

Needs `--pr`. Ask for a short note if none was given. Pass it in single quotes, writing any `'` in it as `'\''` (`it's` → `'it'\''s'`).

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/staff_log.py" defect --pr <n> --note '<note>'
```

Run from the project repo (or pass `--repo-dir`). On success, echo the JSON line it prints. On a non-zero exit (gh failed, PR not merged), show the stderr message and tell the user nothing was recorded.
