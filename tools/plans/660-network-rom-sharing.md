# Plan: #660 Share network-drive ROMs across devices and add upload requests

Issue: #660
Branch: feature/660-network-rom-sharing
PR: none
Status: planned
Fix attempts: 0

## Goal
A network-drive game resolves on any device with the same share ID, and any device can ask the owning device to upload a local-only ROM to the network drive, fulfilled on the owner's next daemon/GUI start.

## Design Alignment
- **Backend Pattern**: Reuse the existing server-brokered `rom_pull_requests` table and `/rom-pull-request(s)` routes (#255/#441) with a new `kind="network-upload"`; the `kind` column already exists, so no schema bump. Fulfilment is one Python function (consistent with "GUI shells out to CLI", #479) called by both the sync-daemon drain and a new CLI command that the GUI invokes after the user approves a large ROM. Share-ID matching reuses `consoles.network_share_id` (#644); path resolution reuses `game_devices.rom_rel_path` and `get_network_source_for_game` (#270).
- **Recommendations**: Pull-request status vocabulary stays `pending/fulfilled/failed`; a declined request is stored as `failed`. Large (over threshold) requests are left `pending` by the daemon so the GUI can prompt.

## Steps
- [ ] 1. `GET /games/{slug}/network-source` also returns `share_id` (the source device's `consoles.network_share_id` for that game's console) so the receiving device can compare against its own console share ID.
  - Files: src/server/store/games.py, src/server/api/games.py (passthrough already returns the dict)
  - Reuses: games.py:get_network_source_for_game (add a LEFT JOIN on consoles by device_id + console_name)
  - New: none
- [ ] 2. Request creation for `kind="network-upload"`: in `create_pull_request` route, when kind is `network-upload`, require the target device to hold the game with `rom_source='local'` and a `rom_path`, reject if the game already has a network source (409), and skip creating a duplicate pending request for the same slug/from-device/kind (return the existing id).
  - Files: src/server/api/transfers.py, src/server/store/transfers.py
  - Reuses: transfers.py:create_pull_request, store.get_network_source_for_game, store.get_game_device
  - New: store.find_pending_pull_request(slug, from_device_id, kind) - no existing lookup by slug/kind
- [ ] 3. Requester visibility: `GET /rom-pull-requests/outgoing` returns the caller's own requests (slug, kind, status, from_device_id) so the UI can show pending/failed/fulfilled.
  - Files: src/server/api/transfers.py, src/server/store/transfers.py
  - Reuses: RomPullRequest model, list_pending_pull_requests_for_device row mapping
  - New: store.list_pull_requests_by_requester - existing list is keyed on the source device only
- [ ] 4. Config key `network_upload_auto_max_mb: int = 512` declared on `Config` (so Python keeps it, #499).
  - Files: src/server/config.py
  - Reuses: existing Config field/load/save handling
  - New: none beyond the field
- [ ] 5. `netrom.upload_to_network(client, slug)`: find this device's local game config and its console row (`client.get_device_consoles(own id)`), verify `<device_network_folder>/.emusync-share-id` equals the console's `network_share_id` (refuse if unverified), compute rel path against `device_local_folder` (basename fallback), copy via temp file + rename into `<network folder>/<rel>` with sha256, never overwriting an existing master (skip), then `set_game_device` with `rom_source=network`, `rom_path`, `local_rom_path`, `rom_rel_path`, `rom_sha256`, launch command rewritten. Mirrors `uploadLocalRom` (#624) semantics.
  - Files: src/cli/netrom.py
  - Reuses: netrom.path_is_reachable, sync_client.get_device_consoles/list_my_game_devices/set_game_device
  - New: upload_to_network - the only existing implementation is TypeScript in the renderer (localToNetwork.ts), unusable from the daemon
- [ ] 6. Daemon: in `_handle_pull_request` branch on `kind == "network-upload"`: if ROM size > `network_upload_auto_max_mb`, return without completing (stays pending, logged); else call `upload_to_network` and `complete_pull_request` fulfilled/failed. The startup drain and SSE path already route through this function.
  - Files: src/cli/transfer.py
  - Reuses: _handle_pull_request, _run_transfer_daemon drain
  - New: none (a branch in the existing function)
- [ ] 7. CLI `rom fulfill-network-upload <request_id> [--decline]` for the GUI prompt path: approve calls `upload_to_network` then completes the request; decline marks it `failed`. Exit 0 ok, 1 error.
  - Files: src/cli/rom.py
  - Reuses: netrom.upload_to_network, SyncClient.complete_pull_request
  - New: command - GUI must shell out to CLI per CLAUDE.md, and no command exists for network upload
- [ ] 8. Tests (real SQLite): share_id in network-source; request create happy path, duplicate returns same id, rejected when game already on network or not local on target; outgoing list; `upload_to_network` against a tmp dir share (marker match uploads and flips row; marker mismatch refuses; existing master not overwritten); daemon handler leaves oversize request pending.
  - Files: src/tests/test_network_upload_requests.py (new), src/tests/test_network_rom.py
  - Reuses: test_integration.py client/AUTH pattern, test_network_rom.py fixtures
- [ ] 9. Docs: ARCHITECTURE.md (new route, CLI command, config key, kind), CLAUDE.md rules entry, GOTCHAS note on large-request-stays-pending.
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md, src/docs/GOTCHAS.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): handled by the fplan (rom:fulfillNetworkUpload). New CLI subcommand: yes (rom fulfill-network-upload; note in PR). Config/data file change: yes (network_upload_auto_max_mb).

## Not in this plan
- Draining requests on every CLI invocation (e.g. `emusync run`); only sync-daemon and GUI start do (the daemon runs whenever the app does). Add a one-line drain in run.py if needed.
- Switch folder-ROMs (whole-folder upload) - request is refused for kind rom-folder consoles in v1.
- Frontend (request button, prompt modal, status) - fplan.

## Log
