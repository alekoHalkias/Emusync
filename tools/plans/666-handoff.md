# Handoff: #666 Skip name-duplicate ROMs of games already configured on this device when importing

## Metadata
- Issue: #666
- Branch: feature/666-skip-duplicate-roms-on-import
- PR: none
- Status: planned
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Name-duplicate ROMs of games already configured on this device are reported as "linked from another device" and re-linked on every open.
### Motivation
Wizard and Refresh counts are wrong; rom_path may be rewritten to duplicate files.
### Proposed Behavior / Steps to Reproduce
GBA share with Pokemon_Emerald_Crest.gba alongside Pokemon Emerald Crest.gba; open Review and import.
### Affected Area
console-import/helpers.ts dedupeAndLink; useConsoleImport.ts linkShareGames; scanNewRoms.ts.
### Acceptance Criteria
- Name match to a game with a ROM on this device is skipped.
- Genuinely other-device games still link.

## 2. Design
### Scope: ui (renderer only)
### Backend Changes: none
### UI Changes: dedupeAndLink skips cross-matches already configured on this device
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: no breaking changes

## 3. Frontend Plan
### Design Alignment: no visual change
### Visual Pattern: none
### Recommendations: none

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (no renderer harness)
### Test Cases: manual - GBA share with underscore duplicates reports no linked games
### Edge Cases: game with no ROM on this device but present on another still links
### Integration Points: wizard (useConsoleImport) and scanNewRoms both call dedupeAndLink
### Outline
Frontend: helpers.ts dedupeAndLink - crossMatch slug already in thisDeviceConfigs -> existingGameSlug (skipped).
Tests: no renderer harness; tsc + manual check. Python suite unaffected.
Docs: none.
### Summary
Name-duplicate ROMs of games already configured on this device are skipped instead of re-linked on every wizard open.

## 7. Test Design
TBD

## 8. Implementation Steps
1. helpers.ts dedupeAndLink: crossMatch slug in thisDeviceConfigs -> existingGameSlug. Reuses existing skip path; no new code.
2. Tests: no renderer harness; manual + tsc.
3. Docs: none.

## 9. Review
TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=ui, plan_target=fplan, difficulty=2/10, breaking=no
- 2026-10-31 fplan: 3 steps written, visual_pattern=none
- 2026-10-31 tplan: test_file=none, 1 manual case + 1 edge case defined
