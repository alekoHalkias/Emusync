# Handoff: #677 Let the AppImage add Steam shortcuts without EMUSYNC_SCRIPT

## Metadata
- Issue: #677
- Branch: feature/677-appimage-steam-launcher
- PR: none
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
AppImage v0.8.6 refuses Steam add with an EMUSYNC_SCRIPT error (#676 guard).
### Motivation
Users should not need an env var.
### Proposed Behavior / Steps to Reproduce
Run AppImage with EMUSYNC_SCRIPT unset; add a game to Steam.
### Affected Area
src/gui/electron/runtime.ts, steam.ts, game.ts, server.ts, paths.ts; src/gui/package.json build config
### Acceptance Criteria
- Add to Steam works without EMUSYNC_SCRIPT
- Target survives restart and updates
- Error is actionable in the GUI
- Dev checkout unchanged

## 2. Design
### Scope: electron main + requirements split + CI smoke check + Python guard test
### Backend Changes: none to Python code; requirements.txt split into runtime and dev
### UI Changes: none visible; errors reuse Setup preflightError and addGame {ok,error}
### Plan Target: fplan
### Sub-issues: none
### Difficulty: 7/10
### Backwards Compatibility: not breaking; dev checkout and EMUSYNC_SCRIPT unchanged; stale /tmp/.mount_* shortcuts replaced on next add

## 3. Frontend Plan
### Design Alignment: no new UI; reuses preflightError and {ok,error}
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
### Test File: src/tests/test_bundle.py (Python); electron manual
### Test Cases: bundle covers all src packages; requirements split; manual first launch, Add to Steam, version bump
### Edge Cases: missing python3/venv/offline retry; cache wiped self-heals; concurrent callers share one run; dev/Windows no-op
### Integration Points: make test-changed/test; electron-vite build; release smoke step
### Outline
Frontend (electron): 2 extraResources; 3 runtime.ts; 4 runtimeSetup.ts; 5 server.ts/steam.ts.
Backend/CI: 1 requirements split; 7 release smoke check; 8 docs.
Tests: 6 test_bundle.py + manual build.
### Summary: Bundle the CLI in the AppImage and provision a stable runtime dir (same layout as a checkout) on first launch, so Steam, server and sync work with no repo.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps
1. requirements split (runtime vs dev); install.sh/Makefile/CI point at dev file.
2. package.json extraResources bundles the CLI to resources/src.
3. runtime.ts: RUNTIME_DIR under cacheDir for packaged AppImage; delete LAUNCHER_STABLE.
4. runtimeSetup.ts (new): ensureRuntime() copies src, builds venv, stamps by version and requirements hash, memoized, retry on failure.
5. server.ts/steam.ts: await ensureRuntime(); drop #676 guard.
6. test_bundle.py: bundle covers all src packages; requirements split.
7. release.yml: AppImage smoke check for resources/src/emusync.py.
8. Docs: CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md.

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
- 2026-11-01 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-11-01 fplan: 5 steps written, visual_pattern=none
- 2026-11-01 tplan: test_file=none, 3 manual cases defined
- 2026-11-01 plan redone: bundle CLI via extraResources + cache runtime dir, 8 steps, difficulty 7/10
- 2026-11-01 implement: step 1 done (requirements split; release.yml line 52 build job left on runtime file)
- 2026-11-01 implement: steps 2-3 done (extraResources, RUNTIME_DIR/USE_RUNTIME_DIR in runtime.ts, guard removed)
