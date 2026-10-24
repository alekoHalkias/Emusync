---
name: merge
description: Reconcile two plan files (e.g., fplan and bplan) into a single unified plan, resolving file-level conflicts, missing IPC channels, and schema mismatches. Use when two independent plans need to be integrated before implementation.
---

# /merge — fplan/bplan reconciliation

Reads two plan files, identifies conflicts, merges them into a single reconciled plan. This prevents integration hell when two feature branches touch overlapping areas.

## Rules

- No emojis anywhere in the output.
- Professional, plain tone.
- The handoff file is the workflow state carrier. Always read it first; never rely on conversation memory.
- The reconciled plan is the source of truth — no partial merges.
- If a conflict is ambiguous (both plans plausibly correct), flag it for user decision and stop.

## Inputs

Two plan files on the same branch, both with `Status: planned` or `Status: implementing`. Typically produced by `fplan` (frontend-focused) and `bplan` (backend-focused) skills.

## Steps

1. **Read the handoff file** at `plans/<N>-handoff.md`. If it does not exist, create it using the template from the `issue` skill, filling in the Issue and Design sections from the GitHub issue.

2. **Load both plans.** Read the two plan files. Extract:
   - Each plan's steps (with file lists and reuse lists).
   - Each plan's Checklist section (schema bump, IPC channels, CLI subcommands, config changes).
   - The plan's Goal and issue number.

3. **Identify conflicts.** Check for:
   - **Same file touched by both plans:** Both plans edit the same file (even at different line ranges). This is a merge conflict that needs resolution.
   - **IPC channel asymmetry:** One plan defines a new `ipcMain.handle` or `ipcRenderer.invoke` channel, but the other plan doesn't add the corresponding `emusync.d.ts` type or renderer/main handler.
   - **Schema mismatch:** Backend plan adds/changes a DB column, but frontend plan assumes the old schema (e.g., reads a field that no longer exists, or writes to a column that was renamed).
   - **API endpoint mismatch:** Backend plan adds or changes a REST endpoint, but frontend plan (api.ts) doesn't call the new endpoint or uses an old signature.
   - **Config key mismatch:** Backend plan changes a config field name or structure, but frontend plan still reads the old key.
   - **Step ordering conflicts:** Steps from both plans are interleaved in a way that one plan's step depends on the other plan's step running first.

4. **Resolve conflicts.**
   - **Same file, different lines:** Merge the changes into a single step that touches the file. List both plans' objectives in the step description. Combine the Reuses lists.
   - **Same file, same lines:** Flag as ambiguous — both plans modify the same code region. Present both approaches to the user and ask which to keep.
   - **IPC asymmetry:** Add the missing handler/type to the reconciled plan. The backend plan typically owns the channel definition; the frontend plan owns the renderer-side type and invocation.
   - **Schema mismatch:** The backend plan takes priority for schema changes. Update the frontend plan's steps to reference the new schema. If the frontend needs a migration period (old+new schema simultaneously), note it.
   - **API endpoint mismatch:** Same as schema — backend plan takes priority. Update frontend steps to call the new endpoint.
   - **Config key mismatch:** Backend plan takes priority. Update frontend config reads.
   - **Step ordering:** Reorder steps so dependencies come first. Backend changes (schema, API, store) before frontend changes (IPC, UI). Steps that touch the same file go together.

5. **Write the reconciled plan.** Output a single plan file:
   ```
   # Merged Plan: #<N> <issue title>

   Source plans: <fplan-file>, <bplan-file>
   Branch: <branch>
   PR: none
   Status: planned
   Fix attempts: 0

   ## Goal
   <combined goal from both plans>

   ## Steps
   - [ ] 1. <merged step, files, reuses, new-code justification>
   - [ ] 2. ...
   - [ ] N. Tests: <combined test cases from both plans>
   - [ ] N+1. Docs: <combined doc updates>

   ## Checklist
   Schema bump: yes/no. New IPC channel (+ emusync.d.ts): yes/no. New CLI subcommand: yes/no. Config/data file change: yes/no.

   ## Conflicts resolved
   - <file>: <brief description of how the conflict was resolved>
   - <IPC channel>: <added missing handler/type>

   ## Unresolved conflicts
   - <none, or list items that need user decision>

   ## Not in this plan
   ## Log
   ```

6. **Update the handoff file.** Rewrite section 5 (Merged Plan) with the conflicts resolved and unresolved lists. Rewrite section 8 (Implementation Steps) with the merged steps. Update the Metadata section: set `Status: planned`. Append to the Log:
   ```
   - <YYYY-MM-DD> merge: <N> conflicts resolved, <M> unresolved
   ```

7. **Commit and present.**
   ```bash
   git add plans/<N>-*.md
   git commit -m "#<N>: merge reconciled plan from fplan and bplan"
   ```
   Present the reconciled plan to the user, listing all conflicts resolved and any that need user input. On approval, invoke `tplan` with the issue number.
