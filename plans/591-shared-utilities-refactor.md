# Plan: #591 refactor: extract common _find_touched_path helper and move shared utilities to common.py

Issue: #591
Branch: feature/591-shared-utilities-refactor
PR: none
Status: planned
Fix attempts: 0

## Goal
Extract the `_find_touched_path` helper and other shared utilities into `cli/common.py` to reduce duplication across console adapters.

## Steps
- [ ] 1. Refactor `cli/run_reconcile.py` to use `_find_touched_path` in `_resolve_written_save` and `_resolve_written_state`.
  - Files: cli/run_reconcile.py
  - Reuses: cli/common.py:_find_touched_path
- [ ] 2. Verify all existing tests pass.
  - Tests: tests/test_run_reconcile.py
- [ ] 3. Docs: none needed - implementation is internal to CLI.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
## Log
