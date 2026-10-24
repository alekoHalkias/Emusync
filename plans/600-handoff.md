# Handoff: #600 Standalone skill runner with isolated context per step

## Metadata
- Issue: #600
- Branch: feature/600-skill-runner-minimal
- PR: none
- Status: implementing
- Created: 2026-01-04
- Last updated: 2026-01-04
- Fix attempts: 0

## 1. Issue
### Summary
Each skill in the EmuSync workflow runs as an inline invocation within a single conversation. Every skill reads the handoff file, the GitHub issue, the plan, CLAUDE.md, docs/ARCHITECTURE.md, docs/GOTCHAS.md, and multiple code files. Over a full pipeline, the conversation context accumulates to hundreds of thousands of tokens, risking context overflow that halts the workflow mid-pipeline.

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
### Design Alignment: n/a — no UI changes.
### Visual Pattern: n/a
### Recommendations: n/a

## 4. Backend Plan
### Design Alignment: n/a — no backend changes.
### Backend Pattern: n/a
### Recommendations: n/a

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: tests/test_run_skill.py (stdlib only, drives the script through a fake `claude` on PATH)
### Test Cases: full status walk created->designed->planned->implementing->implemented->shipped; no-progress run stops; `blocked` exits non-zero.
### Edge Cases: handoff missing; unknown status value; MAX_RUNS hit.
### Integration Points: handoff `Status:` vocabulary in .claude/skills/SKILLS_OVERVIEW.md.

## 7. Test Design
### Test Scope: the runner script only; no product code, no DB.
### Test Types: subprocess-driven script behaviour.
### Test Cases: as section 6.
### Affected Existing Tests: none.
### Implementation Checklist: see plan `## Steps`.

## 8. Implementation Steps
### Steps (from plans/600-skill-runner-minimal.md)
- [ ] 1. `scripts/run-skill.sh`: read `plans/<N>-handoff.md` Status, map to next skill, run it in a fresh `claude -p` process, re-read Status; stop on no progress / MAX_RUNS.
- [ ] 2. `tests/test_run_skill.py`: fake `claude` on PATH rewrites a temp handoff; assert invoke order, no-progress stop, blocked exit.
- [ ] 3. Docs: one line in CLAUDE.md Commands.

### Log
- 2026-01-04 implement: handoff ported forward from feature/600-standalone-skill-runner (rollback left the new branch without one); Metadata Branch/Status reset to the minimal restart.

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
- 2026-01-04 blocked: previous implementation added excessive shell scaffolding (18 files, 1700+ lines) that strayed from the minimal approach — rolling back to main and restarting with this handoff
- 2026-01-04 issue: restarted on branch feature/600-skill-runner-minimal with a minimal plan (single ~60 line script)
- 2026-01-04 implement: Status set to implementing (plan approved), handoff ported to this branch

## Rollback
- **Last known good state:** commit `405f839` (main merge of #599) before step 1
- **Blocked at:** none — informational, from the rolled-back attempt
- **State at failure:** 18 files, 1700+ lines under `scripts/skill-runner/` and `.claude/skill-runner.conf`
