# Handoff: #644 Redesign console import modal with optional network folder and share matching

## Metadata
- Issue: #644
- Branch: feature/644-console-import-share-matching
- PR: none
- Status: implementing
- Created: 2026-10-30
- Fix attempts: 0

## 1. Issue
### Summary
Compact the console import modal top section into one Locations block (local + optional network folder), remove the ROM source toggle, and validate network folders across devices via a marker-file share ID, auto-linking existing games.
### Motivation
Top section is tall; ROM source toggle is redundant; exact-string import_remote_path (#642) cannot match per-device mount paths.
### Proposed Behavior / Steps to Reproduce
See https://github.com/alekoHalkias/Emusync/issues/644
### Affected Area
console-import/ (ResultsStep, useConsoleImport, helpers, resolveRomPaths), LibraryImport.tsx, server/api/devices.py, store + migration, new IPC + emusync.d.ts
### Acceptance Criteria
See issue #644.

## 2. Design
### Scope: backend + ui
### Backend Changes: consoles.network_share_id column + migration; share register/lookup and auto-link-by-filename endpoints; #643 closed as superseded: no import_remote_path on main, nothing to remove; schema migration is v30
### UI Changes: Locations block in ResultsStep, remove romSource, per-ROM source inference, marker read/write IPC + d.ts, chip + toast
### Plan Target: both
### Sub-issues: none
### Difficulty: 7/10
### Backwards Compatibility: non-breaking (additive column; import_remote_path ignored not dropped). PR #643 closed as superseded (user decision); main has no import_remote_path, migration is v30, LibraryImport.tsx needs no remote-path removal.

## 3. Frontend Plan
### Design Alignment: settings-form row pattern (#629), inline chip and status line
### Visual Pattern: Locations block with collapsed folder list
### Recommendations: derive romSource from networkRoot so downstream code is untouched; new hook useNetworkShare

## 4. Backend Plan
### Design Alignment: additive consoles column per schema-evolution recipe; preserve-on-None PUT field; one thin read route
### Backend Pattern: Store method + thin route
### Recommendations: auto-link done client-side via existing scan linkedSlug + resolveImportPaths; server only registers/exposes share IDs

## 5. Merged Plan
### Conflicts Resolved: docs overlap merged into one step; API shape aligned; backend-first ordering
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_network_rom.py
### Test Cases: v29->v30 migration; PUT stores share id; PUT omitting preserves; shares lists other devices only; match/mismatch data
### Edge Cases: blank ids omitted; empty list; 403 on other device; fresh DB stamp
### Integration Points: client logic covered by manual step 10; shareStatus kept pure

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/644-console-import-share-matching.md
- bplan 1: files models.py, schema.py, consoles.py; reuses _try pattern and consoles SQL literals; no new code
- bplan 2: files consoles.py; reuses join pattern of get_network_source_for_game; new query because no cross-device console lookup exists
- bplan 3: files api/devices.py; reuses update_device_console exclude_none loop; new route because nothing lists other devices' consoles
- bplan 4: files tests; reuses client fixture and AUTH
- bplan 5: files ARCHITECTURE.md, CLAUDE.md

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
- 2026-10-30 issue: workflow initialized
- 2026-10-30 design: scope=backend+ui, plan_target=both, difficulty=7/10, breaking=no; #643 closed as superseded
- 2026-10-30 bplan: 5 steps written, backend_pattern=additive column + share-peer lookup; auto-link client-side
- fplan 1: files files.ts, preload.ts, emusync.d.ts; reuses files:exists handler pattern; new handler, no marker code exists
- fplan 2: files api.ts; reuses _fetch, device console wrappers; new getConsoleShares + getDeviceId accessor
- fplan 3: files useNetworkShare.ts (new); reuses api wrappers and window.emusync.files; separate file as useConsoleImport exceeds 300 lines
- fplan 4: files useConsoleImport.ts; reuses scanRoots/dedupeAndLink linkedSlug, resolveImportPaths; importOne extracted, linkShareGames new
- fplan 5: files ResultsStep.tsx; reuses folder list markup and vm handlers; inline chip + disclosure
- fplan 6-8: design guide, manual verification, docs
- 2026-10-30 fplan: 8 steps written, visual_pattern=Locations block + chip
- 2026-10-30 merge: 3 conflicts resolved, 0 unresolved; merged plan tools/plans/644-merged.md (11 steps)
- tplan 4: files src/tests/test_network_rom.py; reuses client fixture, AUTH, _device_auth, v28->v29 migration pattern; no new test infra
- 2026-10-30 tplan: test_file=src/tests/test_network_rom.py, 5 test cases defined
- 2026-10-30 implement: started; Status set implementing in merged, bplan, fplan plans and handoff (hook reads first glob match)
- 2026-10-30 implement: step 1 done (network_share_id column, v30 migration)
- 2026-10-30 implement: step 2 done (list_console_shares store method)
- 2026-10-30 implement: step 3 done (shares route, share id in console GET/PUT)
- 2026-10-30 implement: step 4 done (5 backend tests)
- 2026-10-30 implement: step 5 done (files:ensure-share-marker IPC; tsc errors shown are pre-existing)
- 2026-10-30 implement: step 6 done (getConsoleShares, getDeviceId, share id type)
