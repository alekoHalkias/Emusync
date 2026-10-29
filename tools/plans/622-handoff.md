# Handoff: #622 Allow moving local ROMs outside the console default folder

## Metadata
- Issue: #622
- Branch: feature/622-move-local-rom
- PR: none
- Status: implemented
- Created: 2026-10-29
- Fix attempts: 0

## 1. Issue
### Summary
Let a local ROM outside the console default local folder be moved into it, reusing the network localize flow.
### Motivation
Refresh locations finds games outside the managed folder; no GUI way to bring them in.
### Proposed Behavior / Steps to Reproduce
"Move to console folder" action for local ROMs outside the default folder; copy, verify, remove original, update path and launch command.
### Affected Area
NetworkRomPanel.tsx, electron/sync/rom.ts, localizeJob, cli/netrom.py, PUT /games/{slug}/device
### Acceptance Criteria
See issue #622.

## 2. Design
### Scope: ui (Electron IPC + React)
### Backend Changes: none; reuse PUT /games/{slug}/device
### UI Changes: IPC rom:moveToConsoleFolder (rom.ts, preload.ts, emusync.d.ts) modelled on rom:localize; button in NetworkRomPanel/GameConfig for local ROMs outside device_local_folder
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: no breaking change (additive IPC)

## 12. Log
- 2026-10-29 issue: workflow initialized
- 2026-10-29 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-10-29 fplan: 5 steps written, visual_pattern=reuse btn + msg row

## 3. Frontend Plan
See tools/plans/622-move-local-rom.md

## 8. Implementation Steps
1 rom.ts handler (reuses consoleLocalFolder, copyWithProgress; new handler since localize is network-only)
2 preload.ts + emusync.d.ts (reuses delocalize shape)
3 NetworkRomPanel + GameConfig (reuses console lookup, busy/msg state)
4 tests: none, manual
5 docs ARCHITECTURE.md
- 2026-10-29 tplan: test_file=none (manual + tsc), 4 cases defined

## 6. Testing Plan
### Test File: none (no harness for Electron main); tsc + make test-changed
### Test Cases: move succeeds; inside-folder hides button
### Edge Cases: dest exists; EXDEV; no console folder
### Integration Points: PUT /games/{slug}/device
- 2026-10-29 implement: steps 1-5 done (IPC rom:moveToConsoleFolder, preload/d.ts, MoveLocalRomPanel, docs)
