# Plan: #715 Prevent data loss on failed or empty transfers

Issue: #715
Branch: feature/715-prevent-transfer-data-loss
PR: none
Status: planned
Fix attempts: 0

## Goal
A failed, partial, or empty transfer never overwrites or hides existing ROMs, saves, or states.

## Design Alignment
- **Backend Pattern**: Routes stay thin; fixes live in the existing handlers/helpers (`download_transfer`, `_pull`, `pull_console_memcard`, `_stage_upload`, `_is_stale`). No schema, endpoint, or client-protocol change.
- **Recommendations**: Record the sync baseline with a Starlette `BackgroundTask` attached to the `FileResponse`; it only runs after the body is fully sent, so no new ack endpoint or client change is needed. Add this pattern to the design guide.

## Steps
- [ ] 1. `download_transfer`: stream into `<dest>.part`, verify hash, then `os.replace` onto dest; on any failure unlink the `.part` and leave dest untouched. Drop the `not path.suffix` rejection (keep `is_dir()`), so extensionless ROMs are accepted.
  - Files: src/server/sync_client.py
  - Reuses: existing streaming loop and hash check in `download_transfer`
  - New: none
- [ ] 2. Baseline after delivery: in `_pull` and `pull_console_memcard`, replace the pre-response `set_*_sync_baseline` call with `BackgroundTask(...)` passed to `FileResponse(background=...)`.
  - Files: src/server/api/blobs.py
  - Reuses: `FileResponse`, `store.set_save_sync_baseline`, `store.set_console_save_sync_baseline`
  - New: none (Starlette built-in; no ack endpoint needed)
- [ ] 3. Reject empty uploads: in `_stage_upload`, after streaming, if `size == 0` unlink tmp and raise HTTPException 400 ("Empty upload"). Covers save, state, and memcard pushes since all use it.
  - Files: src/server/api/blobs.py
  - Reuses: `_stage_upload` existing cleanup-on-exception block
  - New: none
- [ ] 4. Offload upload writes: `await loop.run_in_executor(None, f.write, chunk)` in `_stage_upload`, matching `create_rom_transfer`.
  - Files: src/server/api/blobs.py
  - Reuses: pattern at src/server/api/transfers.py create_rom_transfer
  - New: none
- [ ] 5. `_is_stale`: treat a naive timestamp as UTC and catch `TypeError` as well as `ValueError`.
  - Files: src/server/api/_core.py
  - Reuses: naive-to-UTC handling already in `_presence_tick`
  - New: none
- [ ] 6. `files:get-file-hash`: hash in 1 MiB chunks in the inline Python snippet.
  - Files: src/gui/electron/files.ts
  - Reuses: existing spawn of `rt.PYTHON -c`
  - New: none (snippet edit only; IPC signature unchanged)
- [ ] 7. Tests: new src/tests/test_transfer_dataloss_715.py. Cases: (a) hash mismatch and mid-stream failure leave an existing destination byte-identical and no `.part`; (b) extensionless destination downloads; (c) baseline absent after an aborted pull, present after a completed pull (save and memcard); (d) zero-byte POST to save, state, and memcard returns 400 and stores nothing; (e) `_is_stale` with a naive timestamp does not raise. Real SQLite, no mocks; follow test_rom_transfer.py and test_saves.py setup.
- [ ] 8. Docs: add the BackgroundTask-baseline pattern to .claude/backend-design-guide.md; add a short #715 note to src/docs/GOTCHAS.md; one line in CLAUDE.md Saves/sync rules (baseline recorded after delivery, empty uploads rejected, ROM downloads via .part).

## Testing
- **Test File**: src/tests/test_transfer_dataloss_715.py (new; one file for the bug-fix regressions, per the existing test_hardening_NNN.py convention)
- **Test Cases**:
  - ROM hash mismatch: real stdlib `http.server` thread serves bytes with a wrong `X-Rom-Hash`; `SyncClient.download_transfer` raises, pre-existing destination is byte-identical, no `.part` left.
  - ROM mid-stream failure: server closes the connection early; same assertions.
  - ROM success: destination replaced with new bytes, no `.part` left.
  - Extensionless destination downloads successfully; a directory destination still raises.
  - Save baseline: call `_pull` directly with the shared real-SQLite store; baseline is `None` before `resp.background()` runs and equals the pulled hash after. Same for `pull_console_memcard`.
  - Empty upload: zero-byte POST to `/games/{slug}/save`, `/games/{slug}/state`, and `/consoles/{key}/memcard` returns 400, stores nothing, and leaves no file in the upload staging dir.
- **Edge Cases**:
  - `_is_stale` with a naive timestamp returns a bool instead of raising; with garbage string returns False.
  - Non-empty upload after a rejected empty one still works (no leaked state).
  - A pull of a game with no save (204) records no baseline.
- **Integration Points**:
  - Starlette runs `FileResponse.background` after send; confirmed through the existing ASGI `client` fixture by checking `GET .../sync-baseline` after a full GET.
  - files.ts hash snippet: no automated test (Electron IPC); verify manually with a file larger than 1 MiB that the digest equals `sha256sum`.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- MAC-based device merge in `touch_device` (separate follow-up issue).
- Client ack endpoint for pulls (BackgroundTask covers it).
- Known residual: the baseline lands just after the body is sent, so a client that queries the baseline in the same millisecond may briefly see the old value; acceptable.

## Log
