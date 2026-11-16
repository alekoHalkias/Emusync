# Handoff: #750 Remove orphaned blob files and stop device removal from leaking them

## Metadata
- Issue: #750
- Branch: feature/750-orphaned-blob-files
- PR: none
- Status: implemented
- Created: 2026-11-16
- Fix attempts: 0

## 1. Issue
### Summary
Server blob dirs hold files with no row: saves 45 orphans (10.79 GB), states 18 (server PC, 2026-11-16).
### Motivation
Wasted disk; `remove_device` also deletes other devices' needed save generations (possible current-save loss).
### Proposed Behavior / Steps to Reproduce
Push from A and B, remove A, compare `blobs/saves/` with `SELECT id FROM saves`.
### Affected Area
`src/server/store/devices.py` (remove_device, clear_devices, merge_devices), `src/server/store/blobs.py`, one-time cleanup.
### Acceptance Criteria
- [ ] Root cause fixed, no new orphans
- [ ] Device removal keeps generations other devices need (or documented), unlinks files after commit
- [ ] Existing orphans removed once, safely (not `.uploads`, not in-flight `.part`)
- [ ] Real-SQLite regression tests

## 2. Design
### Scope: backend only
### Backend Changes:
- Investigation: prune and remove_game are clean; leaks are remove_device/clear_devices (rows deleted, files kept). remove_device also misses most _DEVICE_REFS tables (FK failure for card/mod pushers).
- Placeholder device REMOVED_DEVICE_ID ("Removed device"), created on demand, hidden from list_devices, rejected by _auth.
- remove_device + clear_devices share one path over _DEVICE_REFS: saves/states/console_save_history/switch_mods/console_saves re-credited to the placeholder; per game/console keep only the removed device's newest generation, delete its older ones, unlink files after commit (#704); other refs deleted.
- Schema v37: move orphan files (no row) under blobs/{saves,states,console_save_history,console_saves,switch_mods} to blobs/.orphaned/<table>/; skip .uploads and .part; log; delete nothing.
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: non-breaking; clear-devices no longer wipes server saves (intended).
### User decisions (2026-11-16): keep removed device's saves credited to a placeholder, but only its newest generation per game; quarantine orphans instead of deleting.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: reuse merge_devices/_DEVICE_REFS (#656) for re-keying; unlink after commit (#704); v37 data fix via _migrate blob_dir (v35/v36 pattern).
### Backend Pattern: remove = delete per-device config rows + merge into placeholder + prune placeholder to newest generation per owner.
### Recommendations: none

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_devices.py, src/tests/test_orphan_blobs.py (new)
### Test Cases: keep-newest per game (save+state), removed device's current save survives, console card + mod pusher removal (FK), placeholder hidden + auth reject, clear_devices keeps saves with no orphans, existing removal tests, v37 quarantine + idempotency
### Edge Cases: remove placeholder id, unknown/double removal, second removed device for same game, missing table in v37
### Integration Points: server PC orphan count 0 outside .orphaned after ship
### Outline:
Backend
- 1. REMOVED_DEVICE_ID placeholder: hidden from list_devices, rejected by _auth
- 2. remove_device: delete per-device config rows, merge_devices into placeholder, keep newest generation per game/console, unlink the rest after commit; clear_devices = remove_device for all
- 3. schema v37: move files with no row to blobs/.orphaned/<table>/ (skip .uploads, .part)
Tests
- 4. test_devices.py removal cases; test_orphan_blobs.py v37 cases
Docs
- 5. CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md
### Summary: Removing a device no longer drops saves or leaks files: its newest generation per game is kept under a hidden "Removed device" placeholder and older ones are deleted cleanly, and v37 moves today's orphaned blob files into blobs/.orphaned/.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/750-orphaned-blob-files.md
- [done] Step 1: store/devices.py, api/_core.py - reuses ensure_device/_auth; new REMOVED_DEVICE_ID constant (FK needs a device row).
- [done] Step 2: store/devices.py, store/blobs.py - reuses merge_devices, _DEVICE_REFS, _unlink_blobs; new _prune_removed_generations (newest-1 per owner for one device, unlike _prune_history).
- [done] Step 3: store/schema.py - reuses _migrate blob_dir hook; new _quarantine_orphan_blobs (nothing compares dirs with rows).
- [done] Step 4: tests in test_devices.py + new test for v37.
- [done] Step 5: CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md.

## 9. Review
### Findings: none
### Blocked: no
### Blockers: none

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
- 2026-11-16 issue: workflow initialized
- 2026-11-16 design: scope=backend, plan_target=bplan, difficulty=5/10, breaking=no
- 2026-11-16 bplan: 5 steps written, backend_pattern=merge into placeholder + v37 quarantine
- 2026-11-16 tplan: test_file=src/tests/test_devices.py + test_orphan_blobs.py, 10 test cases defined
- 2026-11-16 implement: step 1 done (REMOVED_DEVICE_ID placeholder hidden and reserved)
- 2026-11-16 implement: step 2 done (remove_device merges into placeholder, keeps newest per owner); deviation: per-device rows listed once in new _DEVICE_ONLY_REFS tuple next to _DEVICE_REFS; unknown device id is a no-op
- 2026-11-16 implement: step 3 done (schema v37 quarantines orphan blob files); deviation: v36 tests in test_legacy_blob_conversion.py now call _envelope_legacy_blobs directly (their row-less seed files would be quarantined by v37) and compare user_version to _SCHEMA_VERSION
- 2026-11-16 implement: step 4 done (test_device_removal.py, 9 tests); deviation: tests in a new test_device_removal.py (test_devices.py is already 648 lines) including the v37 cases instead of a separate test_orphan_blobs.py; the missing-table test caught v37 quarantining a whole dir when its row query fails, fixed in schema.py to skip the table as the plan specified
- 2026-11-16 implement: step 5 done (CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md)
- 2026-11-16 review: 0 findings, blocked=no
