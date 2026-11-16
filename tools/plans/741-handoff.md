# Handoff: #741 Rebuild runtime venv when system Python version changes

## Metadata
- Issue: #741
- Branch: feature/741-runtime-venv-python-version
- PR: none
- Status: designed
- Created: 2026-11-16
- Fix attempts: 0

## 1. Issue
### Summary
On Steam Deck, the AppImage runtime venv (`~/.cache/emusync/runtime/.cache/.venv`) was built under Python 3.13; SteamOS upgraded `/usr/bin/python3` to 3.14. The venv's `bin/python` symlinks to the host interpreter, so it no longer sees `lib/python3.13/site-packages` and every CLI call fails with `ModuleNotFoundError: No module named 'click'`.
### Motivation
Play (GUI and Steam shortcut) is completely broken after a routine OS update until the user deletes the cache by hand.
### Proposed Behavior / Steps to Reproduce
Build the runtime venv under Python X.Y, upgrade system python3 to X.(Y+1), run `~/.cache/emusync/runtime/src/emusync --help`: fails. Expected: the venv is rebuilt automatically; if that is impossible, a clear error instead of a silent fallback to bare `python3`.
### Affected Area
`src/gui/electron/runtimeSetup.ts` (`provision`, stamps), `src/emusync` (bash launcher), `src/gui/electron/runtime.ts` (`PYTHON`, `LAUNCHER`, read-only).
### Acceptance Criteria
- [ ] Runtime stamp includes system Python version (and path); mismatch triggers venv rebuild.
- [ ] After a SteamOS Python upgrade, Play works without manual cache deletion.
- [ ] Launcher does not silently use venv-less `python3` when a venv exists but is unusable; clear error.
- [ ] Regression test for the stamp/mismatch logic where testable.

## 2. Design
### Scope: backend (bash launcher) + Electron main provisioning; no renderer, IPC, API, schema or config changes.
### Backend Changes:
- `src/emusync` launcher: before exec, detect a stale venv (venv `bin/python`'s `major.minor` has no matching `lib/pythonX.Y` dir, or equivalently `pyvenv.cfg` `version` major.minor differs from the interpreter). On mismatch, self-heal: `python3 -m venv --clear <venv>` + `<venv>/bin/python -m pip install -q -r $SCRIPT_DIR/requirements.txt`, logging to stderr. If the rebuild fails, print a clear error naming the Python versions and exit non-zero; never fall through to bare `python3` when a venv dir exists. The bare-`python3` fallback stays only for the no-venv case. This is the path that matters: Steam shortcuts target the launcher directly and never run Electron's `ensureRuntime()`.
- `src/gui/electron/runtimeSetup.ts` `provision()`: record the system `python3` `major.minor` + resolved path in a `.python-stamp` (alongside `.version` / `.requirements-hash`); on mismatch `rmSync` the venv (or `venv --clear`) so the existing create + pip path rebuilds it. Reuses the existing `run()` helper and failure-writes-no-stamp retry semantics.
### UI Changes: none (Electron main only, no renderer/IPC).
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: non-breaking. Existing runtimes lack `.python-stamp`; treat missing stamp as "check the venv" (compare versions) rather than forcing a rebuild on every upgrade. Dev checkouts (`.venv`, `.cache/.venv`) get the same launcher check, which only acts on a genuine version mismatch.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

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
- 2026-11-16 issue: workflow initialized
- 2026-11-16 design: scope=backend+electron-main, plan_target=bplan, difficulty=3/10, breaking=no
