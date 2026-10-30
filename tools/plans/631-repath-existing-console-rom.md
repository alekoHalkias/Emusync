# Plan: #631 Re-path game when the console folder already has the ROM during move

Issue: #631
Branch: feature/631-repath-existing-console-rom
PR: none
Status: planned
Fix attempts: 0

## Goal
When "Move to console folder" finds a same-named file already in the console folder, re-path the game to it (after a same-size check), verify the result, and leave the original file alone.

## Design Alignment
- **Visual Pattern**: No new UI. The existing inline status text in `MoveLocalRomPanel` (muted 13px next to the button) reports "Moved." or "Already in the console folder - game re-pathed to the existing file." No new classes.
- **Recommendations**: none. `LocalToNetworkModal` (#626, PR not merged to main yet) calls the same IPC and needs no change: an adopted result is `ok: true`, so it stops being listed as an error.

## Steps
- [ ] 1. `rom:moveToConsoleFolder` adopt path: replace the `existsSync(dest)` early error. If dest exists and `statSync(dest).size === statSync(src).size`, skip the rename/copy block and fall through to the existing PUT (rom_path = dest, launch command via the existing `split(src).join(dest)`); if sizes differ keep the current error (message extended with "and it differs in size"). After the PUT, re-GET `/games/{slug}/device` and require `existsSync(dest)` and `rom_path === dest`, else return `ok:false` ("Re-pathed, but could not verify ..."). Return `adopted: true` on this path. Source file is never deleted or overwritten here. Apply the same post-PUT verification to the normal move path (one shared check, no extra branch).
  - Files: src/gui/electron/sync/rom.ts
  - Reuses: the handler's existing GET/PUT calls, `launchCommand` computation, `statSync`, `existsSync`
  - New: a small `adopted` boolean and one verification GET - nothing existing validates the stored config after a move
- [ ] 2. IPC types: add `adopted?: boolean` to the `moveToConsoleFolder` result in both places.
  - Files: src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: the existing channel; no new channel
  - New: none
- [ ] 3. Panel message: in `handleMove`, show "Game re-pathed to the existing file in the console folder." when `r.adopted`, else "Moved."
  - Files: src/gui/renderer/src/components/game-config/MoveLocalRomPanel.tsx
  - Reuses: existing `setMsg` and `onMoved(r.romPath, r.launchCommand)`
  - New: none
- [ ] 4. Verification: no JS test runner or Electron-main test harness exists, so run the tsc checks and `make lint`, then a manual check with a throwaway game: place a same-size file in the console folder, press Move, confirm the message, that the game's path in Settings is the console-folder file, and that the original is still there; repeat with a different-size file and confirm the error.
- [ ] 5. Docs: CLAUDE.md GUI rules line for the #622 move panel gets "an existing same-size file in the console folder is adopted (game re-pathed, verified, original kept, #631)"; ARCHITECTURE.md only if it describes the move flow.
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md (if applicable)

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no (existing channel gains an optional result field; d.ts and preload types updated). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Hash comparison or deleting the original file.
- Changes to LocalToNetworkModal (lands with #626).
- Server/API changes.

## Log
