# Plan: #718 Surface folder-versus-file card mismatch instead of silent no-op pull

Issue: #718
Branch: feature/718-card-format-mismatch
PR: none
Status: implementing
Fix attempts: 0

## Goal
A raw blob pulled onto a directory card raises a typed error instead of reporting success; `emusync run` resolves it as local wins, loudly.

## Design Alignment
- **Backend Pattern**: Writer raises, caller decides policy. Reuses the existing conflict surface (`_warn_save_conflict`: stderr, notification, `save_conflicts.json`, server conflict record). Manual pull, sync restore and Switch seeding already catch `Exception` and report, so they need no change.
- **Recommendations**: none

## Steps
- [x] 1. `_write_memcard_raw_bytes` raises `CardFormatMismatch(ValueError)` ("local card is a folder but the server copy is a single file") when `card.is_dir()`, instead of returning. Atomic `.part` write from #734 unchanged.
  - Files: src/server/sync_client.py
  - Reuses: `_write_memcard_raw_bytes`
  - New: `class CardFormatMismatch(ValueError)` - callers must tell a format mismatch apart from other errors.
- [ ] 2. `_reconcile_save`: wrap the pull in `except CardFormatMismatch`; push the local copy (`client.push_save`), call `_warn_save_conflict(..., "local", ...)` with a format-mismatch message, return the pushed hash. `_warn_save_conflict` gets an optional `msg` override so the "both copies changed" text isn't reused for this case.
  - Files: src/cli/run_reconcile.py, src/cli/run_conflicts.py
  - Reuses: `_warn_save_conflict`, `_log_save_conflict`, `_report_conflict_to_server`, `_notify`
  - New: none
- [ ] 3. Tests (no mocks, real SQLite).
  - Files: src/tests/test_memcard_folder_sync.py, src/tests/test_run_reconcile.py
- [ ] 4. Docs: GOTCHAS.md one paragraph under #734's section (replaces the "directory left alone" note); CLAUDE.md Saves/sync line amended. ARCHITECTURE.md: none needed - no new route/IPC/CLI/config.

## Testing
- **Test File**: src/tests/test_memcard_folder_sync.py, src/tests/test_run_reconcile.py
- **Test Cases**:
  - raw_onto_directory_raises: replace `test_write_memcard_legacy_fallback_does_not_crash_on_directory_target` with `pytest.raises(CardFormatMismatch)` for both a legacy non-tar blob and an enveloped `_FMT_RAW` blob; the directory contents are untouched.
  - reconcile_folder_vs_raw_local_wins: live_server; device A pushes a file save; device B's save path is a folder with content; `_reconcile_save` on B -> server hash equals B's folder hash, B's folder untouched, `save_conflicts.json` has an entry. Reuses the live_server + SyncClient pattern of `test_reconcile_shared_memcard_stale_local_untouched_is_not_a_conflict`.
- **Edge Cases**:
  - File target still written (existing round-trip tests).
- **Integration Points**:
  - Manual `game pull-save` already maps any exception to exit 1 "Pull failed: <msg>" (no test change).

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Server-side baseline is still recorded once the blob is sent (#715 BackgroundTask); the local-wins push immediately supersedes it, so no client-side suppression is needed.

## Log
- 2026-11-02 bplan: plan written
- 2026-11-02 tplan: testing section added
