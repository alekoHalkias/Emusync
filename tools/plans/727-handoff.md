# Handoff: #727 Place Switch saves into each device's own Eden profile

## Metadata
- Issue: #727
- Branch: feature/727-switch-device-profile
- PR: #728
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 1

## 1. Issue
### Summary
Switch saves are placed by adopting whichever Eden profile folder holds the title folder; devices with several profile folders sync a dead one. Each device should have one known profile and the save is moved into it.
### Motivation
Deck Z-A save_path is in malformed profile 677DFF94055FFF9B3D00000000000000; pulls go to a dead folder and stale saves can overwrite newer progress.
### Proposed Behavior / Steps to Reproduce
Save path on every device = <nand root>/<device profile>/<title id>, profile detected from profiles.dat (byte-reversed UUID) and stored per device on the Switch consoles row.
### Affected Area
store schema/consoles, consoles API, cli/run_switch.py, cli/run.py, cli/game.py.
### Acceptance Criteria
- [ ] Per-device profile ID stored, detected from profiles.dat.
- [ ] Find/seed/pull/detect use only the device profile.
- [ ] Existing save_path in another profile corrected.
- [ ] Blob carries only title folder contents.
- [ ] Tests with multiple profile folders.

## 2. Design
### Scope: backend (store, devices API, sync client, CLI run path)
### Backend Changes: New `consoles.switch_profile_id` column (schema v33), exposed on GET /devices/{id}/consoles and the existing PUT /devices/{id}/consoles/{console_id} as an Optional preserve-if-None field (same pattern as network_share_id, #644). CLI: detect live Eden profile folders from profiles.dat (byte-reversed UUID); resolve the device profile (stored value, else detected, then stored fill-only-blank); find/seed/post-launch detection use only <nand root>/<profile>/<title id>; a save_path in another profile is corrected. Blob format unchanged (already title-folder contents only).
### UI Changes: none (profile auto-detected; GUI editor deferred)
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: Additive column with default and Optional request field; older clients that PUT without it keep the stored value. Not breaking.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: per-device console column like network_share_id (#644); schema v33; restrict the shared _switch_profile_dirs.
### Backend Pattern: Optional preserve-if-None on existing PUT; fill-only-blank detection.
### Recommendations: detect from profiles.dat, stored value wins.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_switch_profile.py
### Test Cases: migration; PUT/GET preserve; profiles.dat parse; profile-restricted dirs; find/seed/resolve scope; run_game save_path correction
### Edge Cases: missing/truncated profiles.dat fallback; stored wins; fill-once with warn-only failure
### Integration Points: CLI -> GET/PUT /devices/{id}/consoles -> store.set_console
### Outline:
Backend: (1) consoles.switch_profile_id v33 + API field; (2) SyncClient.update_device_console; (3) profiles.dat detection, _switch_profile_dirs restricted to device profile; (4) resolve/store device profile in run/game; (5) correct save_path in another profile; (7) docs.
Tests: (6) test_switch_profile.py, 6 cases + edge cases.
### Summary: Each device records its Eden profile on its Switch console row and Switch saves are only ever placed in <nand root>/<that profile>/<title id>.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps:
1. store/API column - schema.py, models.py, consoles.py, api/devices.py; reuses network_share_id pattern.
2. client PUT wrapper - sync_client.py; new because no client wrapper for the PUT exists.
3. profiles.dat detection + restriction - run_switch.py; new parser, no existing reader.
4. resolve/store device profile - run_switch.py, run.py, game.py; reuses get_device_consoles.
5. correct save_path in other profile - run.py; reuses #725 self-heal.
6. tests. 7. docs.

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
### Attempt 1: prefer the Eden root that already has the device profile
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=5/10, breaking=no
- 2026-11-01 bplan: 7 steps written, backend_pattern=per-device console column + restricted profile dirs
- 2026-11-01 tplan: test_file=src/tests/test_switch_profile.py, 6 test cases defined
- 2026-11-01 implement: started; user confirmed Deck live profile is 0F9E31CF8F16E6677DFF94055FFF9B3D
- 2026-11-01 implement: step 1 done (consoles.switch_profile_id v33 + API field)
- 2026-11-01 implement: step 2 done (SyncClient.update_device_console)
- 2026-11-01 implement: steps 3-5 done (profiles.dat detection, device profile resolve/store, save_path correction; conftest isolation)
- 2026-11-01 implement: step 6 done (test_switch_profile.py, 9 tests; verified on real Arch profiles.dat)
- 2026-11-01 implement: step 7 done (GOTCHAS, ARCHITECTURE; CLAUDE.md in step 2)
