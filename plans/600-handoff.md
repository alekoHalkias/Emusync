# Handoff: #600 Standalone skill runner with isolated context per step

## Metadata
- Issue: #600
- Branch: feature/600-standalone-skill-runner
- PR: none
- Status: implementing
- Created: 2026-01-04
- Fix attempts: 0

## 1. Issue
### Summary
Each skill in the EmuSync workflow runs as an inline invocation within a single conversation. Every skill reads the handoff file, the GitHub issue, the plan, CLAUDE.md, docs/ARCHITECTURE.md, docs/GOTCHAS.md, design guides, and multiple code files. Over a full pipeline, the conversation context accumulates to hundreds of thousands of tokens, risking context overflow that halts the workflow mid-pipeline.

### Motivation
The workflow requires 6-10 sequential skill invocations per issue. After 4-5 skills, the conversation context is very large. By the time `implement` and `ship` run, overflow risk is high. An overflow mid-pipeline means lost state and a broken pipeline.

### Proposed Behavior / Steps to Reproduce
Build a standalone runner script that:
1. Reads the handoff file to determine the current stage and next skill to run.
2. Compresses the issue-specific context into a minimal snapshot.
3. Spawns a fresh Claude Code invocation with only that compressed context.
4. The skill runs, writes output to the handoff file and plan files, and exits cleanly.
5. The runner loops until workflow reaches `shipped` or `blocked` status.

### Affected Area
`.claude/skills/` — workflow pipeline infrastructure

### Acceptance Criteria
- [ ] Runner script exists at `scripts/run-skill.sh` (or `.py`)
- [ ] Runner reads `plans/<N>-handoff.md` to determine next skill
- [ ] Context snapshot is generated per-skill, containing only what that skill needs
- [ ] Each skill runs in a fresh process (no inherited conversation context)
- [ ] Skill output writes back to the handoff file and plan files
- [ ] Runner loops until workflow reaches `shipped` or `blocked` status
- [ ] All existing skills remain compatible
- [ ] Documented usage: `scripts/run-skill.sh <issue-number>`

## 2. Design
### Scope: New standalone runner script (`scripts/run-skill.sh`) and context compression utility. No changes to EmuSync product code.
### Backend Changes: New shell script and context snapshot generator. No Python/FastAPI/SQLite/Electron/React changes.
### UI Changes: None.
### Sub-issues: None.
### Difficulty: 5/10
### Backwards Compatibility: New tool only. Reads existing handoff/plan file formats without modification.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: TBD (written by /plan skills)

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
- 2026-01-04 issue: workflow initialized
- 2026-01-04 design: scope=infrastructure, difficulty=5/10, breaking=no
