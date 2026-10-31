# Plan: #660 Share network-drive ROMs across devices and add upload requests (frontend)

Issue: #660
Branch: feature/660-network-rom-sharing
PR: none
Status: planned
Fix attempts: 0

## Goal
Let a device play a shared-drive game via share-ID matching without manual mount setup, request an upload of another device's local-only ROM, and let the owning device approve or decline large-ROM requests on GUI start.

## Design Alignment
- **Visual Pattern**: The approval prompt is a banner in the `UpdateBanner` style (surface2 strip, 12px text, `btn btn-ghost` buttons) mounted next to it in App.tsx. The request action is a third option block in the existing `NetworkPlaySetup` modal, same bordered-card layout as "Pull the ROM to this device". No new modal.
- **Recommendations**: Add a "Banners" line to the frontend guide (strip under the topbar for actionable background events, one row per item, primary + ghost action). GUI shells out to the CLI for the upload (#479), matching `sync/save.ts`.

## Steps
- [ ] 1. api.ts: add `share_id` to `GameNetworkSource`; give `createPullRequest` an optional `kind` arg; add `listPendingPullRequests()` (GET /rom-pull-requests/pending) and `listOutgoingPullRequests()` (GET /rom-pull-requests/outgoing) with a shared `PullRequestRow` type.
  - Files: src/gui/renderer/src/api.ts
  - Reuses: api.ts:_fetch, createPullRequest, GameNetworkSource
  - New: two list helpers and one type - no existing client for these routes
- [ ] 2. IPC `rom:fulfillNetworkUpload(requestId, approve)`: spawns `emusync rom fulfill-network-upload <id> [--decline]`, returns `{ok, error?}`. Export `runCliTransfer` from save.ts and reuse it. Register in main.ts, expose in preload.ts, type in emusync.d.ts.
  - Files: src/gui/electron/sync/save.ts (export only), src/gui/electron/sync/rom.ts or new src/gui/electron/sync/netupload.ts (keep rom.ts from growing), src/gui/electron/main.ts, src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: save.ts:runCliTransfer, runtime.ts SCRIPT/PYTHON
  - New: one IPC handler module - rom.ts is already over the 300-line guideline
- [ ] 3. `NetworkUploadPrompt` banner: on mount, list pending requests with `kind === "network-upload"`; render one row each ("<device> asked to upload <game> to the network drive", Upload / Decline buttons, busy spinner, inline error on failure); remove the row on success. Mount in App.tsx beside `<UpdateBanner />`. Daemon-handled small ROMs never appear because the daemon completes them first.
  - Files: src/gui/renderer/src/components/NetworkUploadPrompt.tsx (new), src/gui/renderer/src/App.tsx
  - Reuses: UpdateBanner.tsx styling, icons.tsx WarningIcon, api.ts list helper, window.emusync.rom.fulfillNetworkUpload, whoami/device list for the requester name
  - New: component - nothing existing shows pending cross-device requests
- [ ] 4. NetworkPlaySetup, share-ID resolution: after loading `getGameNetworkSource` and this device's console row, if the row's `network_share_id` equals `netSource.share_id`, use its `device_network_folder` as the mount (ahead of `recent_import_folders`) so tryAutoImport runs with no setup. Different non-blank IDs show a muted "different share" note instead of auto-search.
  - Files: src/gui/renderer/src/components/NetworkPlaySetup.tsx
  - Reuses: tryAutoImport, getDeviceConsoles, whoami (already imported), getGameNetworkSource
  - New: none (a lookup in the existing load effect)
- [ ] 5. NetworkPlaySetup, request upload: when the game has no network source and a source device holds it locally, show a third option block "Ask <device> to upload it to the network drive" calling `createPullRequest(slug, source.id, "", "network-upload")`. Show the outgoing request status (pending / failed / done) from `listOutgoingPullRequests`, and disable the button while one is pending. Message explains it runs next time EmuSync starts on that device.
  - Files: src/gui/renderer/src/components/NetworkPlaySetup.tsx
  - Reuses: pullToDevice flow and its option-block markup, `sources` state
  - New: one handler and one block - parallel to existing option B but a different request kind and outcome
- [ ] 6. Verify: `npm run typecheck`/build in src/gui, then run the app against a dev server with two devices for the request-to-approve round trip (no GUI test framework exists in the repo).
  - Files: none
- [ ] 7. Docs: add the Banners pattern to .claude/frontend-design-guide.md; CLAUDE.md GUI rule line for #660 (prompt banner, `rom:fulfillNetworkUpload`, share-ID mount resolution); ARCHITECTURE.md IPC list.
  - Files: .claude/frontend-design-guide.md, CLAUDE.md, src/docs/ARCHITECTURE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (rom:fulfillNetworkUpload). New CLI subcommand: no (backend plan adds rom fulfill-network-upload). Config/data file change: no.

## Not in this plan
- Showing the ROM size in the prompt (pending list does not carry it).
- Live SSE push of requests into an already-open GUI; the prompt reads on mount only.
- Requester notification outside the NetworkPlaySetup modal.

## Log
