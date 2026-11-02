# Handoff: #725 Link Switch game saves for Pokemon Legends Z-A across Steam Deck and Arch

## Metadata
- Issue: #725
- Branch: feature/725-switch-legends-za-save-link
- PR: #726
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 1

## 1. Issue
### Summary
Pokemon Legends: Z-A Switch saves do not link between a Steam Deck and an Arch machine.
### Motivation
Cross-device save sync is the core feature; this title is not syncing.
### Proposed Behavior / Steps to Reproduce
Import the game on both devices against the same server, launch on each; saves stay separate.
### Affected Area
src/cli/run_switch.py, src/cli/detect.py, src/gui/electron/switchtitledb.ts, switch_title_id storage (store/games.py, api/games.py).
### Acceptance Criteria
- [ ] Root cause identified (title ID per device, Eden save root in use).
- [ ] Same title ID resolved on both devices or self-healed.
- [ ] Save syncs both directions.
- [ ] Regression test.

## 2. Design
### Scope: backend (CLI sync path); investigation-first. Expanded: post-game push detached into a background process (user request).
### Backend Changes: Trace why Legends Z-A fails to link. Findings so far: (1) self-heal in cli/run.py only stores the title ID when `switch_title_id` is blank, so a wrong or stale stored ID is never corrected; (2) `_resolve_written_switch_save` skips adoption when more than one title folder was touched in a session; (3) switchtitledb.ts exact-name match may miss a recent title or return a different ID; (4) Eden roots limited to two fixed paths in run_switch.py. Fix will be the smallest change in the shared path (run_switch.py / run.py) once the cause is confirmed on the two devices.
### UI Changes: none expected
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: No schema, API, config or IPC change expected; no breaking change.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: run.py backfills switch_title_id only in two branches; skipped when save_path already set and server ID blank.
### Backend Pattern: reuse client.update_game backfill at the shared pre-reconcile point.
### Recommendations: wrong-stored-ID case is out of scope; root cause on user data unconfirmed.

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_switch_save_sync.py, src/tests/test_run_reconcile.py
### Test Cases: helper returns ID for hex folder; run_game backfills when save_path set and server ID blank; no update when ID stored
### Edge Cases: non-hex folder name returns ""; update_game failure only warns
### Integration Points: client.update_game -> PUT /games/{slug} -> store.update_game_switch_title_id
### Outline:
Backend: (1) helper _switch_title_id_from_save_path in run_switch.py; (2) backfill in run.py before reconcile; (4) GOTCHAS line.
Tests: helper + run_game backfill tests.
### Summary: Run the post-game push in a detached background process, and publish the Switch title ID to the server when the device already has a learned save folder but the server ID is blank.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps:
1. helper _switch_title_id_from_save_path - files: src/cli/run_switch.py; reuses title-ID regex pattern; new because existing helper parses ROM filename.
2. backfill in run_game - files: src/cli/run.py; reuses client.update_game; no new code.
3. detach post-game work - files: src/cli/run.py, src/cli/run_offline.py; reuses existing post-launch block and finally path; new _detach_after_game because no fork/daemonize helper exists.
4. tests - src/tests/test_switch_save_sync.py, test_run_reconcile.py, plus a subprocess fork test.
5. docs - GOTCHAS.md, CLAUDE.md.

## 9. Review
### Findings: (1) correctness, GUI launch needed --no-detach - fixed F1.1; (2) correctness, join heartbeat before fork - fixed F1.2; (3) docs-stale ARCHITECTURE run.py row - fixed in doc sync.
### Blocked: no
### Blockers: none

## 10. Ship
### Status: shipped
### PR: #726
### Server Sync: done
### Doc Sync: done

## 11. Fix Attempts
### Attempt 1: GUI launch must pass --no-detach (exit = push done)
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=4/10, breaking=no
- 2026-11-01 bplan: 4 steps written, backend_pattern=reuse update_game backfill before reconcile
- 2026-11-01 tplan: test_file=test_switch_save_sync.py + test_run_reconcile.py, 3 test cases defined
- 2026-11-01 plan-update: added detached post-game push (fork+setsid, detach flag default off in-process), difficulty 5/10
- 2026-11-01 implement: step 1 done (_switch_title_id_from_save_path helper)
- 2026-11-01 implement: step 2 done (backfill title ID when save_path already known)
- 2026-11-01 implement: step 3 done (fork post-game push into a detached session)
- 2026-11-01 implement: step 4 done (backfill, helper and real-fork detach tests)
- 2026-11-01 implement: step 5 done (GOTCHAS + CLAUDE.md); all steps complete
- 2026-11-01 ship: tests pass (671), PR #726 opened
- 2026-11-01 implement: F1.1 done (GUI launch passes --no-detach)
- 2026-11-01 implement: F1.2 done (join heartbeat before fork)
- 2026-11-01 review: 3 findings, blocked=no (2 correctness fixed)
- 2026-11-01 ship: doc sync updated ARCHITECTURE.md (GOTCHAS.md, CLAUDE.md in step 5)
- 2026-11-01 ship: server sync done
- 2026-11-01 plan-update: root cause on Deck = .bak profile folder adopted; steps R1-R3 added
