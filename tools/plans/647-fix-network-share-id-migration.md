# Plan: #647 Fix missing network_share_id column on databases at schema v30

Issue: #647
Branch: feature/647-fix-network-share-id-migration
PR: none
Status: planned
Fix attempts: 0

## Goal
Make every database, whatever version it was stamped at, end up with `consoles.network_share_id`, and stop the console settings modal from hiding a failed fetch behind the empty-row message.

## Design Alignment
- **Backend Pattern**: schema-evolution recipe from the backend guide: one `if from_version < N` block with an idempotent `_try(ALTER)`. The abandoned #642 branch already stamped some databases v30, so a version number is only safe once it ships; the column moves to v31 and the v30 block stays as a comment. No Store or API change.
- **Recommendations**: Add one line to `.claude/backend-design-guide.md`: never reuse a schema number that a deployed (even closed or unmerged) branch may have stamped; pick the next free number when a branch is rebased.

## Steps
- [ ] 1. Move the `network_share_id` ALTER from `from_version < 30` to a new `from_version < 31` block, set `_SCHEMA_VERSION = 31`, and leave a comment where the v30 block was explaining that v30 was stamped by the closed #642 work.
  - Files: src/server/store/schema.py
  - Reuses: the existing `_try(conn, "ALTER TABLE ...")` pattern and the `_SCHEMA` column already added for fresh databases
  - New: none
- [ ] 2. Tests (real SQLite): a hand-built v30 consoles table without the column gains it with '' default, keeps its rows, and ends at `_SCHEMA_VERSION`; rename the existing v29 test so it no longer claims v30; add an end-to-end case where a `Store` over a v30-stamped database lacking the column can `list_consoles` after startup.
  - Files: src/tests/test_network_rom.py
  - Reuses: `test_v29_to_v30_migration_adds_share_id` hand-built table pattern, `Store(tmpdir)`
  - New: none
- [ ] 3. `ConsoleFoldersModal`: when the console fetch throws, show "Couldn't load this console's folders - is the server reachable?" instead of "No folders recorded for this console yet" (the genuine no-row case keeps its text); the Ignored games panel still renders.
  - Files: src/gui/renderer/src/components/ConsoleFoldersModal.tsx
  - Reuses: the modal's existing `msg`-style muted text and `row` state
  - New: one `loadFailed` state flag - `row` null already means "no row", so a failure needs its own value
- [ ] 4. Docs: CLAUDE.md schema rule gets the "do not reuse a stamped number" sentence; backend guide line from Recommendations.
  - Files: CLAUDE.md, .claude/backend-design-guide.md

## Testing
- **Test File**: src/tests/test_network_rom.py
- **Test Cases**:
  - test_v30_stamped_db_gains_share_id: v30 table lacking the column gains it as '' without losing rows.
  - test_v29_migration_adds_share_id (renamed): v29 table gains it and `user_version` equals `_SCHEMA_VERSION`.
  - test_store_on_v30_stamped_db_lists_consoles: a Store opened on such a database returns consoles with `network_share_id == ''`.
- **Edge Cases**:
  - Running the migration twice leaves one column and no error (`_try` idempotent).
  - A database that already has the column at v30 (fresh #644 install) is unaffected.
  - Fresh database stamps 31.
- **Integration Points**:
  - Modal error state has no JS test runner: verify manually that stopping the server shows the error message and that the normal no-row case still shows the old text.
  - After merge, restart the server PC service and confirm `GET /devices/{id}/consoles` returns 200.

## Checklist
Schema bump: yes (30 -> 31). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Dropping the stray #642 columns (`import_is_network`, `import_remote_path`) on v30 databases; they are harmless because every query names its columns.

## Log
