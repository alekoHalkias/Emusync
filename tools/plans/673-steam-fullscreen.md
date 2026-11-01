# Plan: #673 Start fullscreen when launched from Steam

Issue: #673
Branch: feature/673-steam-fullscreen
PR: none
Status: planned
Fix attempts: 0

## Goal
Open the EmuSync window fullscreen whenever the process was launched by Steam.

## Design Alignment
- **Visual Pattern**: extends the existing launch-time fullscreen detection in `display.ts:load()` (`--fullscreen`, `SteamDeck`, `SteamOS`); no UI change.
- **Recommendations**: Steam launch overrides the saved preference for that session only. `applyDisplay` calls `setFullScreen` before the page is ready, and `sync` ignores events until ready, so the override is not persisted and desktop launches are unaffected.

## Steps
- [ ] 1. In `load()`, force fullscreen when `SteamGameId` or `SteamAppId` is set (set by Steam for non-Steam shortcuts too).
  - Files: src/gui/electron/display.ts
  - Reuses: existing `process.argv.includes("--fullscreen")` force condition
  - New: none
- [ ] 2. Tests: none automated - Electron main has no test harness; verify by `SteamGameId=1 make dev-gui` (fullscreen) vs plain `make dev-gui` (saved preference), plus tsc.
- [ ] 3. Docs: none needed - the display.ts behavior is not documented per-variable; add one clause to CLAUDE.md only if a Steam/fullscreen rule exists there.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Making the emulator window fullscreen for `emusync run <slug>` shortcuts.

## Log
