# Plan: #629 Console settings model (frontend): one block per console, emulator dropdown, other ROM folders

Issue: #629
Branch: feature/629-console-settings-model
PR: none
Status: planned
Fix attempts: 0

## Goal
Rewrite ConsoleFoldersModal into one block per console with a real emulator dropdown, a conditional copy-destination field, and an Other ROM folders section, backed by `device_extra_folders`.

## Design Alignment
- **Visual Pattern**: Keeps the existing modal pattern (`Modal` size md, `config-form`, `input-group`, `btn btn-ghost` Browse, `modal-actions`, muted 12px helper text). Emulator uses a plain styled `<select>` as in ConsoleStep. Extras list is rows of read-only text plus `btn btn-ghost` Remove, with an `Add folder` ghost button using the existing `dialog.openFolder` picker. No new CSS classes.
- **Recommendations**: Add a "Settings forms" entry to `.claude/frontend-design-guide.md` (label-above-input groups, helper text under a conditional field, list-with-Remove rows). Legacy extra console rows are shown read-only (no delete route exists, and none is added); this is a deliberate limit.

## Steps
- [ ] 1. API types: `DeviceConsole` gains `device_extra_folders?: string[]`; `updateDeviceConsole` already takes the Omit type so the payload carries it. Doc comment updated.
  - Files: src/gui/renderer/src/api.ts
  - Reuses: existing `DeviceConsole` / `updateDeviceConsole`
  - New: none
- [ ] 2. Refresh classification: `sourceFor()` adds each `device_extra_folders` entry as a `local` candidate (longest-prefix logic unchanged), so #616 broken-ROM badge and #618 local/network tagging treat extras as local locations.
  - Files: src/gui/renderer/src/components/game-list/useBrokenRoms.ts
  - Reuses: `sourceFor` candidates array and `.filter(inside)`
  - New: none
- [ ] 3. Modal body rewrite, group and fields: pick the primary row for the console (the row whose `device_game_folder` is non-blank, first wins; matches backend upsert); render one `config-form` with ROM folder, Save folder, States folder, Emulator, Network (NAS) folder. Copy field ("Copy network ROMs to") renders only when the network folder is non-blank, placeholder shows the ROM folder; on Save, blank copy folder with a network folder set is written as the ROM folder so `device_local_folder` consumers (Move/Network panels, cli/rom.py) see the effective value. Single PUT with all fields. Keep the shared-memcard note and the empty state.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: existing `edit`/`browse`/`save` handlers, `updateDeviceConsole`, `usesSharedSaveLayout`; FIELDS array trimmed to the plain-text pickers
  - New: none (same component; no new file)
- [ ] 4. Emulator dropdown: on open call `window.emusync.emulator.detect(consoleKey)`; options = detected `label`s plus a blank "Not set" entry plus the currently stored value if it is not among them (legacy derived or custom text). Stored value = the label string. Label-only: no launch_command rewrite.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: `emulator:detect` IPC and `DetectedEmulatorOption.label` (already typed in emusync.d.ts); ConsoleStep select markup
  - New: none; no IPC channel added
- [ ] 5. Other ROM folders section (bottom): list `device_extra_folders` each with Remove, plus legacy rows' `device_game_folder` (other rows for this console) shown read-only with a one-line note; `Add folder` opens `dialog.openFolder`, ignores blanks and duplicates, and the section saves with the main Save button. Remove edits local state only.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: `browse` pattern, `window.emusync.dialog.openFolder`
  - New: none
- [ ] 6. Retire the stale helper text ("Changing the ROM folder starts a new entry...") since upsert now routes differing folders into extras, and replace with one line about Other ROM folders.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
- [ ] 7. Verification: no JS test runner exists in the repo, so run `make lint` (tsc node+web), then drive the modal with the `run` skill: open a console with a network folder, an unset emulator, one extra folder; Save; reopen; confirm persistence and that Refresh locations does not flag a ROM under an extra folder as outside the console folder.
- [ ] 8. Docs: add the Settings forms entry to .claude/frontend-design-guide.md; CLAUDE.md GUI rules line for ConsoleFoldersModal (one block per console, extras, label-only emulator, #629); ARCHITECTURE.md only if it lists modal behavior.
  - Files: .claude/frontend-design-guide.md, CLAUDE.md, src/docs/ARCHITECTURE.md

## Checklist
Schema bump: no (backend plan owns it). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Backend column, upsert routing, REST field (bplan).
- Deleting legacy extra console rows; a dedicated DELETE route.
- Rewriting per-game launch commands when the emulator changes.
- Changes to GameConfig.tsx, MoveLocalRomPanel, NetworkRomPanel, localToNetwork (read-through only).

## Log
