# Handoff: #745 Install standalone emulators from the import wizard

## Metadata
- Issue: #745
- Branch: feature/745-install-standalone-emulators
- PR: #748
- Status: shipped
- Created: 2026-11-16
- Fix attempts: 0

## 1. Issue
### Summary
Offer in-app installation of standalone emulators (PCSX2, Dolphin, Azahar, mGBA, RPCS3) from the console import wizard when no compatible emulator is detected.
### Motivation
PS2, 3DS and Switch need a standalone emulator; #744 added core install but standalones only get download links.
### Proposed Behavior / Steps to Reproduce
Linux with Flatpak: `flatpak install --user flathub <app-id>`, re-run detection, continue the wizard. Otherwise fall back to the download link.
### Affected Area
`src/cli/consoles_data.py` (read only), `src/gui/electron/emulator/`, `src/gui/renderer/src/components/console-import/EmulatorStep.tsx`.
### Acceptance Criteria
- [ ] On Linux with Flatpak, a missing standalone emulator can be installed from the wizard and is detected afterwards
- [ ] Without Flatpak, or on Windows, the wizard falls back to the download link
- [ ] Install progress and failures are shown in the wizard
- [ ] No elevated privileges are requested (user-level installs only)

## 2. Design
### Scope: UI only (Electron main + renderer)
### Backend Changes: none. `flatpak_id` already in `consoles_data.py` standalones and in `rt.cachedConsoleDefs`.
### UI Changes:
- `detect.ts:coreInstallTargets` returns `standalones: [{id, label, flatpakId}]` (Linux, `flatpak` available, app not yet installed, def has `flatpak_id`).
- New `emulator/installFlatpak.ts` + IPC `emulator:installFlatpak(consoleKey, flatpakId)`: validates the id against that console's standalones; `execFile` `flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo`, then `flatpak install --user -y --noninteractive flathub <id>`; long timeout; returns `{ok}|{ok:false,error}` like `installCore`.
- `preload.ts` + `emusync.d.ts` expose the channel; `useConsoleImport.ts` gets `installFlatpak` that re-runs detection on success.
- `EmulatorStep.tsx`: "Install (Flatpak)" row per standalone beside `CoreInstallList`, spinner while busy, error text on failure.
### Plan Target: fplan
### Sub-issues: none (Windows installer execution dropped; links cover it)
### Difficulty: 3/10
### Backwards Compatibility: non-breaking; additive IPC field and channel only.

## 3. Frontend Plan
### Design Alignment: fits "Empty state with actions (#744)"; no guide change.
### Visual Pattern: label + btn btn-ghost Install rows, spinner while busy, 12px danger error; shares markup with CoreInstallList.
### Recommendations: none

## 4. Backend Plan
### Design Alignment: n/a
### Backend Pattern: n/a
### Recommendations: n/a

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_emulator_suggestions.py
### Test Cases: test_flatpak_ids_are_app_ids (flatpak_id allowlist format)
### Edge Cases: no flatpak_id (Eden), flatpak missing / non-Linux, rejected renderer id (manual)
### Integration Points: manual wizard install of mGBA Flatpak on Linux; make lint + tsc
### Outline:
Frontend
- 1. detect.ts: install.standalones (Flatpak-installable, not yet installed) via hoisted getFlatpakList; types + NO_INSTALL updated
- 2. installFlatpak.ts + IPC emulator:installFlatpak: allowlisted id, user-level flathub remote-add + install, no shell/sudo
- 3. EmulatorStep.tsx: shared install-row list for cores and Flatpak emulators; hook installFlatpak re-detects on success
Tests
- 4. test_emulator_suggestions.py: flatpak_id format check; manual wizard script
Docs
- 5. CLAUDE.md #744 bullet + ARCHITECTURE.md IPC list
### Summary: The import wizard can install a missing standalone emulator as a user-level Flathub Flatpak on Linux and continue; everything else keeps the download links.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/745-install-standalone-emulators.md
- [done] Step 1: detect.ts, emusync.d.ts, useConsoleImport.ts - reuses coreInstallTargets + hoisted getFlatpakList; no new code.
- [done] Step 2: installFlatpak.ts (new), ipc.ts, preload.ts, emusync.d.ts - reuses installCore.ts shape; new file because nothing runs flatpak today.
- [done] Step 3: EmulatorStep.tsx, useConsoleImport.ts - generalises CoreInstallList rows; installFlatpak hook fn mirrors installCore.
- [done] Step 4: test_emulator_suggestions.py - flatpak_id format check; reuses existing test module.
- [done] Step 5: CLAUDE.md, ARCHITECTURE.md - docs only.

## 9. Review
### Findings:
- Low, EmulatorStep.tsx:21 - busy state per list; a Flatpak and a core install can run concurrently (both re-detect, same data). Accepted.
- Low, detect.ts:270 - flatpak list runs twice per emulator:detect (blocking execSync, tens of ms). Accepted.
### Blocked: no
### Blockers: none

## 10. Ship
### Status: shipped
### PR: #748
### Server Sync: done
### Doc Sync: done (CLAUDE.md + ARCHITECTURE.md in steps 2 and 5; GOTCHAS.md not needed)

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-11-16 issue: workflow initialized (existing issue #745)
- 2026-11-16 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
- 2026-11-16 fplan: 5 steps written, visual_pattern=empty-state action rows (#744)
- 2026-11-16 tplan: test_file=src/tests/test_emulator_suggestions.py, 1 test case defined
- 2026-11-16 implement: step 1 done (install.standalones from coreInstallTargets); deviation: flatpak list not memoised at module scope (would go stale after install); new uncached flatpakApps() helper shared by both functions
- 2026-11-16 implement: step 2 done (emulator:installFlatpak IPC)
- 2026-11-16 implement: step 3 done (shared InstallList for cores and Flatpak emulators); deviation: CoreInstallList replaced by InstallList + InstallOptions; Flatpak block shown above cores
- 2026-11-16 implement: step 4 done (flatpak_id app-id format test)
- 2026-11-16 implement: step 5 done (ARCHITECTURE.md IPC entry); deviation: CLAUDE.md part landed in step 2's commit (commit hook requires it when preload.ts changes)
- 2026-11-16 review: 2 findings, blocked=no
- 2026-11-16 ship: tests 755 passed, PR #748 opened, mergeable
- 2026-11-16 ship: server sync done
- 2026-11-16 ship: doc sync done in implement steps; no further changes
