# Plan: #646 Add ignore list for ROMs in console import

Issue: #646
Branch: feature/646-console-import-ignore-list
PR: none
Status: planned
Fix attempts: 0

## Goal
Let users ignore ROMs in the console import results so they stop reappearing, and manage and unignore them from the console settings modal.

## Design Alignment
- **Visual Pattern**: Row action as a small `btn btn-ghost` with a CloseIcon-style control inside the existing result row (click does not toggle selection); bulk action beside the existing select-all controls; in ConsoleFoldersModal the "Ignored games" button toggles an inline list using the guide's list-editor pattern (one row per item with a ghost Remove-style button, here "Unignore"). Changes apply immediately, not through the modal's Save button.
- **Recommendations**: Store the list under `import_ignored_roms` in emusync.toml, matching the per-console `import_rom_source` / `import_local_folder` / `recent_import_folders` keys. `config.py` declares these fields and drops unknown keys on rewrite (#499), so the field must be added there; a GUI-only `display.json` entry would need a new IPC and is global rather than per-console. Note for PR #645: its `import_network_folder` key has the same problem and needs the same `config.py` field.

## Steps
- [ ] 1. Persist the key: add `import_ignored_roms: dict` to `Config`, load it in `load()` and write it in `save()` when non-empty.
  - Files: src/server/config.py, src/tests/test_config_roundtrip.py
  - Reuses: the `import_rom_source` field/load/save pattern; existing round-trip test style
  - New: none beyond the field
- [ ] 2. Shared accessor `loadIgnoredRoms(consoleKey)` / `saveIgnoredRoms(consoleKey, paths)` over `window.emusync.config.load/save` (empty list removes the console's entry).
  - Files: src/gui/renderer/src/components/console-import/ignoredRoms.ts (new)
  - Reuses: the `config.load()` / `config.save()` read-modify-write used by `removeExtraPath` in useConsoleImport.ts
  - New: one small module - both the wizard and ConsoleFoldersModal need it and neither owns the other
- [ ] 3. Wizard logic: load the ignored set when detection finishes; filter `result.roms` against it in `scanRoms` before annotate/classify; add `ignoreRoms(roms: RomEntry[])` which adds each entry's `romPath` and `localRomPath`, persists, and removes them from `roms` and `selected`; expose `ignoreRoms` and `ignoredCount`.
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: `scanRoms` pipeline, `setRoms`/`setSelected`, ignoredRoms.ts
  - New: `ignoreRoms` (~12 lines) - nothing existing removes entries persistently
- [ ] 4. Results step UI: per-row Ignore button (stops propagation), "Ignore selected" button next to the existing bulk controls, and a muted "N ignored - manage in console settings" line when `ignoredCount > 0`.
  - Files: src/gui/renderer/src/components/console-import/ResultsStep.tsx
  - Reuses: existing row markup, `selected`, button classes
  - New: inline buttons only
- [ ] 5. Console settings: "Ignored games" button in ConsoleFoldersModal toggling an inline panel with the list, per-row Unignore and Unignore all, writing through `saveIgnoredRoms` immediately; empty state text.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx, src/gui/renderer/src/components/IgnoredGamesPanel.tsx (new)
  - Reuses: ignoredRoms.ts, the modal's list-editor markup and `consoleKey` prop
  - New: small panel component - keeps the modal under 300 lines
- [ ] 6. Reset: clear `import_ignored_roms` in the settings reset.
  - Files: src/gui/renderer/src/components/ServerStatusButton.tsx
  - Reuses: the existing reset line that clears `import_rom_source` / `import_local_folder`
- [ ] 7. Verification (cases in the Testing section): Python round trip test for the new key (step 1); renderer has no JS test runner, so check manually via `make dev-gui`: ignore one row and a bulk selection, rescan, confirm they stay hidden, restart the app and confirm persistence, open console settings, unignore, rescan, confirm they return; ignoring never deletes files or imported games.
- [ ] 8. Docs: CLAUDE.md rule line and ARCHITECTURE.md (config field, ignoredRoms.ts, IgnoredGamesPanel).
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md

## Testing
- **Test File**: src/tests/test_config_roundtrip.py (extends the existing art_type_by_console round-trip tests; reuses `monkeypatch` on `cfg_module.CONFIG_PATH` and `tmp_path`, no new fixtures).
- **Test Cases**:
  - test_import_ignored_roms_defaults_to_empty_dict: a fresh Config has `{}`.
  - test_import_ignored_roms_roundtrips_through_save_and_load: `{"gba": ["/roms/a.gba", "/roms/b.gba"]}` survives save then load, which guards against the key being dropped on rewrite (#499).
  - test_import_ignored_roms_omitted_from_file_when_empty: an empty dict is not written to the TOML.
- **Edge Cases**:
  - Several consoles with separate lists keep their own entries.
  - Paths with spaces and backslashes round-trip unchanged.
  - A config written before this change (no key) loads with `{}`.
- **Integration Points**:
  - Renderer has no JS test runner, so the filter in `scanRoms`, `ignoreRoms`, the results UI and the settings panel are verified by the manual checks in step 7 (ignore row, ignore selected, rescan hides them, persists across restart, unignore restores, files and imported games untouched).
  - Keep the filtering decision a small pure helper in ignoredRoms.ts (`filterIgnored(roms, ignoredSet)`) so a runner can cover it later.
  - Run `make test-changed` after step 1; full `make test` in ship.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (`import_ignored_roms` in emusync.toml, new Config field).

## Not in this plan
Syncing ignores across devices; ignoring by filename; ignoring whole folders (the existing session-only folder ignore is unchanged); ignored-count badge elsewhere.

## Log
