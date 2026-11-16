# Handoff: #745 Install standalone emulators from the import wizard

## Metadata
- Issue: #745
- Branch: feature/745-install-standalone-emulators
- PR: none
- Status: designed
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
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: n/a
### Backend Pattern: n/a
### Recommendations: n/a

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD
### Outline: TBD
### Summary: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: TBD (written by /plan skills)

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
- 2026-11-16 issue: workflow initialized (existing issue #745)
- 2026-11-16 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
