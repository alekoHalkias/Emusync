# Handoff: #734 Fix save integrity hashing, reconcile baseline, stale locks and related sync issues

## Metadata
- Issue: #734
- Branch: feature/734-sync-audit-fixes
- PR: none
- Status: planned
- Created: 2026-11-02
- Fix attempts: 0

## 1. Issue
### Summary
Code audit found three confirmed sync bugs plus eight smaller robustness issues in the save/sync path, blob store and locks.
### Motivation
Every enveloped save is flagged damaged by integrity checks; restores record unmatchable hashes; a stale save can silently overwrite newer progress under clock skew; a crashed run leaves a lock that blocks launches indefinitely.
### Proposed Behavior / Steps to Reproduce
1. Envelope hash: `_classify_blob`, `_last_good_version`, `_restore_blob`/`_push_blob`, `restore_console_save` hash full bytes incl. ES1 envelope; `_stage_upload` records envelope-free hash. Use one envelope-free helper everywhere.
2. `_reconcile_save`: decide push/pull from baseline (local unchanged + server changed -> pull; local changed + server unchanged -> push); mtime only on true divergence or no baseline.
3. `GET /games/{slug}/lock`: treat locks older than LOCK_TTL_HOURS as unlocked.
4. `acquire_lock`: atomic (BEGIN IMMEDIATE or conditional write).
5. `run.py`: failed state pull warns and launch continues.
6. `push_state` folder pack: recurse (rglob), skip `.bak`.
7. `_write_memcard_raw_bytes`: atomic temp + os.replace.
8. `_write_memcard_raw_bytes`: directory at raw path must not report pulled=True.
9. `_prune_console_history`: unlink after commit.
10. `push_console_save_file`: don't replace the live blob a pull may be streaming (per-generation path).
11. Remove duplicate `SyncClient.pull_save`/`push_save`.
### Affected Area
src/server/store/blobs.py, src/server/store/locks.py, src/server/api/locks.py, src/server/api/blobs.py, src/server/sync_client.py, src/cli/run.py, src/cli/run_reconcile.py
### Acceptance Criteria
See issue #734 checklist. Regression tests for items 1-4 at minimum.

## 2. Design
### Scope: backend only
### Backend Changes: envelope-free hash helper (store/blobs.py) for integrity, last-good, restore, console restore; baseline-driven reconcile (cli/run_reconcile.py); lock TTL on read + atomic acquire (store/locks.py, api/locks.py); state-pull failure fallback (cli/run.py); sync_client.py: recursive state pack, atomic raw write, directory guard, remove duplicate pull_save/push_save; console history unlink after commit; console live blob not replaced under a streaming pull.
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: not breaking. No schema/API/config/IPC change. Legacy un-enveloped blobs hash unchanged. Old restored rows keep stored hash; clients converge after one re-push. Console blob path change must still read existing console_saves/<key>.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: fits existing patterns; fixes stay in existing Store mixins, reconcile policy fn, and SyncClient methods. No new routes/tables/schema/config.
### Backend Pattern: post-commit unlink (#704), .part + os.replace (#715), envelope-free hashing (#478) applied consistently.
### Recommendations: design guide rule - server-side content hashes always envelope-free via _payload_sha256. Overlap with open PR #733 (run.py, sync_client.py) is in different regions.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD
### Outline: TBD
### Summary: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/734-sync-audit-fixes.md
- 1. store/blobs.py; reuses sync_client envelope constants + _stage_upload rule; new _payload_sha256 (no helper hashes stored bytes envelope-free).
- 2. cli/run_reconcile.py; reuses _decide_save_action (optional baseline_hash param); no new code.
- 3. store/locks.py, store/games.py; reuses LOCK_TTL_HOURS + locks PK; new _lock_cutoff (shared by 3 queries).
- 4. cli/run.py state pull block; reuses #717 warn pattern; no new code.
- 5. sync_client.py push_state/_backup_state_files/dup removal; reuses _memcard_payload_bytes rglob pattern.
- 6. sync_client.py _write_memcard_raw_bytes; reuses download_transfer .part pattern.
- 7. store/blobs.py console history/pull; reuses _prune_history return-ids shape, _unlink_blobs.
- 8. tests: test_integrity, test_console_memcard, test_run_reconcile, test_locks, test_state_sync, test_memcard_folder_sync.
- 9. docs: GOTCHAS, CLAUDE.md, design guide.

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
- 2026-11-02 design: scope=backend, plan_target=bplan, difficulty=5/10, breaking=no
- 2026-11-02 bplan: 9 steps written, backend_pattern=existing store mixins + sync_client, no schema
