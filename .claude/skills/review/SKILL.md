---
name: review
description: Review a PR or code diff against EmuSync's rules (CLAUDE.md), gotchas (docs/GOTCHAS.md), and testing standards. Reports findings ranked by severity. Use when the user runs /review <PR-number|branch|diff>, or after /implement to double-check before ship.
---

# /review — PR / diff review

Reads the diff, checks every change against CLAUDE.md rules and docs/GOTCHAS.md, flags bugs, gotcha violations, missing tests, and stale docs. Reports findings ranked most-severe first.

## Rules

- No emojis anywhere in the report.
- No attribution lines.
- The handoff file is the workflow state carrier. Always read and update it.
- Every finding cites `file:line` from the diff.
- If a finding is already covered by an open issue, note it but still report — the issue may be stale.

## Steps

1. **Load the diff.** If `args` is a PR number:
   ```bash
   gh pr diff <N> --repo alekoHalkias/Emusync
   ```
   If `args` is a branch name:
   ```bash
   git diff main...<branch>
   ```
   If `args` is a commit range or a raw diff text was provided, use that directly.

2. **Read the handoff file** at `plans/<N>-handoff.md` (resolve issue number from the branch name or PR body). If it does not exist, create it using the template from the `issue` skill, filling in what you can from the PR/branch.

3. **Read the rules that apply.** Load [docs/GOTCHAS.md](docs/GOTCHAS.md) and the "Rules" section of [CLAUDE.md](CLAUDE.md). You do not need to read the whole file — jump to the gotcha entries relevant to the files being changed (use the issue-number anchors, e.g. `#490` for shared-memcard, `#460` for baseline, `#478` for envelope, `#535` for config writes, `#539` for console folders, `#564` for paths, `#518` for `%ROM%`, etc.).

4. **Check each changed file against the rules.** Specifically scan for:
   - **Hardcoded paths** — any literal path string that should come from `src/server/paths.py` or `gui/electron/paths.ts` (#564).
   - **Hardcoded console flags** — any new Set or literal list for shared-memcard/shared-state consoles that should read from `console_defs` instead (#490).
   - **Path/typing drift** — new IPC channels missing from `src/gui/renderer/src/emusync.d.ts` (#78); new config fields in `emusync.toml` that should be `display.json` instead (#499).
   - **Blob hashing** — any code hashing `memcard_bytes()` instead of `_memcard_payload_bytes()` (#478).
   - **Schema changes** — new DB columns without a corresponding `_migrate()` block and `_SCHEMA_VERSION` bump (#535).
   - **Config writes** — any `writeFileSync` without atomic `.tmp` + rename + 0600 mode (#535).
   - **Sync baseline logic** — any divergence check that doesn't use `get_save_sync_baseline` (#460).
   - **Launch command** — `%ROM%` token replaced at import time instead of at launch (#518).
   - **Test coverage** — new API route without integration tests; new Store method without a test; bug fix without a regression test. No mocks.

5. **Check docs staleness.** If the diff touches a module documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)'s Key Files table, note whether the doc's description of that file's responsibilities still matches. If it changed significantly, flag the doc for update.

6. **Report findings.** Use `ReportFindings` with the verified findings, most-severe first. Each finding:
   - `file`: repo-relative path
   - `line`: line in the diff / new code
   - `summary`: one-line description
   - `short_summary`: ≤60 chars
   - `failure_scenario`: concrete input/state → wrong output
   - `category`: `correctness`, `gotcha-violation`, `test-gap`, `docs-stale`, `style`

   Also print a human-readable summary in the terminal:
   ```
   ## Review: PR #N / branch <name>

   ### Findings (<N> total)

   | # | Severity | Category | File:Line | Summary |
   |---|----------|----------|-----------|---------|
   | 1 | High     | gotcha-violation | src/server/api/blobs.py:142 | Hashes enveloped bytes instead of payload |
   | 2 | Medium   | test-gap | (none) | New endpoint /games/{slug}/conflicts/check has no integration test |
   ...
   ```

   If zero findings: "No issues found." — still report via `ReportFindings` with an empty array.

7. **Update the handoff file.** Rewrite section 9 (Review) with the findings list, blocked status, and any blockers. Update the Log:
   ```
   - <YYYY-MM-DD> review: <N> findings, blocked=<yes/no>
   ```

8. **On approval ("approved", "lgtm"):** stop. If the user asks for fixes, hand the findings to `implement` for each fixable item.
