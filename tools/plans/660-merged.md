# Merged Plan: #660 Share network-drive ROMs across devices and add upload requests

Source plans: tools/plans/660-network-rom-sharing-ui.md, tools/plans/660-network-rom-sharing.md
Branch: feature/660-network-rom-sharing
PR: none
Status: planned
Fix attempts: 0

## Goal
A shared-drive game resolves on any device with the same share ID, and any device can ask the owning device to upload a local-only ROM to the network drive, fulfilled by the daemon (small) or approved in the GUI (large).

## Steps
Backend first, then IPC, then UI.
- [ ] 1. network-source returns `share_id` (source console's `network_share_id`). Files: src/server/store/games.py, src/server/api/games.py. Reuses: get_network_source_for_game. New: none.
- [ ] 2. Request creation for `kind="network-upload"` (validate local source, 409 if already on network, dedupe pending) plus store `find_pending_pull_request`. Files: src/server/api/transfers.py, src/server/store/transfers.py. Reuses: create_pull_request route. New: find_pending_pull_request (no lookup by slug/kind).
- [ ] 3. `GET /rom-pull-requests/outgoing` returning rows `{id, slug, game_name, kind, status, from_device_id, requested_at}` plus store `list_pull_requests_by_requester`. Files: src/server/api/transfers.py, src/server/store/transfers.py. Reuses: RomPullRequest mapping. New: requester-keyed list.
- [ ] 4. Config `network_upload_auto_max_mb: int = 512`. Files: src/server/config.py. Reuses: Config handling.
- [ ] 5. `netrom.upload_to_network(client, slug)` (marker check, temp+rename copy, no overwrite, flip row to network). Files: src/cli/netrom.py. Reuses: path_is_reachable, SyncClient methods. New: Python upload (only a TS version exists).
- [ ] 6. Daemon branch for `network-upload` in `_handle_pull_request`: oversize stays pending, else upload and complete. Files: src/cli/transfer.py. Reuses: _handle_pull_request, drain loop.
- [ ] 7. CLI `rom fulfill-network-upload <id> [--decline]`. Files: src/cli/rom.py. Reuses: upload_to_network, complete_pull_request.
- [ ] 8. Backend tests (real SQLite): share_id; create/dedupe/reject cases; outgoing list; upload_to_network match/mismatch/no-overwrite; daemon leaves oversize pending. Files: src/tests/test_network_upload_requests.py (new), src/tests/test_network_rom.py.
- [ ] 9. api.ts: `share_id` on GameNetworkSource, optional `kind` on createPullRequest, `listPendingPullRequests`, `listOutgoingPullRequests`, shared `PullRequestRow` type matching step 3. Files: src/gui/renderer/src/api.ts.
- [ ] 10. IPC `rom:fulfillNetworkUpload(requestId, approve)` shelling to step 7: export `runCliTransfer` from sync/save.ts, new sync/netupload.ts, register in main.ts, preload.ts, emusync.d.ts. Reuses: runCliTransfer.
- [ ] 11. `NetworkUploadPrompt` banner (UpdateBanner style) mounted in App.tsx; lists pending `network-upload` requests, Upload/Decline via step 10. Files: src/gui/renderer/src/components/NetworkUploadPrompt.tsx (new), App.tsx.
- [ ] 12. NetworkPlaySetup: share-ID mount resolution (console row `device_network_folder` when `network_share_id` equals `share_id`) and a third option block "Ask <device> to upload" with outgoing status. Files: src/gui/renderer/src/components/NetworkPlaySetup.tsx. Reuses: tryAutoImport, pullToDevice block, getDeviceConsoles.
- [ ] 13. Verify: `make test-changed`, GUI typecheck/build, manual two-device round trip.
- [ ] 14. Docs (single pass): CLAUDE.md rule line, ARCHITECTURE.md (route, CLI command, config key, IPC, kind), GOTCHAS.md (oversize stays pending), frontend guide Banners already added.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (rom:fulfillNetworkUpload). New CLI subcommand: yes (rom fulfill-network-upload; note in PR). Config/data file change: yes (network_upload_auto_max_mb).

## Conflicts resolved
- CLAUDE.md / ARCHITECTURE.md: both plans had a docs step; combined into step 14.
- API shape: the outgoing-requests response fields pinned in step 3 so api.ts (step 9) matches.
- IPC: backend owns the CLI command (step 7), frontend owns the channel (step 10); channel + preload + d.ts all in one step.
- Ordering: backend steps 1-8 precede api.ts/UI steps; step 12 needs `share_id` from step 1.

## Unresolved conflicts
none

## Not in this plan
- Drain on every CLI invocation (e.g. emusync run); only daemon and GUI start.
- Switch folder ROMs; ROM size in prompt; SSE push to an open GUI.

## Log
