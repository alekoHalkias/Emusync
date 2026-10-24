---
name: docs
description: Update EmuSync's documentation (ARCHITECTURE.md, GOTCHAS.md, CLAUDE.md) to stay in sync with code changes. Use when the user runs /docs, after /implement when a PR touches documented modules, or when the user reports that docs are stale.
---

# /docs — keep documentation in sync with code

Follows CLAUDE.md's "Execution approval policy" — updating docs is a normal commit, pre-approved. No need to ask whether to update docs; if code and docs diverge, fix the docs.

## Rules

- No emojis.
- Docs are the source of truth for "what does this module own" — if code moved, docs move with it.
- Never invent behavior that isn't in the code. If a section is unclear, read the code and write what it actually does.
- Keep GOTCHAS.md entries tied to their issue numbers — they exist to explain why something is the way it is.
- CLAUDE.md is a short index and standing rules; push detailed explanations to GOTCHAS.md.

## Files

| File | Purpose | When to update |
|------|---------|----------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module-by-module detail, Key Files table, IPC bridge, component descriptions | Any code change that adds/removes/renames a module, changes a module's responsibilities, adds an IPC channel, changes a component's behavior |
| [docs/GOTCHAS.md](docs/GOTCHAS.md) | Why-things-are-the-way-they-are, with issue numbers | New gotcha-worthy decision, or an existing gotcha's code path changed |
| [CLAUDE.md](CLAUDE.md) | Short index, rules, workflow, gotcha summaries | Rule/policy changes, workflow changes, new gotcha summaries |

## Steps

1. **Determine scope.** If `args` is a PR number or branch, diff against `main` to see what changed:
   ```bash
   gh pr diff <N> --repo alekoHalkias/Emusync
   # or
   git diff main...<branch>
   ```
   If `args` is nothing, check which files were recently changed:
   ```bash
   git log --oneline --since="7 days ago" --name-only | sort -u
   ```

2. **Compare code to docs.** For each changed file, check the Key Files table in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md):
   - Is the file still listed? If not, add it.
   - Does the "Owns" description still match? If the file gained/lost responsibilities, update the description.
   - Are any functions mentioned in the doc still present? If renamed or deleted, update.
   - Are any new functions worth documenting? If they're public API, store methods, or IPC handlers, add them.

3. **Check the IPC bridge.** If any `gui/electron/` module changed, compare against the IPC bridge section in ARCHITECTURE.md:
   - New `ipcMain.handle` → add to the bridge table.
   - Removed channel → delete from the bridge.
   - Changed signature → update.
   - Also check `gui/renderer/src/emusync.d.ts` matches.

4. **Check GOTCHAS.md.** For each changed area, scan GOTCHAS.md for related entries:
   - Is the gotcha still accurate? (code may have evolved)
   - Is the issue number still relevant?
   - Should a new gotcha be added for a decision made in this change?

5. **Check CLAUDE.md.** The "Rules" section summarizes gotchas — if GOTCHAS.md changed, CLAUDE.md's summary likely needs updating too. Also check:
   - Key Files index — does it match ARCHITECTURE.md?
   - Testing section — are the patterns still current?
   - Workflow section — is the issue→plan→implement→ship chain still accurate?

6. **Write the updates.** Edit the files in place. Keep the same style:
   - ARCHITECTURE.md: table for Key Files, code blocks for commands, backtick for file paths.
   - GOTCHAS.md: one paragraph per gotcha, issue number anchor, concrete file:line references.
   - CLAUDE.md: concise, bullet points, no long explanations (push those to GOTCHAS.md).

7. **Commit and push.**
   ```bash
   git add docs/ARCHITECTURE.md docs/GOTCHAS.md CLAUDE.md
   git commit -m "docs: sync documentation with recent code changes"
   git push -u origin <branch>
   ```
   If on `main`, create a `docs/<short-desc>` branch first. Open a PR with a brief summary.

8. **Report.** List which files were updated and what changed in each.
