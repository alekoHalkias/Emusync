# Handoff: #693 Clean up upload failure, mod validation, lock release and log sanitization

## Metadata
- Issue: #693
- Branch: feature/693-robustness-cleanup
- PR: none
- Status: implemented
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Low-severity robustness and hygiene defects from a code audit.
### Motivation
Staging leaks, path traversal via title_id/mod_name, no lock-release retry, log forging via X-Device-Name, untracked build artifacts.
### Proposed Behavior / Steps to Reproduce
- transfers.py: stream failure mid-upload leaves rom_staging/<id>/; no size cap.
- switch_mods.py / mods.py: title_id and mod_name unvalidated in path.
- run.py: lock_released set True even when release_lock raised.
- _core.py: X-Device-Name printed raw.
- Repo root emusync wrapper untracked; tsbuildinfo modified.
### Affected Area
src/server/api/transfers.py, mods.py, src/server/store/switch_mods.py, src/cli/run.py, src/server/api/_core.py, .gitignore
### Acceptance Criteria
- [ ] Staging dir removed on upload failure.
- [ ] Title ID and mod name validated at the API boundary.
- [ ] Lock release failure retried once or clearly reported.
- [ ] Control characters stripped from device names before logging/storing.
- [ ] emusync wrapper and tsbuildinfo files ignored.
- [ ] Tests for validation and sanitization.

## 2. Design
### Scope: backend only (plus .gitignore)
### Backend Changes: transfers.py staging cleanup + cap; _core.py _safe_segment/_clean_header; mods.py validation; run.py lock release retry; .gitignore + untrack tsbuildinfo
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: no breaking change; mod names with separators/control chars and over-cap uploads now rejected (400/413)

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: fits API-boundary HTTPException validation; helpers in _core.py
### Backend Pattern: reuse _remove_staging_dir, existing _release closure
### Recommendations: none

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_hardening_693.py
### Test Cases: see plan Testing section
### Edge Cases: encoded slash/backslash/NUL/newline in path segments; empty device name after clean
### Integration Points: client fixture, AUTH, rom_staging dir
### Outline: staging/cap, mods validation, device name, lock retry
### Summary: real SQLite, no mocks

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
See tools/plans/693-robustness-cleanup.md (steps 1-7, each annotated with Files/Reuses/New).

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
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=3/10, breaking=no
- 2026-11-01 bplan: 7 steps written, backend_pattern=boundary validation + _core helpers
- 2026-11-01 tplan: testing section added
- 2026-11-01 implement: steps 1-7 done (single commit)
