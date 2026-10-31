# Handoff: #660 Share network-drive ROMs across devices and add upload requests

## Metadata
- Issue: #660
- Branch: feature/660-network-rom-sharing
- PR: none
- Status: implementing
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
### Design Alignment: banner in UpdateBanner style for approvals; third option block in NetworkPlaySetup for requests; share-ID lookup in existing load effect.
### Visual Pattern: surface2 strip + btn/btn-ghost; bordered option card.
### Recommendations: Banners pattern added to frontend guide; GUI shells out to CLI. Plan: tools/plans/660-network-rom-sharing-ui.md

## 4. Backend Plan
### Design Alignment: reuse rom_pull_requests with kind=network-upload (no schema bump); #270 network-source gains share_id; fulfilment in one Python function shared by daemon and CLI.
### Backend Pattern: Store mixin helpers + thin routes in api/transfers.py; GUI shells out to CLI (#479).
### Recommendations: declined stored as failed; oversize requests stay pending for GUI prompt; Switch folder ROMs out of scope.

## 5. Merged Plan
### Conflicts Resolved: docs steps combined; outgoing-request response shape pinned for api.ts; IPC channel/CLI ownership split; backend-first ordering
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_network_upload_requests.py (new), src/tests/test_network_rom.py (share_id case)
### Test Cases: share_id in network-source; create/pending/outgoing; dedupe; 409 already-network and 400 not-local; upload_to_network success; daemon small=fulfilled, oversize=pending; decline marks failed
### Edge Cases: marker mismatch/missing; existing master not overwritten; ROM outside local folder; unreachable share; device merge keeps requests
### Integration Points: live_server + SyncClient; make_client + _device_auth; GUI verified by typecheck and manual round trip (no GUI test framework)
- tplan step: files tests/test_network_upload_requests.py (new), test_network_rom.py; reuses make_client, _device_auth, live_server; new file because test_rom_transfer.py only covers kind=rom

### Outline
Frontend:
- api.ts: share_id, kind arg, pending/outgoing list helpers
- IPC rom:fulfillNetworkUpload (netupload.ts, preload, d.ts, export runCliTransfer)
- NetworkUploadPrompt banner in App.tsx (Upload/Decline)
- NetworkPlaySetup: share-ID mount resolution and "Ask <device> to upload" block
Backend:
- network-source returns share_id
- network-upload request creation (validate, 409, dedupe) and outgoing list route
- config network_upload_auto_max_mb
- netrom.upload_to_network (marker check, safe copy, flip to network)
- daemon branch (oversize stays pending) and CLI rom fulfill-network-upload
Tests:
- test_network_upload_requests.py and share_id case in test_network_rom.py
- Verify and docs step

### Summary
Network-drive games become playable on any device with the same share ID, and devices can request an upload of a local-only ROM, fulfilled by the owner's daemon (small) or GUI approval (large).

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/660-merged.md (14 steps, backend 1-8, frontend 9-12, verify 13, docs 14)

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
- 2026-10-31 fplan: 7 steps written, visual_pattern=UpdateBanner-style strip + NetworkPlaySetup option block
- 2026-10-31 merge: 4 conflicts resolved, 0 unresolved
- 2026-10-31 tplan: test_file=src/tests/test_network_upload_requests.py, 7 test cases defined
- 2026-10-31 implement: step 1 done (network-source returns share_id)
- 2026-10-31 implement: step 2 done (network-upload request validation and dedupe)
- 2026-10-31 implement: step 3 done (outgoing pull-requests route)
- 2026-10-31 implement: step 4 done (network_upload_auto_max_mb config key)
- 2026-10-31 implement: step 4 done (network_upload_auto_max_mb config key)
- 2026-10-31 implement: step 5 done (netrom.upload_to_network)
- 2026-10-31 implement: step 6 done (daemon handles network-upload, oversize stays pending)
- 2026-10-31 implement: step 7 done (rom fulfill-network-upload CLI command)
- 2026-10-31 implement: step 8 note: 409/400 check order swapped in the route (network check first) so an owner already flipped to network returns 409
- 2026-10-31 implement: step 8 done (backend tests for network upload requests)
