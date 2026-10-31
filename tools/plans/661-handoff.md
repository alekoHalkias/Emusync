# Handoff: #661 Replace per-stage plan approvals with one outline after tplan

## Metadata
- Issue: #661
- Branch: feature/661-single-plan-approval
- PR: none
- Status: shipped
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
fplan, bplan and tplan each stop for user approval. Remove those pauses and present one combined outline after tplan.
### Motivation
Three approval stops interrupt the flow and show partial plans; one review point is easier to evaluate.
### Proposed Behavior / Steps to Reproduce
- fplan/bplan hand off directly (merge or tplan) with no approval stop.
- tplan does not stop for approval on its own output.
- After tplan, write and show one outline of what will be done across all plans plus a one-line change summary; user approves once, then /implement.
- Genuinely open design questions may still be asked.
### Affected Area
.claude/skills/{fplan,bplan,tplan,plan,design}/SKILL.md, SKILLS_OVERVIEW.md, handoff template.
### Acceptance Criteria
- [x] fplan, bplan, tplan contain no approval stop before handing off.
- [x] tplan ends by writing an outline of all plans plus a one-line change summary to the handoff file.
- [x] The outline is presented once for approval before /implement.
- [x] SKILLS_OVERVIEW.md reflects the new flow.

## 2. Design
### Scope: workflow skill files only (.claude/skills)
### Backend Changes: none
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: no breaking changes; fix-plan mode unchanged

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: n/a, workflow markdown only; no backend guide change
### Backend Pattern: n/a
### Recommendations: store outline/summary in section 6 (### Outline, ### Summary), no new handoff section

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (markdown-only)
### Test Cases: grep checks that only tplan step 13 retains an approval stop and that Outline/Summary fields exist in tplan and issue skills
### Edge Cases: fix-plan mode unchanged in all three skills; design step 9 routing still consistent
### Integration Points: make test-changed passes (no code touched)
### Outline
- Backend: n/a
- Frontend: n/a
- Workflow skills: (1) bplan/fplan step 13 continue without approval; (2) tplan step 13 writes outline + summary into this section, then asks once; (3) merge hands off to tplan without approval; (4) issue handoff template gains Outline/Summary; (5) SKILLS_OVERVIEW.md updated.
- Tests: none; grep verification only.
### Summary
Planning skills no longer ask for approval at each stage; tplan ends with one outline and one-line summary for a single approval.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps:
- [x] 1. bplan/fplan step 13: no approval stop, continue per design step 9. Files: bplan/SKILL.md, fplan/SKILL.md. Reuses: existing step 13 + design step 9. New: none.
- [x] 2. tplan step 13: write Outline + one-line Summary into handoff section 6, then single approval. Files: tplan/SKILL.md. Reuses: tplan steps 11-12 pattern. New: outline instruction (no existing cross-plan overview).
- [x] 3. merge: hand off to tplan without approval presentation. Files: merge/SKILL.md. Reuses: existing wording. New: none.
- [x] 4. issue skill handoff template: add Outline/Summary under section 6. Files: issue/SKILL.md. Reuses: template. New: none.
- [x] 5. SKILLS_OVERVIEW.md: update Next lines, tplan output, handoff structure, diagram. Files: SKILLS_OVERVIEW.md. Reuses: existing sections. New: none.
- [x] 6. Tests: none (markdown-only). 7. Docs: covered by step 5.

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=workflow-docs, plan_target=bplan, difficulty=2/10, breaking=no
- 2026-10-31 bplan: 5 steps written, backend_pattern=n/a (workflow markdown)
- 2026-10-31 tplan: test_file=none, 0 test cases (grep verification); outline written
- 2026-10-31 implement: steps 1-7 done (skills edited, overview updated, grep-verified)
