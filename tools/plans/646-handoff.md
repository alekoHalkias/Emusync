# Handoff: #646 Add ignore list for ROMs in console import

## Metadata
- Issue: #646
- Branch: feature/646-console-import-ignore-list
- PR: #649
- Status: shipped
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Ignore individual ROMs in the console import results so they stop reappearing; an Ignored games button in console settings lists them and allows unignoring.
### Motivation
Unwanted files in ROM folders reappear on every scan; the existing folder ignore is session-only.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/646
### Affected Area
console-import/ (ResultsStep, useConsoleImport, helpers), ConsoleFoldersModal.tsx, persistence for the ignore list
### Acceptance Criteria
See issue #646.

## 2. Design
### Scope: ui only
### Backend Changes: none (per-device config key import_ignored_roms[console] = [paths], decided by user: per device, by path)
### UI Changes: per-row Ignore + Ignore selected in results; scan filters ignored paths; Ignored games button/list in ConsoleFoldersModal with Unignore; reset in ServerStatusButton clears the key
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: non-breaking, new optional config key. PR #645 touches the same console-import files; rebase after it merges.

## 3. Frontend Plan
### Design Alignment: row action + inline list-editor pattern, immediate apply
### Visual Pattern: per-row Ignore, Ignore selected, inline Ignored games panel in ConsoleFoldersModal
### Recommendations: store under import_ignored_roms in toml; requires a config.py field because unknown keys are dropped (#499); same defect exists for import_network_folder in PR #645

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_config_roundtrip.py
### Test Cases: defaults empty; round trip; omitted when empty
### Edge Cases: multiple consoles; spaces/backslashes; pre-existing config without key
### Integration Points: renderer logic verified manually (step 7); filterIgnored kept pure for a future runner

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/646-import-ignore-list.md
- fplan 1: files config.py, test_config_roundtrip.py; reuses import_rom_source field pattern
- fplan 2: files console-import/ignoredRoms.ts (new); reuses config.load/save read-modify-write; shared by wizard and modal
- fplan 3: files useConsoleImport.ts; reuses scanRoms pipeline; ignoreRoms new (nothing persistently removes entries)
- fplan 4: files ResultsStep.tsx; reuses row markup and selected set
- fplan 5: files ConsoleFoldersModal.tsx, IgnoredGamesPanel.tsx (new); reuses list-editor markup; separate panel keeps modal under 300 lines
- fplan 6: files ServerStatusButton.tsx; reuses existing reset line
- fplan 7-8: manual verification, docs

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: shipped
### PR: #649
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
- 2026-10-31 fplan: 8 steps written, visual_pattern=row action + inline unignore panel
- tplan 1: files src/tests/test_config_roundtrip.py; reuses monkeypatch CONFIG_PATH + tmp_path pattern; no new fixtures
- 2026-10-31 tplan: test_file=src/tests/test_config_roundtrip.py, 3 test cases defined
- 2026-10-31 implement: started
- 2026-10-31 implement: step 1 done (Config.import_ignored_roms + 3 round-trip tests)
- 2026-10-31 implement: step 2 done (ignoredRoms.ts accessor + filterIgnored)
- 2026-10-31 implement: step 3 done (ignored set, scan filter, ignoreRoms)
- 2026-10-31 implement: step 4 done (row Ignore, Ignore selected, ignored count line)
- 2026-10-31 implement: step 5 done (IgnoredGamesPanel in ConsoleFoldersModal)
- 2026-10-31 implement: step 6 done (reset clears import_ignored_roms)
- 2026-10-31 implement: step 8 done (ARCHITECTURE.md section; CLAUDE.md rule added in step 1)
- 2026-10-31 implement: step 7 done (GUI behavior confirmed by user)
- 2026-10-31 ship: tests pass (566 passed, 3 skipped)
