# Handoff: #692 Harden CORS, PIN check, external URLs and archive restore safety

## Metadata
- Issue: #692
- Branch: feature/692-harden-cors-restore-safety
- PR: none
- Status: designed
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
TBD
## 4. Backend Plan
### Design Alignment: fits existing helpers (_safe_extract_tar, .bak convention); backend-design-guide.md unchanged
### Backend Pattern: extract archive to a sibling temp dir first, then swap/move with os.replace; CORS allowlist via allow_origin_regex
### Recommendations: CORS allowlist (null, localhost, 127.0.0.1) rather than mandatory PIN; document in GOTCHAS.md
## 5. Merged Plan
TBD
## 6. Testing Plan
TBD
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
9. Docs.
## 9. Review
TBD
## 10. Ship
TBD
## 11. Fix Attempts
none
## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend+electron-main, plan_target=both, difficulty=4/10, breaking=no
- 2026-11-01 bplan: 9 steps written, backend_pattern=extract-to-temp-then-swap
