# Plan: #677 Let the AppImage add Steam shortcuts without EMUSYNC_SCRIPT

Issue: #677
Branch: feature/677-appimage-steam-launcher
PR: none
Status: planned
Fix attempts: 0

## Goal
When EmuSync runs from an AppImage, find (or ask for) a repo checkout and use its `src/emusync` as the Steam launcher instead of failing on a missing env var.

## Design Alignment
- **Visual Pattern**: no new UI; the folder picker reuses the native `dialog.showOpenDialog({ properties: ["openDirectory"] })` pattern from files.ts.
- **Recommendations**: none. Bundling the CLI in the AppImage stays out of scope (needs Python and a venv on the device).

## Steps
- [ ] 1. Persist a repo path: add optional `repoPath` to the `Display` interface, read it in `load()`. GUI-only setting, so it lives in display.json, not emusync.toml (#499).
  - Files: src/gui/electron/display.ts
  - Reuses: display.ts:load/save
  - New: one field - no existing key stores a repo location.
- [ ] 2. New `launcher.ts` with `findLauncher()` and `pickLauncher()`. `findLauncher()`: `LAUNCHER` when `LAUNCHER_STABLE`; else the first of display `repoPath`, `~/Documents/Scripts/Emusync`, `~/Github/Emusync`, `~/Emusync`, `~/emusync` whose `src/emusync` exists; else null. `pickLauncher()`: open-directory dialog, accept the pick (or its `src` parent) only if `src/emusync` exists there, save it as `repoPath`, return the launcher path or null on cancel/invalid.
  - Files: src/gui/electron/launcher.ts
  - Reuses: runtime.ts:LAUNCHER/LAUNCHER_STABLE, display.ts:load/save, paths, files.ts dialog call pattern
  - New: launcher.ts - runtime.ts cannot import display.ts (display imports rt from runtime, import cycle), and steam.ts is already large.
- [ ] 3. Use it. In steam.ts, `steam:addGame` does `findLauncher() ?? await pickLauncher()` and on null returns the error "No EmuSync checkout selected. Choose the folder containing src/emusync.py, or set EMUSYNC_SCRIPT." The read-only handlers (isAdded, addedSlugs, removeGame) use `findLauncher() ?? LAUNCHER` since matching is by basename. In game.ts `launcher:path` returns `findLauncher() ?? LAUNCHER`. Remove the `LAUNCHER_STABLE` guard from steam.ts (moved into findLauncher).
  - Files: src/gui/electron/steam.ts, src/gui/electron/game.ts
  - Reuses: existing `{ ok, error }` result shape, ourSlug/isOurShortcut
  - New: none
- [ ] 4. Tests: no TS harness; manual check, plus type-check. See Testing.
- [ ] 5. Docs: update the CLAUDE.md Steam shortcut rule (#675) to describe the lookup order and picker, `repoPath` in display.json (#677).
  - Files: CLAUDE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (display.json `repoPath`, optional).

## Not in this plan
Bundling the CLI/Python into the AppImage; a settings-panel control for repoPath; changing SCRIPT/PYTHON resolution for server spawn.

## Log
