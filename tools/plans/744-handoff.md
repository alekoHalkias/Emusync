# Handoff: #744 Link emulator suggestions and install missing RetroArch cores from the import wizard

## Metadata
- Issue: #744
- Branch: feature/744-emulator-install-suggestions
- PR: none
- Status: implementing
- Created: 2026-11-12
- Fix attempts: 0

## 1. Issue
### Summary
When the import wizard finds no compatible emulator/core, each suggestion gets a download/info link, and if RetroArch is installed but the console's core is missing, offer in-app core install from the RetroArch buildbot, then re-run detection.
### Motivation
The empty state is a plain-text list today; missing cores are the common case and cheap to fix automatically since RetroArch detection and core lib names already exist.
### Proposed Behavior / Steps to Reproduce
1. Links per suggestion (emulator site or Flathub), opened externally.
2. RetroArch detected (native or Flatpak) but no core: list the console's known cores with Install; download for platform/arch from buildbot, extract into detected `coresDir`, fetch `.info` if absent, re-run `emulator:detect`.
3. RetroArch absent: links only.
4. Errors shown inline; temp file + verify + move, no partial core left.
Out of scope: standalone emulator install (#745).
### Affected Area
- src/gui/renderer/src/components/console-import/EmulatorStep.tsx
- src/gui/electron/emulator/detect.ts, src/gui/electron/emulator/ipc.ts
- src/cli/consoles_data.py
- src/gui/renderer/src/emusync.d.ts
### Acceptance Criteria
- [ ] Each suggestion in the no-emulator state has a working external link
- [ ] With RetroArch installed and core missing, wizard offers installing the console's cores
- [ ] Installed core lands in detected cores dir (native and Flatpak); wizard advances without restart
- [ ] Linux and Windows core downloads both work
- [ ] Failed downloads show an error and leave no partial core file
- [ ] With RetroArch absent, only links are shown

## 2. Design
### Scope: ui (Electron main + renderer)
### Backend Changes: none. Core lists already reach Electron via `/system-defs` (`rt.cachedSystemDefs[sysKey].cores`, `consoleDef.systemKeys`, used in `detect.ts:160`).
### UI Changes:
- Electron main: new IPC `emulator:installCore` (buildbot URL per platform/arch, download to temp, extract zip, verify, move into detected RetroArch `coresDir`; fetch `.info` if absent; native and Flatpak). `emulator:detect` returns an extra optional field listing installable cores + target RetroArch when RetroArch is present but no option matched.
- Renderer: `EmulatorStep.tsx` empty state: suggestions get external links (keyword-to-URL map in renderer, opened via existing openExternal path), Install buttons for cores, re-run detection on success; inline errors.
- `emusync.d.ts`: new channel + extended detect return type.
### Plan Target: fplan
### Sub-issues: none (standalone emulator install is #745)
### Difficulty: 4/10
### Backwards Compatibility: non-breaking; detect gains an optional field only.

## 3. Frontend Plan
### Design Alignment: fits existing empty state; no new components or CSS classes.
### Visual Pattern: suggestions as `<a target="_blank">` (existing window open handler -> shell.openExternal); install rows = name + `btn btn-ghost` Install, `spinner` busy state, inline 12px danger error.
### Recommendations: add "Empty state with actions" line to the design guide (done in step 7). Scope narrowed to Linux x86_64 for core install (GUI RetroArch detection is Linux/.so only).

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_emulator_suggestions.py (new) + manual script in plan
### Test Cases: suggestion_links_cover_all_suggestions; core_libs_are_buildbot_safe; manual steps 1-6 (install, link, error, standalone-only, flatpak)
### Edge Cases: forged lib/coresDir rejected; buildbot 404; missing cores dir
### Integration Points: both detect call sites in useConsoleImport; shared art.ts:download unchanged
### Outline:
Frontend
- [done] 1 detect.ts/ipc.ts: coreInstallTargets (Linux x86_64 only) returned as detect `install`
- [done] 2 installCore.ts + emulator:installCore: buildbot download -> python zipfile extract -> .part + rename into coresDir, validated against detected targets
- [done] 3 preload.ts / emusync.d.ts: new channel + detect type
- [done] 4 useConsoleImport.ts: store install, installCore re-runs detection
- [done] 5 EmulatorStep.tsx: suggestion links + Install rows with spinner/inline error Deviation: links keyed by first word.
- 7 Docs: ARCHITECTURE.md, CLAUDE.md, design guide
Tests
- [done] 6 test_emulator_suggestions.py (2 cases) + lint/tsc + manual script Deviation: regex allows hyphens.
### Summary: The import wizard's no-emulator state links every suggestion and installs missing RetroArch cores in one click on Linux x86_64.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/744-emulator-install-suggestions.md
- [done] 1 detect.ts/ipc.ts: coreInstallTargets + detect `install` field. Reuses detectRetroArch, systemDefs core walk. New fn: nothing returns RA targets without an installed core.
- [done] 2 installCore.ts (new) + ipc.ts: emulator:installCore. Reuses art.ts:download, runtime PYTHON (stdlib zipfile). New module: no existing extract/install code.
- [done] 3 preload.ts, emusync.d.ts: channel + detect type. Reuses emulator namespace.
- [done] 4 useConsoleImport.ts: store install, installCore -> re-run detectEmulators. Reuses detectEmulators.
- [done] 5 EmulatorStep.tsx: links via keyword URL table + install rows. Reuses empty state markup, window open handler. New URL table: suggestions are free text in console_defs, schema change not justified. Deviation: links keyed by first word.
- [done] 6 Tests: per tplan. Deviation: regex allows hyphens.
- 7 Docs: ARCHITECTURE.md, CLAUDE.md, design guide.

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
- 2026-11-12 issue: workflow initialized; standalone install split to #745
- 2026-11-12 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-11-12 fplan: 7 steps written, visual_pattern=existing empty state + link list + ghost Install rows
- 2026-11-12 tplan: test_file=src/tests/test_emulator_suggestions.py, 2 test cases defined + manual script
- 2026-11-12 implement: step 1 done (coreInstallTargets + detect install field)
- 2026-11-12 implement: step 2 done (installCore.ts + emulator:installCore IPC)
- 2026-11-12 implement: step 3 done (preload + emusync.d.ts)
- 2026-11-12 implement: step 4 done (wizard install state + installCore re-detect)
- 2026-11-12 implement: step 5 done (suggestion links + core install rows)
- 2026-11-12 implement: step 6 done (test_emulator_suggestions.py, 2 passing)
