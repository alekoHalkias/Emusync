# Plan: #729 Auto-link network-drive games on devices sharing the same network share (backend)

Issue: #729
Branch: feature/729-auto-link-network-games
PR: none
Status: implementing
Fix attempts: 0

## Goal
Give a device, in one request, the list of network-drive games it can link itself because its console network share ID matches the source device's.

## Design Alignment
- **Backend Pattern**: Thin route over one inline-SQL Store method in the existing `games` mixin, next to `get_network_source_for_game` and returning the same portable fields. Read-only, additive, no schema change.
- **Recommendations**: Register the route before `/games/{slug}` (like `/games/overview`) so the literal path is not captured as a slug.

## Steps
- [ ] 1. Store method `network_link_candidates(device_id) -> list[dict]` in `src/server/store/games.py`. One query: `game_devices gd` (rom_source='network', rom_rel_path != '', device_id != me) JOIN `games g` JOIN `consoles src` (src.device_id = gd.device_id, src.console_name = g.console, src.network_share_id != '') JOIN `consoles mine` (mine.device_id = me, mine.console_name = g.console, mine.network_share_id = src.network_share_id, mine.device_network_folder != ''), WHERE NOT EXISTS a `game_devices` row for (g.slug, me); `GROUP BY g.slug` with `MAX(gd.rowid)` so each game appears once from its most recently written source row. Returns `slug, console, rom_path, rom_rel_path, launch_command, save_path, state_path, share_id, mount_root` (mount_root = mine.device_network_folder).
  - Files: src/server/store/games.py
  - Reuses: column set and console/share join of `get_network_source_for_game` (same file)
  - New: method - `get_network_source_for_game` is per-slug and does not filter by this device's share or existing config; looping it from the client is N requests plus a per-game share lookup.
- [ ] 2. Route `GET /games/network-link-candidates` in `src/server/api/games.py`, placed before `GET /games/{slug}`: `_auth`, return `_get_store().network_link_candidates(device_id)`.
  - Files: src/server/api/games.py
  - Reuses: `_auth`, `_get_store` from `_core.py`; pattern of `/games/overview`
  - New: route - none existing exposes the candidate list.
- [ ] 3. Tests in `src/tests/test_network_rom.py` (real SQLite, `client` fixture, two devices via different `X-Device-ID`): (a) device A network game + both consoles with same share ID -> B gets one candidate with B's `mount_root` and A's `rom_rel_path`; (b) different share ID -> empty; (c) blank share ID on either side -> empty; (d) B already has a `game_devices` row -> empty; (e) A's own call never lists its own game; (f) two consoles rows for B with the same console -> still one candidate.
  - Files: src/tests/test_network_rom.py
  - Reuses: existing fixtures/helpers in that file
- [ ] 4. Docs: add the route to src/docs/ARCHITECTURE.md (REST list) and a one-line rule in CLAUDE.md under the #660 network bullet.
  - Files: src/docs/ARCHITECTURE.md, CLAUDE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no (frontend plan). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Electron/renderer linking (frontend plan). Server-side linking: the server cannot verify the file exists on the client's mount, so the client does the link.

## Log
- 2026-11-02 bplan: 4 steps written
