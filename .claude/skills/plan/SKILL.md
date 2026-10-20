---
name: plan
description: Use when the user runs /plan, or automatically at the end of /issue, on a feature/<issue-number>-* branch whose issue needs an implementation plan before any code is written.

DO NOT MAKE CHANGES TO CODE BEFORE SHOWING PLAN.
---

# /plan — plan the current branch's issue

Follows CLAUDE.md's "Execution approval policy" — read-only commands run automatically, no confirmation needed. The "wait for approval" in step 9 is a deliberate workflow checkpoint on the *plan itself* (per the user's design for this pipeline), not a generic "may I run this command" gate — clarifying questions in step 6 are asked because the answer is genuinely unknown, not to seek permission.

## Steps

1. Get the current branch:
   ```bash
   git branch --show-current
   ```
   Extract the issue number from the `feature/<issue-number>-...` naming convention (CLAUDE.md). If the branch doesn't match that pattern (e.g. `main`, or an unlinked name), ask the user which issue number to plan for — do not guess.

2. Fetch the issue:
   ```bash
   gh issue view <issue-number> --repo alekoHalkias/Emusync --json number,title,body,comments
   ```
   Fallback via curl + `GITHUB_TOKEN` if `gh` is unavailable:
   ```bash
   curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues/<issue-number>"
   curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues/<issue-number>/comments"
   ```

3. Read the issue title, body, and comments in full. Cross-reference CLAUDE.md's Key Files index, docs/ARCHITECTURE.md's per-module detail (read the relevant section, not the whole file), and the actual code (not just the issue text) to find which files, IPC channels, DB tables, or components the work will touch.

4. **Reuse search (required before drafting).** For every piece of new logic the work seems to need, grep for an existing helper, type, IPC handler, CLI subcommand, store method, or component that already does it (or nearly does). Extend or call the existing one rather than writing a parallel copy; CLAUDE.md's gotchas record several times a duplicated implementation drifted apart. The plan must list, per step, what is reused (`path:symbol`) and what is genuinely new, with a one-line reason for each new thing.

5. **Conflict and gotcha checks.**
   - `git fetch --prune && git branch -r`: if another `feature/*` or `copilot/*` branch likely touches the same files, flag it to the user before going further (CLAUDE.md Step 2).
   - Scan CLAUDE.md's "Common gotchas" for entries on the areas this work touches (schema migrations, shared-memcard consoles, folder-vs-file saves, `emusync.toml` vs GUI-only settings, IPC typing in `emusync.d.ts`, etc.) and make the plan comply with each one that applies.
   - If the issue is too large for one reviewable PR, propose a split into separate issues instead of one giant plan.

6. If the issue is ambiguous or leaves a design/config decision open (data shape, UX behavior, naming, which layer owns something, edge-case handling), ask the user targeted clarifying questions before finalizing the plan. Don't ask about things you can resolve by reading the code. Don't ask "should I proceed" once the plan is clear — only ask what's genuinely undecided.

7. Draft the plan in this shape:
   - **Goal:** one sentence, tied to the issue number.
   - **Steps:** ordered; each names the files/modules touched, what is reused vs new (step 4), and the observable result.
   - **Cross-cutting checklist** (state yes/no and where): schema version bump (`schema.py` `_migrate` + `_SCHEMA`); new IPC channel (`preload.ts` + `emusync.d.ts`); new CLI subcommand; config fields or `~/.emusync/` files.
   - **Tests:** per CLAUDE.md's testing requirements (new API route, new Store method, bug-fix regression), naming the test file; no mocks.
   - **Docs:** which of CLAUDE.md / docs/ARCHITECTURE.md need updating and why.
   - **Not in this plan:** adjacent work deliberately left out.
   - **Risks / open questions:** anything unresolved after step 6.

8. Present the plan and stop. Do not edit code yet.

9. Wait for the user's reply.
   - Full approval ("approved", "looks good", "proceed"): invoke the `implement` skill via the Skill tool. Do not ask "should I proceed" again; answers already given in step 6 stand and are not re-asked.
   - Approval with changes ("yes but…"): apply the changes, then invoke `implement` with the revised plan. Re-present first only if the change alters scope, schema, or a public interface.
   - Rejection or requested rework: revise and re-present before invoking `implement`.
