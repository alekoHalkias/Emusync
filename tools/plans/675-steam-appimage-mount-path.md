# Plan: #675 Fix Steam shortcuts targeting the AppImage temporary mount path

Issue: #675
Branch: feature/675-steam-appimage-mount-path
PR: none
Status: planned
Fix attempts: 0

## Goal
Never write a `/tmp/.mount_*` launcher path into shortcuts.vdf; use the repo-checkout launcher named by EMUSYNC_SCRIPT, or fail with a clear error.

## Design Alignment
- **Visual Pattern**: no UI change; errors reuse the `{ ok:false, error }` result already shown by the Steam add flow.
- **Recommendations**: none. Decision (user): the AppImage runs against a repo checkout via EMUSYNC_SCRIPT; no bundling, no persisted path.

## Steps
- [ ] 1. Add `launcherPath(): string | null` to runtime.ts: `join(dirname(SCRIPT), "emusync")`, or null when that path is inside an AppImage mount (`/tmp/.mount_` prefix, or `process.env.APPIMAGE` set while EMUSYNC_SCRIPT is unset).
  - Files: src/gui/electron/runtime.ts
  - Reuses: runtime.ts:SCRIPT
  - New: launcherPath - the same join is repeated at 5 call sites, so one helper is the smaller diff than patching each.
- [ ] 2. Replace the 4 `join(dirname(SCRIPT), "emusync")` sites in steam.ts and the one in game.ts (`launcher:path`) with `launcherPath()`. Read-only handlers (isAdded, addedSlugs, removeGame) fall back to the old join when null so stale `/tmp/.mount_*` shortcuts are still matched (ourSlug compares by basename). `steam:addGame` returns `{ ok:false, error: "EmuSync is running from an AppImage with no repo checkout. Set EMUSYNC_SCRIPT to <repo>/src/emusync.py and restart." }` when null, before touching shortcuts.vdf. An existing stale entry is rewritten by the existing filter+push path on the next successful add.
  - Files: src/gui/electron/steam.ts, src/gui/electron/game.ts
  - Reuses: steam.ts:ourSlug/isOurShortcut, existing `{ok,error}` return shape
  - New: none
- [ ] 3. Tests: no TS test harness exists and the repo tests are Python/real SQLite; add no new harness. Manual check in the plan log: run with EMUSYNC_SCRIPT unset from an AppImage (expect the error, shortcuts.vdf untouched) and set (expect repo path). Python regression `test_launcher_wrapper_finds_a_python` already covers the wrapper.
  - Files: none
  - Reuses: src/tests (existing wrapper test)
  - New: none - a TS harness for a 5-line path guard is not worth adding
- [ ] 4. Docs: CLAUDE.md Steam/Ops rule noting that the AppImage requires EMUSYNC_SCRIPT for Steam shortcuts and never writes a `/tmp/.mount_*` path (#675).
  - Files: CLAUDE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Bundling the CLI into the AppImage; persisting a repo path in display.json; targeting the AppImage itself as the shortcut exe.

## Log
