# Plan: #725 Link Switch game saves for Pokemon Legends Z-A across Steam Deck and Arch

Issue: #725
Branch: feature/725-switch-legends-za-save-link
PR: none
Status: planned
Fix attempts: 0

## Goal
A Switch game whose device already has a learned save folder publishes its title ID to the server, so other devices can match and seed the same save.

## Design Alignment
- **Backend Pattern**: CLI run path (`cli/run.py`) already backfills `switch_title_id` via `client.update_game` in two places (#443): after a title-ID local match, and after a post-launch adoption. Both are skipped when `save_path` is already set on the device and the server ID is blank (game played before the self-heal existed, or save path set manually). That is the confirmed code gap: the other device then has no ID to match or seed from, so saves never link. Fix at the shared point in `run_game`, before reconcile, reusing `update_game`.
- **Recommendations**: Root cause on the user's Deck/Arch data is not observed (the local DB here has no Z-A row). The fix covers the gap found in code; if the stored ID is non-blank but wrong, that is a separate follow-up.

## Steps
- [ ] 1. In `run_switch.py` add `_switch_title_id_from_save_path(save_path)`: returns the folder basename if it matches the 16-hex title ID regex, else "".
  - Files: src/cli/run_switch.py
  - Reuses: `_SWITCH_TITLE_ID_RE` pattern in src/cli/detect.py (bracket-free variant needed)
  - New: one small helper - existing `_switch_title_id_from_rom` parses a bracketed filename tag, not a folder name.
- [ ] 2. In `run_game` (after `resolved_title_id`/before reconcile), when `console_abbr == "Switch"` and `not switch_title_id` and `save_path` is set: derive the ID from `save_path` (fall back to `resolved_title_id`), call `client.update_game(game_slug, game_name, switch_title_id=...)` inside try/except warning, and set `switch_title_id`/`resolved_title_id`.
  - Files: src/cli/run.py
  - Reuses: `client.update_game`, the existing warning pattern at run.py:387
  - New: none
- [ ] 3. Tests: src/tests/test_switch_save_sync.py - helper returns ID for a 16-hex folder and "" otherwise; run with `save_path` set and blank server ID backfills the ID (real SQLite, existing fixtures in that file); no backfill when ID already stored. No mocks.
- [ ] 4. Docs: GOTCHAS.md Switch section: one line noting the backfill also runs when save_path is already known.

## Testing
- **Test File**: src/tests/test_switch_save_sync.py (helper cases); src/tests/test_run_reconcile.py (run_game backfill, reusing its existing run_game harness)
- **Test Cases**:
  - helper returns the ID for a 16-hex folder path
  - run_game with save_path set and blank server title ID calls update_game with the ID
  - no update when server ID already stored
- **Edge Cases**:
  - non-hex folder name (e.g. a path ending in a game name) returns "" and nothing is stored
  - update_game failure only warns, launch continues
- **Integration Points**: client.update_game -> PUT /games/{slug} -> store.update_game_switch_title_id

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Correcting a wrong stored title ID; titledb fuzzy matching; additional Eden roots.

## Log
