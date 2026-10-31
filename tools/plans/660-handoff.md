# Handoff: #660 Share network-drive ROMs across devices and add upload requests

## Metadata
- Issue: #660
- Branch: feature/660-network-rom-sharing
- PR: none
- Status: planned
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Network-drive games playable on every device with the same share ID; devices can request that another device upload a local-only ROM to the network drive.
### Motivation
Per-device path setup and manual upload today.
### Proposed Behavior / Steps to Reproduce
Share ID + relative path resolution (#644). Any device can request an upload; owning device checks pending requests once on any EmuSync launch (GUI, tray/background, CLI). Auto-upload under a size threshold, prompt above it; declines/failures reported to requester. Decisions confirmed with user.
### Affected Area
store/games.py, store/consoles.py, store/schema.py, api/games.py, api/devices.py, cli/netrom.py, cli/rom.py, cli/run.py, electron sync/rom.ts, localToNetwork.ts, useNetworkShare.ts, useBrokenRoms.ts
### Acceptance Criteria
See https://github.com/alekoHalkias/Emusync/issues/660

## 2. Design
### Scope: backend+ui
### Backend Changes: new rom_upload_requests table (schema v33), create/list/resolve routes, launch-time pending check for the calling device, share-ID based rel-path resolution fallback for devices without a game_devices row. Reuse rom_rel_path, rom_source, local_rom_path, list_console_shares.
### UI Changes: Request upload action, launch-time processor in Electron main reusing rom:uploadMaster/uploadLocalRom, size-threshold auto vs prompt, request status display, emusync.d.ts entries.
### Plan Target: both
### Sub-issues: none
### Difficulty: 6/10
### Backwards Compatibility: non-breaking; additive schema v33, fallback resolution, new Config key declared in config.py

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: reuse rom_pull_requests with kind=network-upload (no schema bump); #270 network-source gains share_id; fulfilment in one Python function shared by daemon and CLI.
### Backend Pattern: Store mixin helpers + thin routes in api/transfers.py; GUI shells out to CLI (#479).
### Recommendations: declined stored as failed; oversize requests stay pending for GUI prompt; Switch folder ROMs out of scope.

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
### Steps: see tools/plans/660-network-rom-sharing.md (bplan steps 1-9)
- 1: files store/games.py, api/games.py; reuses get_network_source_for_game; new none
- 2: files api/transfers.py, store/transfers.py; reuses create_pull_request route; new find_pending_pull_request (no lookup by slug/kind)
- 3: files api/transfers.py, store/transfers.py; reuses RomPullRequest mapping; new list_pull_requests_by_requester (existing keyed on source)
- 4: files server/config.py; reuses Config handling; new field only
- 5: files cli/netrom.py; reuses path_is_reachable and client methods; new upload_to_network (only TS impl exists)
- 6: files cli/transfer.py; reuses _handle_pull_request; new none (branch)
- 7: files cli/rom.py; reuses upload_to_network; new command (GUI must shell out to CLI)
- 8: files tests/test_network_upload_requests.py, test_network_rom.py; reuses integration fixtures
- 9: docs CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md

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
- 2026-10-31 design: scope=backend+ui, plan_target=both, difficulty=6/10, breaking=no
- 2026-10-31 bplan: 9 steps written, backend_pattern=reuse rom_pull_requests kind=network-upload, python fulfilment shared by daemon and CLI
