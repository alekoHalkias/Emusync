# Handoff: #753 Replace launch command field with an emulator picker in game and console settings

## Metadata
- Issue: #753
- Branch: feature/753-emulator-picker
- PR: none
- Status: implementing
- Created: 2026-11-20
- Fix attempts: 0

## 1. Issue
### Summary
Replace GameConfig's free-text launch command with an Emulator dropdown of emulators detected on this device for the game's console; build the command from emulator + ROM path (`%ROM%`). Same picker in ConsoleFoldersModal for all games on the console. "More..." opens an inline install panel.
### Motivation
Hand-typed commands are error-prone; wizard already detects emulators, builds commands, and installs cores/Flatpaks (#744, #745).
### Proposed Behavior / Steps to Reproduce
User decisions (2026-11-20):
- Custom command entry in the dropdown shows the text field; stored commands that match no detected emulator open as Custom, unchanged.
- Game-level change affects only that game (launch cmd + save/state paths). Console-level picker in console settings updates `device_emulator` and rebuilds all of the console's games on this device (skip Custom).
- If new emulator's save/state location differs: prompt with the new save path and new state path, offer to move existing saves (safe temp+swap move). No = keep files, use new paths.
- Warn on switch that old emulator's save may not load in the new one.
- "More..." = inline install panel reusing wizard flow (installCore, installFlatpak, SUGGESTION_LINKS); re-detect after install.
### Affected Area
GameConfig.tsx, ConsoleFoldersModal.tsx, console-import/EmulatorStep.tsx, gui/electron/emulator/ (detect.ts, scan.ts, installCore.ts, installFlatpak.ts), PUT /games/{slug}/device, console device update.
### Acceptance Criteria
See issue #753.

## 2. Design
### Scope: UI only (Electron main + React). No backend.
### Backend Changes: none. PUT /games/{slug}/device already takes launch_command/save_path/state_path; console row already has device_emulator.
### UI Changes:
- emulator/scan.ts: extract per-ROM save/state/launch resolution from the scanForRoms loop into a reusable function; new IPC to resolve paths for one ROM + one detected option (add to preload.ts and emusync.d.ts).
- New IPC to move save/state files to new paths, reusing the rename / EXDEV copy+verify approach of rom:moveToConsoleFolder (sync/rom.ts). Never delete the source before the copy is verified.
- EmulatorPicker component: detected options + "Custom command" (shows text field) + "More..." (inline install panel). Used in GameConfig.tsx (replaces launch field) and ConsoleFoldersModal.tsx (replaces label-only select).
- Extract the install panel (installCore/installFlatpak/SUGGESTION_LINKS) from console-import/EmulatorStep.tsx for sharing; re-detect after install.
- Switch dialog: save compatibility warning; if save/state paths change, show new paths and offer to move saves.
- Console-level apply: update device_emulator, rebuild launch/save/state for each of this device's games on the console (skip Custom), same dialog.
- Matching a stored command to a detected option: compare execPath (+ corePath for RetroArch); no match = Custom.
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 6/10
### Backwards Compatibility: non-breaking. New IPC only; unmatched commands kept as Custom. Shared-layout consoles: per-game switch changes launch cmd + state path only; card move only from console-level picker.
## 3. Frontend Plan
### Design Alignment: settings-form input-group + plain select; install rows reuse wizard InstallOptions; switch confirm is a standard Modal (Cancel / Keep files / Move saves).
### Visual Pattern: new guide entry "Emulator picker (#753)" in .claude/frontend-design-guide.md.
### Recommendations: console-level picker hides Custom; GameConfig queues the save move and runs it on Save so a cancelled form never leaves files moved.

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_move_saves.py (Node-driven, skips below Node 22.18)
### Test Cases: file move; folder move; state files moved individually; same-path no-op; missing source no-op.
### Edge Cases: destination exists never overwritten (skipped); state name collision keeps colliding file in source; blank from-paths skip that half.
### Integration Points: test_emulator_suggestions.py unchanged (SUGGESTION_LINKS stays in EmulatorStep.tsx); existing device PUT tests cover persisted fields; tsc both projects + make lint; 7-step manual script in plan.
### Outline:
Frontend
- 1 scan.ts: extract resolveRomEntry (no behavior change)
- 2 IPC emulator:resolveGame (one ROM + one emulator -> launch cmd, save/state paths)
- 3 IPC emulator:moveSaves in emulator/moveSaves.ts (safe move, never overwrite)
- 4 EmulatorStep.tsx: export InstallOptions + SuggestionLinks
- 5 EmulatorPicker.tsx: detected options, Custom command, More... install panel; matchOption
- 6 emulatorSwitch.ts: planSwitch / previewConsoleSwitch / applyConsoleSwitch (shared-layout and blank-save rules)
- 7 EmulatorSwitchModal.tsx: compatibility warning, new paths, Cancel / Keep files / Move saves
- 8 GameConfig.tsx: Emulator field replaces launch input; move runs on Save
- 9 ConsoleFoldersModal.tsx: picker replaces label select; console-wide apply skipping Custom games
Tests
- 10 test_move_saves.py (5 cases + 3 edge cases), suggestion test regression, tsc/lint, manual script
Docs
- 11 ARCHITECTURE.md + CLAUDE.md
### Summary: Game and console settings choose an installed emulator from a dropdown (Custom and More... included), build the launch command and save/state paths from it, warn about save compatibility and offer to move existing saves to the new emulator's location.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/753-emulator-picker.md (11 steps). Per-step summary:
- [done] 1: scan.ts - extract resolveRomEntry from runEmulatorScan loop; reuses existing body; no new logic.
- [done] 2: emulator/ipc.ts, preload.ts, emusync.d.ts - emulator:resolveGame; reuses step 1; new channel because scan only resolves folders.
- 3: emulator/moveSaves.ts (+ipc, preload, d.ts) - emulator:moveSaves; reuses rom:moveToConsoleFolder rename/EXDEV pattern; new file because rename-game-files is base-name bound and files.ts near 300 lines.
- 4: console-import/EmulatorStep.tsx - export InstallOptions (props not vm) + SuggestionLinks; SUGGESTION_LINKS stays for test_emulator_suggestions.py.
- 5: game-config/EmulatorPicker.tsx - useEmulatorOptions, matchOption, EmulatorPicker; reuses detect/install IPC and step 4; new because no dropdown over detected options exists.
- 6: game-config/emulatorSwitch.ts - planSwitch, previewConsoleSwitch, applyConsoleSwitch; reuses listMyGameDevices/getGameDevice/setGameDevice and layout helpers; new to keep GameConfig from growing and share with console modal.
- 7: game-config/EmulatorSwitchModal.tsx - warning + new paths + move choice; reuses Modal; new because SyncConflictModal is conflict-specific.
- 8: GameConfig.tsx - Emulator field replaces launch input, queued move on Save; reuses steps 5-7.
- 9: ConsoleFoldersModal.tsx - picker replaces label select, console-wide apply; reuses steps 5-7 and save().
- 10: tests (tplan). 11: docs (ARCHITECTURE.md, CLAUDE.md).

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-11-20 issue: workflow initialized; user decisions recorded in section 1
- 2026-11-20 design: scope=ui, plan_target=fplan, difficulty=6/10, breaking=no
- 2026-11-20 fplan: 11 steps written, visual_pattern=settings select + inline install panel + switch confirm modal
- 2026-11-20 tplan: test_file=src/tests/test_move_saves.py, 8 test cases defined
- 2026-11-20 implement: step 1 done (extract resolveRomEntry from emulator scan)
- 2026-11-20 implement: step 2 done (add emulator:resolveGame IPC)
- 2026-11-20 implement: step 2 done (add emulator:resolveGame IPC)
