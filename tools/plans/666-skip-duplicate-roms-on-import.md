# Plan: #666 Skip name-duplicate ROMs of games already configured on this device when importing

Issue: #666
Branch: feature/666-skip-duplicate-roms-on-import
PR: none
Status: implementing
Fix attempts: 0

## Goal
A ROM whose name matches a game that already has a ROM on this device counts as already imported instead of being linked again.

## Root cause
`dedupeAndLink` (console-import/helpers.ts) skips a ROM only when its path or lowercase filename equals this device's stored config. A ROM with a different filename but the same slug/name (for example `Pokemon_Emerald_Crest.gba` vs `Pokemon Emerald Crest.gba`) falls to the cross-device branch and gets `linkedSlug`, even though that game already has a ROM here. `linkShareGames` then re-links it and the wizard reports "N games linked from <device>" on every open; `scanNewRoms` counts the same ROMs as new.

## Design Alignment
- **Visual Pattern**: no visual change.
- **Recommendations**: none

## Steps
- [ ] 1. In `dedupeAndLink`, when `crossMatch` is found and its slug is in `thisDeviceConfigs`, return `{ ...rom, existingGameSlug: crossMatch.slug }` so the ROM is filtered out and counted in `skipCount`.
  - Files: src/gui/renderer/src/components/console-import/helpers.ts
  - Reuses: existing `existingGameSlug` skip path and `thisDeviceConfigs` argument
  - New: none
- [ ] 2. Tests: no renderer test harness exists; verify with tsc on the touched file and a manual check (Review and import on the GBA share no longer reports 5 linked; Refresh count excludes them; a game configured only on another device still links).
- [ ] 3. Docs: none needed - behavior fix, no rule/IPC/config change.

## Testing
- **Test File**: none (no renderer harness)
- **Test Cases**:
  - Manual: GBA share with underscore-named duplicates reports no linked games
- **Edge Cases**:
  - Game with no ROM on this device but present on another still gets linkedSlug
- **Integration Points**:
  - Wizard (useConsoleImport) and scanNewRoms both call dedupeAndLink

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Choosing which of several duplicate files a game should point at.

## Log
