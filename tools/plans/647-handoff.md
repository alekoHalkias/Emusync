# Handoff: #647 Fix missing network_share_id column on databases at schema v30

## Metadata
- Issue: #647
- Branch: feature/647-fix-network-share-id-migration
- PR: none
- Status: implementing
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Databases already at schema v30 (from closed #642/#643) skip #644's v30 migration, so consoles.network_share_id is missing and console queries fail.
### Motivation
Console settings shows no folders; GET /devices/{id}/consoles returns 500 on the server PC.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/647
### Affected Area
schema.py migration, consoles.py, ConsoleFoldersModal.tsx, test_network_rom.py
### Acceptance Criteria
See issue #647.

## 2. Design
### Scope: backend (+ one small UI step)
### Backend Changes: network_share_id ALTER moves to from_version < 31; _SCHEMA_VERSION = 31
### UI Changes: ConsoleFoldersModal shows an error on fetch failure instead of the empty-row message
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: non-breaking, idempotent ALTER

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: schema-evolution recipe, idempotent ALTER in a new v31 block
### Backend Pattern: migration only; no Store or API change
### Recommendations: never reuse a schema number a deployed branch may have stamped

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_network_rom.py
### Test Cases: v30-stamped db gains column; v29 test renamed; Store on v30-stamped db lists consoles
### Edge Cases: migration twice; db already has column; fresh stamps 31
### Integration Points: modal error state verified manually; restart server PC and check consoles endpoint

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/647-fix-network-share-id-migration.md
- bplan 1: files schema.py; reuses _try ALTER pattern; no new code
- bplan 2: files test_network_rom.py; reuses v29 hand-built table pattern and Store(tmpdir)
- bplan 3: files ConsoleFoldersModal.tsx; reuses msg-style muted text; new loadFailed flag because row null already means no row
- bplan 4: files CLAUDE.md, backend-design-guide.md

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
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=backend+small ui, plan_target=bplan, difficulty=2/10, breaking=no
- 2026-10-31 bplan: 4 steps written, backend_pattern=idempotent v31 migration
- 2026-10-31 tplan: test_file=src/tests/test_network_rom.py, 3 test cases defined (testing section written in the same plan)
- 2026-10-31 implement: started
- 2026-10-31 implement: step 1 done (network_share_id ALTER moved to v31, _SCHEMA_VERSION 31)
- 2026-10-31 implement: step 2 done (3 migration tests; Store-on-v30 test heals a real DB via DROP COLUMN)
- 2026-10-31 implement: step 4 done (CLAUDE.md schema rule; backend guide updated in bplan)
