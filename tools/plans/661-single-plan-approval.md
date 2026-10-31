# Plan: #661 Replace per-stage plan approvals with one outline after tplan

Issue: #661
Branch: feature/661-single-plan-approval
PR: none
Status: planned
Fix attempts: 0

## Goal
Remove the approval stop from fplan, bplan and tplan, and have tplan end with one combined outline plus a one-line change summary for a single approval.

## Design Alignment
- **Backend Pattern**: not applicable; edits are to workflow skill markdown only. No backend design guide change.
- **Recommendations**: Store the outline in handoff section 6 (Testing Plan) as `### Outline` and `### Summary`, since tplan owns that section and it already runs last. No new handoff section, so section numbers other skills reference stay stable.

## Steps
- [ ] 1. bplan and fplan step 13: replace "Show the plan to the user and stop. On approval ..." with "Do not stop for approval. Continue to the next stage per the design skill's step 9 (`merge` when both plans exist, else `tplan`)." Fix-plan mode text unchanged.
  - Files: .claude/skills/bplan/SKILL.md, .claude/skills/fplan/SKILL.md
  - Reuses: existing step 13 wording and the design skill step 9 routing
  - New: none
- [ ] 2. tplan step 13: replace the stop with an outline step. Read handoff sections 3-6 and 8; write `### Outline` (one line per step, grouped under Frontend / Backend / Tests, only groups that exist) and `### Summary` (one line stating what the change does) into section 6 of the handoff; commit; show both to the user and stop. On approval invoke `implement`; on requested changes revise the affected plan, recommit, re-present. Add a Log line `tplan: outline written`.
  - Files: .claude/skills/tplan/SKILL.md
  - Reuses: tplan steps 11-12 (handoff update and commit pattern)
  - New: outline/summary instruction - no existing step produces a cross-plan overview
- [ ] 3. merge: reword the end of step 7 so it hands off to `tplan` without presenting the plan for approval (ambiguous-conflict stop at line 16 stays).
  - Files: .claude/skills/merge/SKILL.md
  - Reuses: existing wording
  - New: none
- [ ] 4. issue skill handoff template: add `### Outline: TBD` and `### Summary: TBD` under section 6.
  - Files: .claude/skills/issue/SKILL.md
  - Reuses: existing template block
  - New: none
- [ ] 5. SKILLS_OVERVIEW.md: update fplan/bplan/merge "Next" lines, tplan Output/Next (outline, single approval), the section 6 line in the handoff structure, and the diagram note.
  - Files: .claude/skills/SKILLS_OVERVIEW.md
  - Reuses: existing sections
  - New: none
- [ ] 6. Tests: none - markdown-only workflow change, no code path.
- [ ] 7. Docs: SKILLS_OVERVIEW.md covered in step 5; CLAUDE.md and docs/ARCHITECTURE.md need no change - they do not describe per-stage approvals.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Removing approval from the deprecated `plan` skill.
- Changing fix-plan mode (already approval-free).

## Log
