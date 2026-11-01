# Handoff: #691 Fix path traversal, unsafe tar extraction and presence monitor NameError

## Metadata
- Issue: #691
- Branch: feature/691-path-traversal-tar-presence
- PR: #694
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Three high-severity defects found in a code audit: an arbitrary-file-write via the ROM transfer filename, unguarded tar extraction of client-uploaded archives on the server, and a NameError in the presence monitor.
### Motivation
Security/robustness bugs found in a code audit.
### Proposed Behavior / Steps to Reproduce
1. POST `/games/{slug}/rom-transfer` with header `X-Filename: ../../x` (or an absolute path) from any paired device.
2. Push a console memcard folder archive containing `../` members and pull it back via `pull_console_save_path` / `_extract_memcard_archive`.
3. Let a device go idle past `OFFLINE_TIMEOUT_SECONDS` while it holds no locks.
1. The staged file always lands inside `rom_staging/<transfer_id>/`.
2. Server-side extraction refuses members that resolve outside the destination.
3. The presence monitor logs each released lock and keeps processing other devices.
### Affected Area
`src/server/api/transfers.py`, `src/server/store/blobs.py`, `src/server/sync_client.py` (`_safe_extract_tar`), `src/server/api/_core.py`.
### Acceptance Criteria
- [ ] Filename header is reduced to a safe basename; empty, `.` and `..` rejected.
- [ ] All server-side tar extraction goes through one shared safe-extract helper.
- [ ] Dead suffix branch in `pull_console_save_path` removed or fixed.
- [ ] Presence monitor logs per released lock and never aborts on a device without locks.
- [ ] Regression tests for each, real SQLite.

## 2. Design
### Scope: backend only
### Backend Changes: transfers.py reduce X-Filename to safe basename (reject empty/./..); blobs.py use sync_client._safe_extract_tar in _extract_memcard_archive and remove dead `.tar.gz/.tgz` suffix branch in pull_console_save_path (blob path has no suffix); _core.py move lock-released _print_activity inside the slug loop.
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: not breaking; GH comment posted on #691.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: fits existing HTTPException + shared _safe_extract_tar pattern
### Backend Pattern: reuse sync_client._safe_extract_tar from store/blobs.py (lazy import); no new helpers
### Recommendations: none

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_rom_transfer.py, test_console_memcard.py, test_devices.py
### Test Cases: traversal_filename, absolute_filename, bad_filename (400), malicious_tar, valid_tar, monitor_no_locks, monitor_two_locks
### Edge Cases: backslash separators, blank header default, existing memcard pull tests still pass
### Integration Points: real SQLite Store via api_module.init; reuse make_client, _device_auth, #597 monitor harness
### Outline:
Backend: (1) basename check in transfers.py; (2) _safe_extract_tar in blobs._extract_memcard_archive; (3) delete dead suffix branch; (4) indent lock-released log in _monitor_presence.
Tests: 3 files extended, 7 cases. Docs: none.
### Summary: Sanitize ROM transfer filenames, route server tar extraction through the safe helper, and fix the presence monitor NameError.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
Plan file: tools/plans/691-path-traversal-tar-presence.md
- Step 1: touches api/transfers.py; reuses HTTPException pattern, PurePosixPath stdlib; no new code beyond inline check.
- Step 2: touches store/blobs.py; reuses sync_client._safe_extract_tar; nothing new.
- Step 3: touches store/blobs.py; deletion of dead branch.
- Step 4: touches api/_core.py _monitor_presence; reuses _print_activity/_game_label; indentation fix.
- Step 5: tests in test_rom_transfer.py, test_console_memcard.py, test_devices.py; reuse make_client and #597 monitor harness.
- Step 6: docs none.

## 9. Review
### Findings: none (diff checked against CLAUDE.md rules; full suite 603 passed)
### Blocked: no
### Blockers: none

## 10. Ship
### Status: shipped
### PR: #694
### Server Sync: done
### Doc Sync: done (none needed)

## 11. Fix Attempts
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=2/10, breaking=no
- 2026-11-01 bplan: 6 steps written, backend_pattern=reuse _safe_extract_tar, inline basename check
- 2026-11-01 tplan: test_file=test_rom_transfer.py/test_console_memcard.py/test_devices.py, 7 test cases defined
- tplan step note: reuses make_client/_device_auth/#597 harness; no new fixtures.
- 2026-11-01 implement: steps 1-6 done (basename check, safe tar extract, dead branch removed, monitor log in loop, tests)
- 2026-11-01 review: 0 findings, blocked=no
- 2026-11-01 ship: PR #694, server sync done, doc sync none needed
