# Handoff: #702 Quote emulator path in launch commands and parse them Windows-safely

## Metadata
- Issue: #702
- Branch: feature/702-launch-command-quoting
- PR: none
- Status: planned
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Generated launch commands embed exec_path unquoted; `emusync run` parses with POSIX shlex.split.
### Motivation
Emulator paths with spaces or Windows backslashes produce a broken argv.
### Proposed Behavior / Steps to Reproduce
Emulator at `/opt/My Emu/emu` or `C:\Program Files\Emu\emu.exe`; stored command `<exec> "%ROM%"`; `emusync run` fails.
### Affected Area
src/cli/console.py, src/gui/electron/emulator/scan.ts, src/cli/run.py
### Acceptance Criteria
- exec_path quoted wherever a launch command is built (Python and TS)
- run.py parses commands on Windows without losing backslashes
- previously stored unquoted commands with spaces still launch
- %ROM% substitution with spaces yields one argument
- regression tests

## 2. Design
### Scope: backend-only fix plus a one-line TS change
### Backend Changes: quote exec_path in console.py; run.py gets a `_split_launch_command` helper
### UI Changes: none (scan.ts string construction only)
### Plan Target: bplan
### Sub-issues: none
### Difficulty: low
### Backwards Compatibility: stored unquoted commands must keep working

## 3. Frontend Plan
### Design Alignment: n/a
### Visual Pattern: n/a
### Recommendations: n/a

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
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend (+1 TS string), plan_target=bplan, difficulty=3/10, breaking=no

## Plan summary (bplan)
- Step 1: src/cli/common.py; reuses shlex/shutil.which; new helper because nothing handles Windows or legacy unquoted exec paths.
- Step 2: src/cli/run.py, src/cli/run_offline.py; reuses _resolve_launch_command.
- Step 3: src/cli/console.py, src/gui/electron/emulator/scan.ts; quotes only.
- Step 4: tests, real files. Step 5: docs none.
- 2026-11-01 bplan: 5 steps written, backend_pattern=shared pure helper in cli/common.py
