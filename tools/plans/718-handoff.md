# Handoff: #718 Surface folder-versus-file card mismatch instead of silent no-op pull

## Metadata
- Issue: #718
- Branch: feature/718-card-format-mismatch
- PR: pending
- Status: implemented
- Created: 2026-11-02
- Fix attempts: 0

## 1. Issue
### Summary
Pulling a raw (file-format) save onto a device whose local card path is a directory silently writes nothing but reports success.
### Motivation
pull_save returns (True, hash), the caller reports a successful pull, and the mismatch is never surfaced.
### Proposed Behavior / Steps to Reproduce
Server holds a raw blob; device's card path is an existing directory; `emusync run` or manual pull.
### Affected Area
src/server/sync_client.py (_write_memcard_raw_bytes, pull_save, pull_console_memcard), src/cli/run_reconcile.py.
### Acceptance Criteria
- Directory-versus-raw mismatch raises a clear error instead of returning success.
- No silent success; mismatch surfaced.
- Raw write uses temp file plus os.replace (already done by #734).
- Regression test for directory card plus raw blob.

## 2. Design
### Scope: backend only
### Backend Changes: typed CardFormatMismatch raised by the raw writer on a directory target; pre-launch reconcile resolves it as "local wins" (push local folder, warn + notify + save_conflicts.json + server conflict record).
### UI Changes: none (manual pull already exits 1 with "Pull failed: <msg>", shown by the GUI).
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: no breaking change. User decision (2026-11-02): on mismatch during `emusync run`, local wins (keeps the old folder-migration behavior from the PCSX2 folder-card fix) but is surfaced loudly instead of reported as a successful pull. The server's old raw copy stays in save history.

## 3. Frontend Plan
### Design Alignment: n/a
### Visual Pattern: n/a
### Recommendations: none

## 4. Backend Plan
### Design Alignment: reuses the existing conflict surface (_warn_save_conflict) and the existing "except Exception -> Pull failed" handling in every other pull caller. One new exception class, no routes, schema or config.
### Backend Pattern: client-side writer raises a typed error; policy decided in run_reconcile.
### Recommendations: none

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_memcard_folder_sync.py, src/tests/test_run_reconcile.py
### Test Cases: see plan file Testing section
### Edge Cases: legacy un-enveloped non-tar blob onto a directory also raises; file target unaffected
### Integration Points: real SyncClient against live_server
### Outline:
Backend
- sync_client: CardFormatMismatch(ValueError) raised by _write_memcard_raw_bytes on a directory target
- run_reconcile/run_conflicts: pull mismatch -> push local, warn with a format-mismatch message, log + report conflict
Tests
- writer raises on directory (replaces the old must-not-raise test)
- reconcile regression via live_server: server ends with the folder copy, conflict logged
### Summary: A raw blob pulled onto a folder card now raises instead of silently succeeding; `emusync run` resolves it as local wins with a visible warning.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: test_write_memcard_legacy_fallback_does_not_crash_on_directory_target (renamed, now expects CardFormatMismatch)
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/718-card-format-mismatch.md (steps 1-4)

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
- 2026-11-02 issue: workflow initialized
- 2026-11-02 design: scope=backend, plan_target=bplan, difficulty=3/10, breaking=no
- 2026-11-02 bplan: 4 steps written, backend_pattern=typed writer error + reconcile policy
- 2026-11-02 tplan: test_file=test_memcard_folder_sync.py + test_run_reconcile.py, 3 test cases defined
- Step 1: src/server/sync_client.py; reuses _write_memcard_raw_bytes; new CardFormatMismatch class - callers need to tell a format mismatch from other ValueErrors.
- Step 2: src/cli/run_reconcile.py, src/cli/run_conflicts.py; reuses _warn_save_conflict (optional message override), client.push_save; no new helper.
- Step 3: src/tests/test_memcard_folder_sync.py, src/tests/test_run_reconcile.py; reuses live_server + SyncClient pattern from test_reconcile_shared_memcard_stale_local_untouched_is_not_a_conflict.
- Step 4: src/docs/GOTCHAS.md, CLAUDE.md; reuses existing #734 / Dolphin #428 entries.
- 2026-11-02 implement: step 1 done (CardFormatMismatch raised on directory target)
- 2026-11-02 implement: step 2 done (reconcile resolves mismatch as local wins)
- 2026-11-02 implement: step 3 done (writer raise test + live_server reconcile regression)
- 2026-11-02 implement: step 4 done (GOTCHAS/CLAUDE.md updated in the step 1 commit, required by the CLAUDE.md commit hook)
