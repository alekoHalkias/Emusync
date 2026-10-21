# Plan: #578 Better Metadata Extraction

Issue: #578
Branch: feature/578-better-metadata
PR: none
Status: planned
Fix attempts: 0

## Goal
Implement automated metadata retrieval via IGDB, with caching, fallback, toggle auto-fetch, and manual override support.

## Steps
- [x] 1. Add `auto_fetch_metadata: bool` to `server/config.py` (default: True). Update `load` and `save` accordingly. Add documentation in config.
  - Files: server/config.py
  - Reuses existing Config dataclass.
- [x] 2. Update `server/api/games.py::get_game_metadata` to:
    - Check `store.get_game_metadata`.
    - If None and `auto_fetch_metadata` is True, call `get_igdb_metadata` and store via `store.set_game_metadata`.
    - Return meta (or 404 if still missing).
  - Files: server/api/games.py
- [x] 3. Improve `server/api/igdb.py::fetch_igdb_metadata`:
    - Correct query handling: send `variables` dict directly.
    - After default query, if no result, perform title-based fallback using `_TITLE_QUERY`.
    - Log errors, return None on failure.
  - Files: server/api/igdb.py
- [x] 4. Add tests in `tests/test_metadata/test_metadata.py`:
    - Test cache retrieval when metadata already present.
    - Test auto-fetch enabled: metadata fetched and stored.
    - Test auto-fetch disabled: metadata not fetched.
    - Test fallback to title search.
  - Files: tests/test_metadata/test_metadata.py
- [x] 5. Update documentation:
    - docs/GOTCHAS.md: note new metadata endpoint, toggle, manual override.
    - docs/ARCHITECTURE.md: mention IGDB service and caching.

  - Files: docs/GOTCHAS.md, docs/ARCHITECTURE.md

## Checklist
- Schema bump: no.
- New IPC channel: no.
- New CLI subcommand: no.
- Config/data file change: yes.

## Not in this plan
- GUI display changes (handled in a separate PR).

## Log
- None yet.