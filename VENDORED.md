# Vendored third-party skills

Skills under `plugins/staff/skills/` copied from upstream repos at pinned commits. Licenses are in `plugins/staff/licenses/`. Each file was read in full on the review date before being committed.

Sources:
- Pocock: https://github.com/mattpocock/skills @ `d65391149dbb5fe76478e76fa8d5122b2aa5a70e`
- Superpowers: https://github.com/obra/superpowers @ `22f0b463e7a5e579904dd6211a520321035526f7`

| skill | source repo | SHA | upstream path | reviewed | local edits | non-md files | review verdict |
|---|---|---|---|---|---|---|---|
| grill-me | mattpocock/skills | d653911 | skills/productivity/grill-me | 2026-11-25 | SKILL.md: "grilling" -> "staff:grilling" | agents/openai.yaml | Prompt-only, no network or exec. OK. |
| grilling | mattpocock/skills | d653911 | skills/productivity/grilling | 2026-11-25 | none | agents/openai.yaml | Prompt-only, no network or exec. OK. |
| handoff | mattpocock/skills | d653911 | skills/productivity/handoff | 2026-11-25 | none | agents/openai.yaml | Prompt-only; writes a doc to the OS temp dir and says to redact secrets. OK. |
| to-spec | mattpocock/skills | d653911 | skills/engineering/to-spec | 2026-11-25 | SKILL.md: `/setup-matt-pocock-skills` -> `/staff:setup-matt-pocock-skills` | agents/openai.yaml | Prompt-only. Publishes to the project issue tracker, which is its stated job. OK. |
| to-tickets | mattpocock/skills | d653911 | skills/engineering/to-tickets | 2026-11-25 | SKILL.md: `/setup-matt-pocock-skills` -> `/staff:setup-matt-pocock-skills` (2 places) | agents/openai.yaml | Prompt-only. Publishes to the issue tracker, as stated. OK. |
| implement | mattpocock/skills | d653911 | skills/engineering/implement | 2026-11-25 | SKILL.md: "tdd" -> "staff:tdd", "code-review" -> "staff:code-review" | agents/openai.yaml | Prompt-only. Tells the agent to commit to the current branch. OK. |
| implement-spec | mattpocock/skills | d653911 | skills/engineering/implement-spec | 2026-11-25 | SKILL.md: description `/to-spec`, `/to-tickets` -> `/staff:to-spec`, `/staff:to-tickets`; body `/setup-matt-pocock-skills` -> `/staff:setup-matt-pocock-skills`; `tdd` -> `staff:tdd`; `code-review` -> `staff:code-review` | agents/openai.yaml | Prompt-only. Spawns subagents and worktrees by instruction. OK. |
| tdd | mattpocock/skills | d653911 | skills/engineering/tdd | 2026-11-25 | SKILL.md: "the `code-review` skill" -> "the `staff:code-review` skill" | agents/openai.yaml | Prompt-only; mocking.md and tests.md are example prose. OK. |
| code-review | mattpocock/skills | d653911 | skills/engineering/code-review | 2026-11-25 | SKILL.md: `/setup-matt-pocock-skills` -> `/staff:setup-matt-pocock-skills` | agents/openai.yaml | Prompt-only. Runs read-only git diff and rev-parse and spawns subagents. OK. |
| setup-matt-pocock-skills | mattpocock/skills | d653911 | skills/engineering/setup-matt-pocock-skills | 2026-11-25 | none | agents/openai.yaml | Prompt-only plus doc templates. Mentions `gh`/`glab` commands and a GitLab docs URL as text; it can edit CLAUDE.md/AGENTS.md and create labels, but only after user confirmation. OK. |
| systematic-debugging | obra/superpowers | 22f0b46 | skills/systematic-debugging | 2026-11-25 | SKILL.md: `superpowers:verification-before-completion` -> `staff:verification-before-completion`; `superpowers:test-driven-development` -> `staff:tdd` | find-polluter.sh, condition-based-waiting-example.ts | Read both files. find-polluter.sh only runs `find`, `ls` and `npm test <file>` on the cwd, with no network or writes; kept because root-cause-tracing.md refers to it. The .ts is an inert example whose only imports are type-only (`~/threads/...`, not resolvable here). Kept; neither is run automatically. OK. |
| verification-before-completion | obra/superpowers | 22f0b46 | skills/verification-before-completion | 2026-11-25 | none | none | Prompt-only. OK. |

The `agents/openai.yaml` files are Codex UI metadata and are ignored by Claude Code. They were kept unmodified so a folder diff against upstream stays clean. Their `short_description` in implement-spec still says `/to-spec` and `/to-tickets` (not rewritten, since the file is unused).

## Grep review

`find plugins/staff/skills -type f ! -name '*.md'` returns the 2 systematic-debugging files and the 10 openai.yaml files listed above.

