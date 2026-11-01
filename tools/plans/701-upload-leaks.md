# Plan: #701 Fix upload and staging file leaks, check game exists on save/state push

Issue: #701
Branch: feature/701-upload-leaks
PR: none
Status: implemented
Fix attempts: 0

## Goal
Stop leaking upload temp files and stale ROM staging dirs, and reject save/state pushes for unknown games before staging.

## Design Alignment
- **Backend Pattern**: HTTPException 404 "Game not found" as in `_history`; best-effort cleanup via `unlink(missing_ok=True)` as in `_stage_upload`; startup sweep stays in `_core._sweep_stale_staging`.
- **Recommendations**: age limit is a module constant (7 days) rather than a Config field; no user need for a knob yet, add to Config if asked. Issue text said "configurable"; this narrows it.

## Steps
- [x] 1. `_push`: 404 if `store.get_game(slug)` is missing (before `_stage_upload`); wrap `_store_it` so a raise unlinks `tmp`.
  - Files: src/server/api/blobs.py
  - Reuses: `_get_store().get_game`, `tmp.unlink(missing_ok=True)`
  - New: none
- [x] 2. `push_console_save_file`: unlink `src` on the hash-match early return.
  - Files: src/server/store/blobs.py
  - Reuses: `Path(src).unlink(missing_ok=True)` as in `_push_blob_file`
  - New: none
- [x] 3. `_sweep_stale_staging`: also remove staging dirs of pending transfers older than `_STAGING_MAX_AGE_DAYS` (7) and mark them `failed`.
  - Files: src/server/api/_core.py
  - Reuses: `Store.get_rom_transfer`, `update_transfer_status`, `RomTransfer.queued_at` (ISO UTC)
  - New: one constant - no config plumbing exists in `_core.init`
- [x] 4. Tests: unknown-slug save/state push returns 404 and `.uploads` empty; store raising in `_store_it` leaves `.uploads` empty; repeat identical memcard push leaves `.uploads` empty; old pending transfer's staging dir removed and status `failed` on `init`, fresh pending kept. Real SQLite.
  - Files: src/tests/test_upload_leaks.py
  - Reuses: `src/tests/test_integration.py` client/AUTH pattern
- [x] 5. Docs: none needed - internal cleanup behavior, no new routes/config/IPC.

## Testing
- **Test File**: src/tests/test_upload_leaks.py (pattern: tests/test_hardening_691.py, fixtures `client`/`make_client` from conftest)
- **Test Cases**:
  - unknown slug save/state POST: 404, `store._blob_dir/.uploads` has no files
  - store raises in push (monkeypatch `push_save_file` to raise via pytest monkeypatch of the real Store method): `.uploads` empty
  - identical console memcard pushed twice: `.uploads` empty after second
  - `init` sweep: pending transfer row with old `queued_at` -> dir removed, status `failed`; fresh pending -> dir kept
- **Edge Cases**: existing game save push still 200 (regression guard)
- **Integration Points**: `_core.init` -> `_sweep_stale_staging`; `_push` -> `Store.push_*_file`

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Periodic (non-startup) sweep; configurable age; memcard push game check (keyed by console, not a game).
## Log
