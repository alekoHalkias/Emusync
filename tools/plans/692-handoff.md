# Handoff: #692 Harden CORS, PIN check, external URLs and archive restore safety

## Metadata
- Issue: #692
- Branch: feature/692-harden-cors-restore-safety
- PR: none
- Status: implemented
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Medium-severity hardening and data-safety defects from a code audit.
### Motivation
Cross-origin pages can reach an open local server; PIN compare is not constant-time; openExternal accepts any scheme; restore failures can leave empty/partial memcard or state targets; merge backup misses subfolder members.
### Proposed Behavior / Steps to Reproduce
See issue #692 body (cited code in _core.py, sync_client.py, window.ts).
### Affected Area
src/server/api/_core.py, src/server/sync_client.py, src/gui/electron/window.ts.
### Acceptance Criteria
- CORS restricted or PIN required; decision documented.
- hmac.compare_digest for PIN.
- openExternal limited to http/https; will-navigate handled.
- Memcard/state restore extracts to temp then swaps / rolls back; tarfile closed.
- Merge backup uses member relative path.
- Regression tests for restore failure and merge backup.

## 2. Design
### Scope: backend (Python) + small Electron main-process change (no renderer/IPC/schema change)
### Backend Changes: _core.py CORS origin allowlist + hmac.compare_digest; sync_client.py three restore functions made failure-safe, merge backup by relative path
### UI Changes: window.ts only: http/https guard on openExternal, will-navigate guard (main process, no IPC)
### Plan Target: both (bplan for Python, fplan for the window.ts change; merge trivial)
### Sub-issues: none
### Difficulty: 4/10
### Backwards Compatibility: no breaking changes (CORS only narrows browser origins; Electron renderer origin and dev server stay allowed)

## 3. Frontend Plan
### Design Alignment: no visual change; Electron main process only
### Visual Pattern: none
### Recommendations: none
Step 7 of plan file: window.ts - src/gui/electron/window.ts, reuses setWindowOpenHandler; new inline openSafe (same http/https check needed in two handlers). No IPC, no emusync.d.ts change.
## 4. Backend Plan
### Design Alignment: fits existing helpers (_safe_extract_tar, .bak convention); backend-design-guide.md unchanged
### Backend Pattern: extract archive to a sibling temp dir first, then swap/move with os.replace; CORS allowlist via allow_origin_regex
### Recommendations: CORS allowlist (null, localhost, 127.0.0.1) rather than mandatory PIN; document in GOTCHAS.md
## 5. Merged Plan
### Conflicts Resolved: none (bplan and fplan share one plan file tools/plans/692-harden-cors-restore-safety.md; disjoint files)
### Unresolved Conflicts: none
## 6. Testing Plan
- **Test File**: src/tests/test_restore_safety.py
- **Test Cases**:
  - cors_allowed_origin: async `client` OPTIONS `/health` (or any route) with `Origin: null` and `Origin: http://localhost:5173` + `Access-Control-Request-Method: GET` returns `access-control-allow-origin` echoing the origin.
  - cors_foreign_origin: `Origin: https://evil.example` preflight has no `access-control-allow-origin` header.
  - pin_constant_time: correct PIN accepted, wrong PIN 401/403 via existing `AUTH`; non-ASCII PIN header does not 500.
  - memcard_restore_failure_keeps_card: `_write_memcard_tar_bytes(card, corrupt_tar)` raises `tarfile.TarError`, card folder content unchanged, no `.emusync-*` temp dirs left, no empty card.
  - memcard_restore_success_backs_up: valid tar replaces folder, `<card>.bak` holds old tree (covered by existing test; add file-card to folder-card case).
  - state_extract_failure_no_rename: `_extract_state_folder` with an enveloped corrupt tar.gz leaves existing state files and creates no `.bak`.
  - state_extract_success: files replaced, previous ones in `.bak`.
  - merge_backup_subfolder: shared folder with `sub/a.state`; merging an archive containing `sub/a.state` leaves `sub/a.state.bak` with old content, new content in place; untouched siblings unchanged.
  - merge_traversal_rejected: archive with `../x` raises/ignores before any `.bak` is made.
- **Edge Cases**:
  - Legacy (un-enveloped) raw state blob still written as `<Folder>.state`.
  - Legacy raw-file memcard fallback (`_write_memcard` with non-tar bytes) still works (existing test must keep passing).
  - Existing `.bak` is overwritten, not accumulated.
- **Integration Points**:
  - `_write_memcard` TarError fallback to `_write_memcard_raw_bytes` depends on step 4 still raising TarError.
  - `run`/pull-state callers of these helpers unchanged in signature.
  - window.ts: no automated harness; manual check (external https link opens, `javascript:`/`file:` ignored, in-app navigation blocked), tsc.

### Outline
Frontend: window.ts - openSafe http/https guard for setWindowOpenHandler plus will-navigate guard.
Backend: _core.py CORS allow_origin_regex; hmac.compare_digest; sync_client.py _extract_tar_to_tmp helper; memcard, state and merge restores extract to temp then swap; merge backup by relative path; docs.
Tests: test_restore_safety.py (CORS, PIN, memcard/state failure rollback, merge subfolder backup); manual check for window.ts.
### Summary
Narrow CORS, constant-time PIN, http(s)-only external links, and make archive restores atomic-ish with correct merge backups.
## 7. Test Design
TBD
## 8. Implementation Steps
Backend (plan file tools/plans/692-harden-cors-restore-safety.md steps 1-6, 9):
1. _core.py CORS regex - reuses CORSMiddleware; no new code.
2. _core.py hmac.compare_digest - reuses existing check.
3. sync_client.py _extract_tar_to_tmp - new helper, shared by 3 restores.
4. _write_memcard_tar_bytes extract-then-swap - reuses helper.
5. _extract_state_folder extract-then-swap - reuses helper.
6. _merge_extract_state_folder temp extract + per-file relative backup - reuses helper.
7. window.ts: openSafe + will-navigate (reuses setWindowOpenHandler; inline helper because two handlers need the check).
8. Tests: src/tests/test_restore_safety.py (reuses conftest client/AUTH and memcard test patterns).
9. Docs: GOTCHAS.md entry + CLAUDE.md rule line.
## 9. Review
### Findings: 1 fixed (state extract moved dirs with os.replace; now file-wise). Residual: window.ts not type-checked locally (no node_modules)
### Blocked: no
### Blockers: none
TBD
## 10. Ship
TBD
## 11. Fix Attempts
none
## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend+electron-main, plan_target=both, difficulty=4/10, breaking=no
- 2026-11-01 bplan: 9 steps written, backend_pattern=extract-to-temp-then-swap
- 2026-11-01 fplan: 1 step written, visual_pattern=none
- 2026-11-01 tplan: test_file=src/tests/test_restore_safety.py, 9 test cases defined
- 2026-11-01 implement: steps 1-9 done (CORS regex, hmac, temp-extract restores, window.ts guards, tests, docs); full suite 606 passed. Deviation: single commit for all steps; tsc not run (no node_modules)
- 2026-11-01 review: 1 finding (fixed), blocked=no
