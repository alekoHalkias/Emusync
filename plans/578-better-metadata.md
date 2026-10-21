# Plan: #578 Better Metadata Extraction

Issue: #578
Branch: feature/578-better-metadata
PR: none
Status: planned
Fix attempts: 1

## Goal
Server caches per-game metadata (synopsis, release date, cover URL) fetched keyless from Wikipedia, with an auto-fetch toggle and manual overrides that are never overwritten.

## Decisions (from user)
- Source is keyless (no IGDB, no credentials). Box art display already exists in the GUI (art.ts: SteamGridDB then libretro-thumbnails); this PR only adds text metadata plus a cover URL stored for reference. Wikipedia REST (search + page summary) is the chosen keyless source for synopsis/release date.
- Manual overrides live in the same cache table with `source='manual'`; auto-fetch never overwrites them.

## Steps
- [x] 1. Reset the failed first attempt. Run `git stash push -u -- server/api/igdb.py server/api/defs.py server/api/games.py server/config.py server/store tests/test_metadata server/sync_client.py` first so nothing is lost, then `git checkout main -- server/api/defs.py server/api/games.py server/config.py server/store server/sync_client.py` and delete `server/api/igdb.py`, `tests/test_metadata/`, and untracked `tests/test_metadata.py`. Result: product code identical to main (this also drops the INSERT OR REPLACE change to `add_game`, which violated CLAUDE.md).
  - Files: the above
  - Reuses: main
- [x] 2. Schema v28: table `game_metadata(slug TEXT PRIMARY KEY REFERENCES games(slug) ON DELETE CASCADE, synopsis TEXT NOT NULL DEFAULT '', release_date TEXT NOT NULL DEFAULT '', cover_url TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, fetched_at TEXT NOT NULL)`. Add to `_SCHEMA`, `if from_version < 28` in `_migrate()`, bump `_SCHEMA_VERSION`, keep the fresh-DB stamp.
  - Files: server/store/schema.py
  - Reuses: schema.py `_try`, existing migration pattern
- [ ] 3. Store methods `get_metadata(slug)`, `set_metadata(slug, fields, source)` (refuses to overwrite a `manual` row unless source is `manual`), `delete_metadata(slug)`. New mixin file because games.py is near the size limit; add to `Store` bases.
  - Files: server/store/metadata.py, server/store/__init__.py
  - Reuses: server/store/games.py mixin pattern
  - New: metadata.py - separate table-group mixin per CLAUDE.md conventions
- [ ] 4. Config: `auto_fetch_metadata: bool = True`, loaded with `bool(data.get(...))`, saved always (so False persists).
  - Files: server/config.py
  - Reuses: Config dataclass, atomic save
- [ ] 5. Service `fetch_wikipedia(name, console)` using httpx (already a dependency): search `https://en.wikipedia.org/w/rest.php/v1/search/title?q=<name> video game`, then `/api/rest_v1/page/summary/<title>`; return `{synopsis, release_date, cover_url}` or None. Timeout 10s, one retry with 1s sleep on 429/5xx, never raises; User-Agent set. Router `server/api/metadata.py`: `GET /games/{slug}/metadata` (404 unknown game; cached row if present and under 30 days old or manual; else when toggle on, fetch, store with source `wikipedia`, on failure serve stale row or empty default), `PUT /games/{slug}/metadata` (manual, source `manual`), `DELETE /games/{slug}/metadata` (clear, forces refetch). Register router in the api package; use `_get_store()` and `_auth` accessors.
  - Files: server/api/metadata.py, server/api/__init__.py (or wherever routers register)
  - Reuses: server/api/defs.py router/auth pattern, server/config.py load
  - New: metadata.py - no existing external-fetch service in server/
- [ ] 6. Tests (real SQLite, no mocks, tests/test_metadata_api.py): manual PUT persists and survives GET with toggle on; DELETE then GET with toggle off returns empty default; unknown slug 404; store refuses auto overwrite of manual; stale auto row refetch path exercised by pointing the fetch base URL at a tiny local `live_server`-style stub (configurable module constant) incl. error/offline case returning default without raising; migration test from v27 DB creates the table.
  - Files: tests/test_metadata_api.py
  - Reuses: tests/conftest.py client, AUTH
- [ ] 7. Docs: docs/ARCHITECTURE.md (routes, table, config field `auto_fetch_metadata`), docs/GOTCHAS.md (manual never overwritten, Wikipedia keyless/fuzzy match, 30-day TTL). CLAUDE.md update required by the hook for config.py (one-line rule).
  - Files: docs/ARCHITECTURE.md, docs/GOTCHAS.md, CLAUDE.md

## Checklist
Schema bump: yes (28). New IPC channel: no. New CLI subcommand: no. Config/data file change: yes (`auto_fetch_metadata`).

## Not in this plan
- GUI display/toggle UI and manual-entry form (follow-up issue); cover download/caching (GUI art pipeline already covers art).
- IGDB / SimHacker sources.

## Log
- Attempt 1 (blocked): tests had no assertions, igdb.py misused httpx and was not wired in, add_game changed to INSERT OR REPLACE. Superseded by this plan.
- Step 1: server/sync_client.py revert to main left uncommitted (hook requires CLAUDE.md); commits with the docs step.
- Step 2: main is at schema v27, so the bump is to v28 (plan said 29).
