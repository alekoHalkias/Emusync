# Handoff: #717 Do not treat a failed save-meta lookup as no server save

## Metadata
- Issue: #717
- Branch: feature/717-save-meta-failure
- PR: none
- Status: planned
- Created: 2026-11-01
- Fix attempts: 0
- Related: #718 (separate issue, not yet branched)

## 1. Issue
### Summary
`_reconcile_save` treats any failure of the server save-metadata lookup as "the server has no save".
### Motivation
A transient timeout/5xx can overwrite a newer server save (local push) or let a fresh save replace server progress post-game.
### Proposed Behavior / Steps to Reproduce
Server answers /health but save/meta times out or 5xx. Expected: failure distinct from 204; no push on failure; warn on stderr.
### Affected Area
src/cli/run_reconcile.py (_reconcile_save ~63-66), src/cli/run.py (post-game push), src/server/sync_client.py, _MemcardClient.
### Acceptance Criteria
- [ ] Request failure not conflated with no save on server
- [ ] No pre-launch push and no post-game push on failure, with warning
- [ ] Regression test with real SQLite server
- [ ] Genuine 204 behavior unchanged

## 2. Design
### Scope: backend only (CLI run path, no schema/API/IPC change)
### Backend Changes: In `src/cli/run_reconcile.py::_reconcile_save`, stop swallowing the `get_save_meta` exception (both the no-save_path branch and the main branch). Let a request failure propagate or return a sentinel so `run.py` takes the offline launch path (or launches without any push). In `src/cli/run.py` skip the post-game save push when the pre-launch reconcile could not reach the server (server_size lookup at ~521 already degrades to None; the push must not proceed on an unverified server state). `_MemcardClient.get_save_meta` shares the path so it is covered. `cli/sync.py:47` and `cli/watch.py:113` callers checked separately in the plan.
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none (#718 is a separate issue)
### Difficulty: 3/10
### Backwards Compatibility: no breaking change; genuine 204 behavior unchanged.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: errors via exceptions, absence via None; reuse run.py offline fallback
### Backend Pattern: propagate meta errors from _reconcile_save, catch once in run_game and call _run_offline
### Recommendations: none

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_run_reconcile.py
### Test Cases: meta_error_propagates; meta_204_still_pushes; server_save_survives_meta_failure (live_server); run_game_falls_back_offline
### Edge Cases: 5xx same as timeout; no-save_path branch propagates; _MemcardClient path
### Integration Points: run.py try/except -> _run_offline; lock release
### Outline:
- Backend: 1 run_reconcile.py stop swallowing meta errors; 2 run.py catch HTTPError -> _run_offline; 4 CLAUDE.md rule line
- Tests: 3 extend _FakeClient, 4 cases (reuses _FakeClient, _write_save, live_server)
### Summary: A failed save-meta request no longer reads as "no server save"; the run launches offline instead of pushing or overwriting.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/717-save-meta-failure.md
- 1. files: src/cli/run_reconcile.py; reuses get_save_meta 204->None contract; new: none
- 2. files: src/cli/run.py; reuses _run_offline, _release; new: none (one try/except)
- 3. files: src/tests/test_run_reconcile.py; reuses existing fixtures; new: tests only
- 4. files: CLAUDE.md; new: one rule line

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
- 2026-11-01 bplan: 4 steps written, backend_pattern=propagate errors, reuse offline fallback
- 2026-11-01 tplan: test_file=src/tests/test_run_reconcile.py, 4 test cases defined
