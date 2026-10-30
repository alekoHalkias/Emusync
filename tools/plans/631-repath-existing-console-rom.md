# Plan: #631 Re-path game when the console folder already has the ROM during move

Issue: #631
Branch: feature/631-repath-existing-console-rom
PR: none
Status: implementing
Fix attempts: 0

## Goal
When "Move to console folder" finds a same-named file already in the console folder, re-path the game to it (after a same-size check), verify the result, and leave the original file alone.

## Design Alignment
- **Visual Pattern**: No new UI. The existing inline status text in `MoveLocalRomPanel` (muted 13px next to the button) reports "Moved." or "Already in the console folder - game re-pathed to the existing file." No new classes.
- **Recommendations**: none. `LocalToNetworkModal` (#626, PR not merged to main yet) calls the same IPC and needs no change: an adopted result is `ok: true`, so it stops being listed as an error.

## Steps
- [x] 1. `rom:moveToConsoleFolder` adopt path: replace the `existsSync(dest)` early error. If dest exists and `statSync(dest).size === statSync(src).size`, skip the rename/copy block and fall through to the existing PUT (rom_path = dest, launch command via the existing `split(src).join(dest)`); if sizes differ keep the current error (message extended with "and it differs in size"). After the PUT, re-GET `/games/{slug}/device` and require `existsSync(dest)` and `rom_path === dest`, else return `ok:false` ("Re-pathed, but could not verify ..."). Return `adopted: true` on this path. Source file is never deleted or overwritten here. Apply the same post-PUT verification to the normal move path (one shared check, no extra branch).
  - Files: src/gui/electron/sync/rom.ts
  - Reuses: the handler's existing GET/PUT calls, `launchCommand` computation, `statSync`, `existsSync`
  - New: a small `adopted` boolean and one verification GET - nothing existing validates the stored config after a move
- [x] 2. IPC types: add `adopted?: boolean` to the `moveToConsoleFolder` result in both places.
  - Files: src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: the existing channel; no new channel
  - New: none
- [x] 3. Panel message: in `handleMove`, show "Game re-pathed to the existing file in the console folder." when `r.adopted`, else "Moved."
  - Files: src/gui/renderer/src/components/game-config/MoveLocalRomPanel.tsx
  - Reuses: existing `setMsg` and `onMoved(r.romPath, r.launchCommand)`
  - New: none
- [x] 4. Verification (see Testing): no JS test runner or Electron-main test harness exists, so run the tsc checks and `make lint`, then a manual check with a throwaway game: place a same-size file in the console folder, press Move, confirm the message, that the game's path in Settings is the console-folder file, and that the original is still there; repeat with a different-size file and confirm the error.
- [x] 5. Docs: CLAUDE.md GUI rules line for the #622 move panel gets "an existing same-size file in the console folder is adopted (game re-pathed, verified, original kept, #631)"; ARCHITECTURE.md only if it describes the move flow.
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md (if applicable)

## Testing
- **Test File**: none automated. The change lives in the Electron main process (`src/gui/electron/sync/rom.ts`) and a React panel; the repo has no JS test runner or main-process harness, and CLAUDE.md forbids mocks. Adding a runner for one handler is out of proportion, so verification is `tsc` (node + web), `make lint`, `make test-changed` (no Python file changes expected, so it should fall back to the full suite), and the manual script below.
- **Test Cases** (manual, throwaway game in a temp console folder; the server can be a dev server via `make dev-server`):
  - adopt: ROM outside the console folder and a same-size file with the same name inside it. Move shows the re-pathed message; the game's ROM path (Settings, or `GET /games/{slug}/device`) is the console-folder file; the original file still exists.
  - launch command: a game whose `launch_command` embeds the old path now embeds the new path (and a `%ROM%` token launch command is unchanged).
  - verification: the success message only appears after the re-read of the stored path matches.
- **Edge Cases**:
  - same name, different size: the error is returned, game unchanged, nothing written.
  - normal move into an empty console folder still works and still reports "Moved.".
  - source already in the console folder keeps "ROM is already in the console folder".
  - server unreachable during the PUT or the verification GET: `ok: false` with an error, not a false success.
- **Integration Points**:
  - `rom:moveToConsoleFolder` -> `PUT /games/{slug}/device` -> `GET /games/{slug}/device`.
  - `MoveLocalRomPanel` `onMoved` callback updates GameConfig's displayed path and launch command from `r.romPath` / `r.launchCommand`; confirm GameConfig shows the new path after an adopt.
  - `LocalToNetworkModal` (#626, not yet on main) shares the channel; adopted results are `ok: true`.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no (existing channel gains an optional result field; d.ts and preload types updated). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Hash comparison or deleting the original file.
- Changes to LocalToNetworkModal (lands with #626).
- Server/API changes.

## Log
Step 2: CLAUDE.md line for the move panel was updated in the same commit because the pre-commit hook requires it when preload.ts changes (it is the plan's step 5 docs change).
Step 4: tsc node/web show 3 errors each that are identical without these changes (files.ts, steam.ts, etc.), none in touched files; make lint passes. The manual adopt/different-size script was NOT run (needs the Electron app against the real config and server); needs a human check.
Step 5: CLAUDE.md only; ARCHITECTURE.md does not describe the move flow.
