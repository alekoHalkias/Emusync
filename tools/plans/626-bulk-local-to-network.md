# Plan: #626 Offer bulk move and network upload of local-only games on Refresh locations

Issue: #626
Branch: feature/626-bulk-local-to-network
PR: none
Status: implementing
Fix attempts: 0

## Goal
Refresh locations offers, in a popup, to move local-only games into the console's default folder and add them to the network drive, then does so in bulk on confirm.

## Design Alignment
- **Visual Pattern**: reuse the existing modal styling used by LocationResolverModal / ConsoleFoldersModal.
- **Recommendations**: none.

## Steps
- [ ] 1. Extract the upload logic from MoveLocalRomPanel.handleUpload into `uploadLocalRom(slug, folder, netFolder)` (reads the current game device config so it works after a move); the panel calls it.
  - Files: src/gui/renderer/src/components/game-config/localToNetwork.ts (new), MoveLocalRomPanel.tsx
  - Reuses: rom.uploadMaster, relPathUnder, getGameDevice/setGameDevice
  - New: helper file - the logic must be shared by the panel and the bulk modal.
- [ ] 2. useBrokenRoms.refresh also returns `candidates`: local-source, non-missing, not just corrected, games on this device whose console has a network folder (canUpload) or whose ROM is outside device_local_folder (canMove).
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: consoles already fetched in refresh, inside()
- [ ] 3. LocalToNetworkModal: list of candidates, two checkboxes (move, add to network drive), Confirm runs move then upload per game, collecting per-game errors; shows a summary.
  - Files: src/gui/renderer/src/components/LocalToNetworkModal.tsx (new)
  - Reuses: rom.moveToConsoleFolder, uploadLocalRom, existing modal CSS classes
  - New: modal - no existing modal does bulk actions with options.
- [ ] 4. GameGrid.handleRefreshLocations opens the modal when candidates exist; onChanged after it closes with changes.
  - Files: src/gui/renderer/src/components/GameGrid.tsx
- [ ] 5. Tests: none (renderer/Electron have no harness); tsc and make test must not regress; manual check.
- [ ] 6. Docs: ARCHITECTURE.md and CLAUDE.md one-liners.

## Testing
- **Test File**: none (manual + tsc + make test)
- **Test Cases**: refresh with local-only games shows popup; confirm moves/uploads; cancel changes nothing; no popup when none qualify.
- **Edge Cases**: one game fails (others continue); master already exists (linked); no network folder (upload option hidden).
- **Integration Points**: PUT /games/{slug}/device.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Cancel mid-run; progress bars per copy.

## Log