`grep -rnE 'curl|wget|https?://|eval|exec' plugins/staff/skills` hits, all benign:
- `condition-based-waiting-example.ts:158`: "execution" in a comment.
- `root-cause-tracing.md:27`: "execution" in prose.
- `root-cause-tracing.md:42,81`: `execFileAsync('git', ['init'])` in example snippets for the debugging write-up.
- `setup-matt-pocock-skills/SKILL.md:45`, `issue-tracker-gitlab.md:3`: link to https://gitlab.com/gitlab-org/cli (docs link for the `glab` CLI).
- `triage-labels.md:7`: "needs-triage" matched "eval" in "evaluate".

No executables were deleted.

## Local edits (summary)

All edits only rewrite references to skills vendored here to the `staff:` form. See the table for the per-file list. No other content was changed. The verification grep from the brief (Step 4) returns nothing.

## Dangling references

References to skills not vendored here. Text is left as upstream wrote it.
- tdd/SKILL.md:26: `Skill tool with "codebase-design"`. Calling it will fail or be ignored; the surrounding text says it is only a vocabulary reference.
- setup-matt-pocock-skills/SKILL.md (lines 29, 53, 113 and others): the `triage` skill. It checks whether `triage` is installed; it is not, so Section B (triage labels) is skipped and triage-labels.md is not used.
- setup-matt-pocock-skills/SKILL.md:40: lists `to-tickets`, `triage`, `to-spec` in prose (not an invocation, left as is).
- setup-matt-pocock-skills/domain.md:11,45: `/domain-modeling`, `/grill-with-docs`, `/improve-codebase-architecture`.
- setup-matt-pocock-skills/issue-tracker-{github,gitlab,local}.md: `/triage`, `/wayfinder`.

## Plugin checks (2026-11-25)

- `claude plugin validate plugins/staff`: passed with one warning (no plugin icon; ICON_MISSING). The warning is directory-submission only.
- `claude --plugin-dir plugins/staff plugin details staff`: 12 skills, 0 agents/hooks/MCP/LSP. Projected always-on cost is ~699 tokens per session. On-invoke costs: systematic-debugging ~3.3k, setup-matt-pocock-skills ~2.6k, code-review ~2.2k, to-tickets ~1.9k, verification-before-completion ~1.2k, tdd ~1.2k, to-spec ~1k, implement-spec ~960, grilling ~660, handoff ~260, implement ~180, grill-me under 20.
- `claude plugin details plugins/staff` does not work because the plugin is not installed; the `--plugin-dir` form above was used.

## How to bump

```bash
mkdir -p /tmp/vendor && cd /tmp/vendor
git clone https://github.com/mattpocock/skills
git -C skills checkout <new-sha>
git clone https://github.com/obra/superpowers
git -C superpowers checkout <new-sha>
```

Then:
1. Diff each upstream folder against `plugins/staff/skills/<name>/` and read every changed file in full.
2. Re-run the greps in the "Grep review" section, and the cross-reference grep for `staff:` references.
3. Re-apply the local edits listed above, update the SHA and reviewed columns, and refresh the dangling-reference list.
4. Run `claude plugin validate plugins/staff` and `claude --plugin-dir plugins/staff plugin details staff`.

## Machine plugins

Third-party marketplace plugins installed on this machine, recorded 2026-11-25 (read from `claude plugin list --json`, `~/.claude/plugins/installed_plugins.json` and `git -C ~/.claude/plugins/marketplaces/<name> rev-parse HEAD`). Re-check on every bump.

| marketplace | plugin | installed version | installed commit | marketplace checkout HEAD | date |
|---|---|---|---|---|---|
| caveman (JuliusBrussee/caveman) | caveman | 14d4f2e21a16 | 14d4f2e21a16b573373ca24698cd6bd3db75bf52 | 14d4f2e21a16b573373ca24698cd6bd3db75bf52 | 2026-11-25 |
| ponytail (DietrichGebert/ponytail) | ponytail | 5.3.3 | ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10 | ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10 | 2026-11-25 |
| thedotmack (thedotmack/claude-mem) | claude-mem | 16.1.5 | 11b47f9f4b8dc3614fab7452647f578886468849 | 11b47f9f4b8dc3614fab7452647f578886468849 | 2026-11-25 |
| openai-codex (openai/codex-plugin-cc) | codex | 1.0.6 | db52e28f4d9ded852ab3942cea316258ae4ef346 | db52e28f4d9ded852ab3942cea316258ae4ef346 | 2026-11-25 |
| cc-marketplace (kenryu42/cc-marketplace) | safety-net | 0.8.2 | a8acf4db1c0d73964b51be6c4c125def2443da5d | ca75085158a57cd620d57385f9560cab936e38fa | 2026-11-25 |

Pinning by SHA is possible via settings `extraKnownMarketplaces.<name>.source.ref` (Claude Code ≥2.1.324); deferred to stage 2 because re-registering uninstalls plugins.
