# EmuSync — CLAUDE.md

## Project overview

EmuSync is a LAN save-file sync tool for emulators: one machine (gaming PC) runs a Python/FastAPI server, other devices (Steam Deck, second PC) pair with it and sync saves automatically. GUI is Electron + React wrapping the Python CLI. No cloud, no accounts, no port forwarding.

---

## Architecture

```
emusync.py          ← Thin CLI entry-point shim (kept at this path for install.sh/Makefile/Electron spawn/pkill); delegates to the cli/ package
cli/                ← Click CLI implementation; one module per command group
server/             ← Python backend (FastAPI + SQLite + mDNS)
gui/electron/       ← Electron main process; spawns Python, bridges IPC
gui/renderer/src/   ← React renderer; talks to Python API via fetch + IPC
tests/              ← Integration tests (real SQLite, no mocks)
```

**Data flow:**
1. Electron spawns `emusync.py server start` as a child process
2. Python writes `~/.emusync/.server_pid` and `.server_token` on start
3. Renderer calls the Python REST API (`http://localhost:8765`) directly via `api.ts`
4. Electron IPC (`preload.ts` → `main.ts`) handles config I/O, server lifecycle, file dialogs, game launch
5. `emusync run <slug>` wraps emulator launch: derives the emulator command from the game's stored `launch_command`, reconciles the save (push if local newer than server, else pull) → launch → push save → release lock. An explicit command can still be passed as a fallback (`emusync run <slug> -- retroarch …`, e.g. a Steam `%command%` wrapper around RetroArch), honored only if the game is imported on this device (has a `save_path`) — otherwise launch is refused. A true divergence (both copies changed) auto-resolves newest-wins, surfaced via stderr + a `notify-send` notification + an entry in `save_conflicts.json`. If the server is unreachable, launch proceeds **offline** (no lock/sync) and the play window is appended to `offline_plays.json` so a newer offline save wins the next online launch (issue #5)

---

## Key files

| File | Owns |
|------|------|
| `emusync.py` | Thin entry-point shim: bootstraps `sys.path`, calls `cli()` from `cli/`. Must stay at this path — `install.sh`, `Makefile`, Electron's `spawn` in `main.ts`, and `pkill -f "emusync.py server start"` invoke it by path. No command logic here |
| `cli/` | Click CLI, one module per command group. `root.py` = root `cli` group; `__init__.py` imports every command module (registers subcommands) and re-exports `cli`. `common.py` = shared helpers (`_client`, `_print_table`, `_get_device_name`, `_show_game_running_popup`, `_fmt_time`/`_relative`/`_parse_iso_utc` for human-readable timestamps — #216); `consoles_data.py` = hardcoded `_IMPORT_CONSOLES`/`_IMPORT_SYSTEMS`/extension sets + `_prepare_console_seed_data` (seeds the server's global console defs); `detect.py` = RetroArch/core/ROM detection + scan helpers (mirrors `main.ts`); standalone emulator detection reads `save_dir`/`state_dir` from a standalone def's `dirs.native`/`dirs.flatpak` (expanded via `_expand_home`, mirroring `detect.ts`'s `expand()`) rather than a nonexistent top-level `save_dir` key, and expands `~` in `native_bins` before checking existence, #361; `server.py` = `server` group (start/stop/restart/clear-devices/discover-json) + lifecycle helpers + embedded transfer daemon; `device.py` = `device` group (`connect`/`list`/`compare` — `compare` shows game coverage across paired devices); `game.py` = `game` group (`add`/`list`/`edit`/`remove` — `remove` defaults to unlinking the game from this device only via `client.remove_game_device`, leaving other paired devices and save/state history untouched; `--everywhere` opts into the old full-purge behavior via `client.remove_game`, #363); `console.py` = `console` group (`list` + `import`, the wizard mirroring the GUI Add Console flow: detect RetroArch/cores/standalones → scan ROM folder → bulk import; ROM extension matching falls back to `rom_extensions` when `system_keys` is empty (PS2), and a shared-memcard console's (PS2) save/state resolve to the shared card/sstates location via `cli.detect._resolve_shared_memcard_save_state` rather than a per-game filename match, #361); `sync.py` = `sync status` + `sync history <slug>` / `sync restore <slug> <version-id>` (save/state rollback, #7 — `--state` targets states; restore makes a version current on the server and writes it to this device's disk if configured); `transfer.py` = top-level `push`/`pull`/`sync-daemon` + the transfer daemon loop (`push` streams a ROM to a target device; `pull` requests one from a source device, fulfilled by the source's sync-daemon; `sync-daemon` holds an SSE connection open, auto-receives incoming transfers, fulfills pending pull requests, and — if `watch_saves` is set — starts the background save watcher, see `watch.py`); `watch.py` = opt-in background save/state watcher (#242): `run_save_watcher`/`SaveWatcher` poll each local game's `save_path`/`state_path` and push on change, so saves from a non-EmuSync-wrapped session (plain RetroArch-direct, #210) still sync. Dependency-free polling; a file must be *settled* (`SETTLE_SECONDS`) before pushing; reuses `_save_is_safe_to_push` (truncation guard); skips a game locked by another device. Wired in via `_run_transfer_daemon(..., watch_cfg=cfg)` from both `sync-daemon` and the server-embedded daemon; `run.py` = the `run` command + the SIGTERM handler that kills the emulator child (registered at import time) + `_resolve_launch_command` (network-ROM launch-path resolution) + `_start_lock_heartbeat`; split (#368) into four sibling modules, each re-exported from `run.py` so `from cli.run import X` still works for existing callers/tests: `run_reconcile.py` (`_reconcile_save`/`_decide_save_action` — newest-wins: push if local mtime > server `pushed_at`, else pull, loser kept as `.bak` — plus post-launch written-path detection, `_resolve_written_save`/`_resolve_written_state`); `run_ps2.py` (PS2/PCSX2 shared-layout adapter — for a shared-memory-card console (`_SHARED_MEMCARD_CONSOLES`, currently `PS2`) `_reconcile_save` runs against the console card via the `_MemcardClient` adapter, mapping the per-game save API onto `/consoles/{key}/memcard`, with post-launch written-path adoption skipped for those consoles (#295); PCSX2 save states live in one SHARED folder named per game serial (`sstates/<SERIAL> (<CRC>).<slot>.p2s`), so for `_SHARED_STATE_CONSOLES` (`PS2`) states sync filtered by serial (#294) via `_ps2_state_serial_prefix`; also `_learn_ps2_serial`/`_read_pcsx2_playtime`, #301); `run_conflicts.py` (save-safety + conflict surfacing — a true divergence surfaces via `_warn_save_conflict`: stderr + `_notify` + `_log_save_conflict` → `save_conflicts.json` + `_report_conflict_to_server` → `POST /games/{slug}/conflicts` for the GUI Conflicts panel, #243; the post-game save push is gated by `_save_is_safe_to_push` (#213): a 0-byte save, or one that shrank below 50% of the server's previous copy (crash signal), is **not** pushed — the server copy is kept and the refusal surfaced via `_warn_unsafe_save`); `run_offline.py` (`_launch_and_wait` + offline fallback — if `client.health()` fails, `run.py` calls into `_run_offline`, which launches anyway and logs the play to `offline_plays.json`; `_cache_game_device`/`_load_cached_game_device` persist each game's paths under `game_cache/` so offline launches know the save path, server remains authoritative; `_cache_game_device` also takes an optional `game_name`/`console`, upserted into a sibling `game_cache/_offline_index.json` when given — the GUI's `game:offlineList` IPC reads it to show a fallback game list when the server can't be reached at all, #383). `_child_proc` (the tracked emulator child) lives in `run_offline.py`; `run.py`'s SIGTERM handler reads it via the module (`cli.run_offline._child_proc`), not a re-exported name, since a plain import wouldn't see later reassignment; `netrom.py` = network-ROM helpers: `path_is_reachable` (bounded mount-liveness probe before any network-path touch, so a dead mount never hangs launch/watcher/push), rel-path `normalize`/`sanitize`/`compute_rel_path`/`join_network` (portable POSIX rel-paths over POSIX/UNC roots), `localize_rom`/`delocalize_rom` (free-space-checked, atomic-via-temp+rename, master-guarded copy), `upload_to_master` (reverse of `localize_rom` — copy a local-only ROM UP to the share; skip-if-exists so a present master is never overwritten, #270); `rom.py` = `rom` group (`list`/`localize`/`delocalize` — copy a network ROM, or a whole `--console`, onto local disk for offline play and back; never touches the NAS master) |
| `server/api/` | FastAPI app, split into per-domain `APIRouter` modules (#224): `_core.py` owns the `app`, shared mutable state (`_store`/`_master_pin`/`_data_dir`/presence sets/`_device_event_queues`), `init()`, `_auth`, activity-log helpers (`_print_activity`/`_device_label`/`_game_label`), ROM-staging helpers, `/health`; `devices.py`/`games.py`/`transfers.py`/`blobs.py`/`locks.py`/`defs.py`/`conflicts.py` are the routers (`conflicts.py` = save-conflict records behind the GUI Conflicts panel — `POST /games/{slug}/conflicts`, `GET /conflicts`, `POST /conflicts/{id}/dismiss`, #243); `__init__.py` re-exports `app`+`init` and `include_router`s them (so `from server import api` still gives `api.app`/`api.init`). Routers reach reassigned globals via accessors (`_get_store()`, `get_data_dir()`), never by re-importing rebindable names. Auth via `Authorization: Bearer {PIN}` + `X-Device-ID`/`X-Device-Name`; routes: `/health`, `/games`, `/games/overview` (per-device batch: lock + last save + this device's config for every game in one call, registered before `/games/{slug}` so it isn't matched as a slug — used by the GUI list + lock poll instead of 3 requests/game), `/devices`, `/whoami`, `/saves`, `/states`, `/locks`, `/events`, `/events/stream` (SSE), `/games/{slug}/devices`, `/games/{slug}/network-source` (any device's network-share config for a game, so a device without it can join the rel-path to its own mount root — #270), `/game-devices`, `/devices/{id}/consoles`, `/devices/{id}/game-devices`, `/games/{slug}/rom-transfer`, `/rom-transfers/pending`, `/rom-transfers/{id}/file`, `/rom-transfers/{id}`, `/games/{slug}/rom-pull-request`, `/rom-pull-requests/pending`, `/rom-pull-requests/{id}`, `/console-defs`, `/system-defs`, `/console-folder-names`, `/standalones/{console_key}`; save/state history + rollback (#7): `GET /games/{slug}/save/history` + `POST /games/{slug}/save/restore` (+ `/state/` equivalents), `save/meta`/`state/meta` now also report `size`; in `blobs.py` save/state routes are thin wrappers over shared `_BlobKind`-parametrised handlers (`_pull`/`_push`/`_meta`/`_history`/`_restore`) dispatching to uniform store methods (`pull_<noun>_path`, `push_<noun>_file`, …) — #240; save/state integrity (#285): `GET /games/{slug}/integrity` (recomputes one game's verdict on demand — 0-byte/shrank/hash-mismatch/missing), `GET /integrity` (library-wide summary from the at-rest snapshot) + `POST /integrity/rescan`; the snapshot builds in `_core._run_integrity_sweep()` on startup (after `_sweep_stale_staging`), read via `get_integrity_status()` — no schema column, computed from row metadata + on-disk bytes; console-scoped shared memory card (#295, `blobs.py`): `GET/POST /consoles/{console_key}/memcard` + `GET /consoles/{console_key}/memcard/meta` — one card per console keyed by abbr (e.g. `PS2`), shared across the console's games (single-generation/console-keyed; used by PS2 via `run.py`'s `_MemcardClient`); `_auth` auto-registers devices on first request; `GET /devices` includes `is_online`; `init()` accepts optional `data_dir` for ROM staging; `_device_event_queues` maps device IDs to asyncio queues for SSE delivery; `settings.py` = shared SteamGridDB API key (`GET`/`PUT /settings/steamgriddb-key`), a generic `server_settings` key-value store entered once on the server device and fetched by every connected device's Electron process so art fetching doesn't need a per-user key (#322); `games.py`'s `GameRequest`/`PUT /games/{slug}` also accepts optional `sgdb_game_id` — a manually-picked SteamGridDB match remembered per game (#325), left untouched when omitted (same truthy-check pattern as `console`); `DELETE /games/{slug}/device` (#343) unlinks the game from the calling device only — idempotent, other devices untouched — vs. `DELETE /games/{slug}` which fully purges the game everywhere |
| `server/store/` | SQLite via stdlib `sqlite3`, split into a package: `__init__.py` composes `Store` from one mixin per table-group and re-exports the public surface (`Store`, `LOCK_TTL_HOURS`, `upsert_console_for_game`, dataclasses); `connection.py` = `_ThreadLocalConnection` (one SQLite connection per thread); `schema.py` = `_SCHEMA`/`_SCHEMA_VERSION`/`_migrate`; `models.py` = row dataclasses; `_base.py` = `StoreBase` (connection + schema/migration setup); `devices.py`/`games.py`/`blobs.py`/`locks.py`/`events.py`/`transfers.py`/`consoles.py`/`console_defs.py` = per-domain CRUD mixins. Tables: `devices`, `consoles`, `games`, `game_devices`, `saves`, `states`, `locks`, `events`, `rom_transfers`, `rom_pull_requests`, `console_defs`, `system_defs`, `core_defs`, `console_folder_names`, `standalone_emulators`, `save_conflicts`, `console_saves`, `server_settings`; schema v15 (v15: `games.sgdb_game_id`, a manually-picked SteamGridDB match shared across devices via the `games` row, set through `PUT /games/{slug}`, untouched by a plain rename — #325; v14: `server_settings` generic key-value table, currently the shared SteamGridDB key — #322; v13: `console_saves`, one memory card per `console_key` shared across a console's games (PS2/PCSX2), single generation, bytes under `blobs/console_saves/<key>`, methods `push_console_save_file`/`pull_console_save_path`/`get_console_save_meta` mirror per-game saves but console-keyed — #295; v12: `console_defs.rom_extensions` decoupling scannable ROM extensions from core-derived `systemKeys` so a standalone-only console with no libretro core (PS2) scans the right files, plus `standalone_emulators.launch_args` so PCSX2 boots with `-batch -fullscreen`; `get_console_defs` returns `romExtensions` (falling back to `systemKeys`); `consoles_data.py` adds the `ps2`/PCSX2 def — #293; v11: `standalone_emulators.dirs_json`, an extensible `~`-templated per-emulator dir-path blob keyed native/flatpak → save/state/memcard, so PCSX2 carries its state + memcard dirs — the seed now actually emits each console's `standalones` (previously hardcoded `[]`) and `console_defs.py` round-trips them via `_standalone_row_to_dict` — #292; v10: network-ROM source columns (#255): `consoles.device_network_folder`/`device_local_folder` + `game_devices.rom_source`/`rom_rel_path`/`local_rom_path`/`rom_sha256`, existing rows default `rom_source='local'`; v9: `save_conflicts` via `ConflictMixin` — `add_conflict`/`list_open_conflicts`/`dismiss_conflict`, #243; v8 moves save/state bytes onto disk, #239; v7 adds `rom_transfers.sha256`, #214; v6 adds `console_key` to `core_defs`). `blobs.py` (`SaveStateMixin`) stores blob **bytes on disk** under `<data_dir>/blobs/<saves|states>/<row id>` — only metadata (`hash`/`pushed_at`/`size`/`device_id`) lives in the row (#239), keeping the DB small even with large state archives × `HISTORY_LIMIT`. **Keeps history**: `_push_blob`/`_push_blob_file` append a new generation (deduping identical consecutive content), `_prune_history` prunes to the newest `HISTORY_LIMIT` (20) per game, unlinking pruned files; the *current* blob is the most recent row (`rowid` DESC). `push_save_file`/`pull_save_path` (+ state) stream uploads to a staged temp file (`new_upload_path()`) and serve pulls via `FileResponse` with no in-memory buffering; `remove_game` calls `delete_blobs_for_game` before the FK cascade; `remove_game_device(slug, device_id)` (#343) deletes just one `game_devices` row, leaving the game/saves/other devices alone. `list_save_history`/`restore_save` (+ state) back rollback; `restore` re-inserts a past version as a new generation so history only grows forward; `integrity_for_game(slug)`/`sweep_integrity()` + private `_classify_blob`/`_last_good_version` classify a game's current blob ok/damaged/missing (0-byte, shrank below `_SHRINK_FLOOR`=0.5, hash mismatch, or file gone) and surface the newest healthy generation — no schema column, computed from metadata + blob (#285); `ensure_device()` returns `(device, is_new)`; `rom_transfers`/`rom_pull_requests` track pending deliveries/requests; `console_defs`/`system_defs`/`core_defs`/etc. store global emulator/console defs seeded by `cli/server.py` (data from `consoles_data.py`); `upsert_console_for_game(store, device_id, console_name, rom_path, save_path, rom_folder_path)` (used by both `server/api/games.py` and `cli/game.py`) infers emulator/folder paths and creates-or-updates the `Console` row; `settings.py` (`SettingsMixin`) backs `server_settings` (v14) |
| `server/config.py` | TOML config dataclass; load/save `~/.emusync/emusync.toml` |
| `server/mdns.py` | mDNS advertise + LAN discovery via `zeroconf` |
| `server/sync_client.py` | HTTP client wrapping all server endpoints (used by `emusync run`, `push`, `pull`); persistent `httpx.Client` (keep-alive); sends PIN + device headers; `GameDeviceConfig` holds `rom_path`, `save_path`, `launch_command`, `state_path`, `rom_folder_path`, `rom_source`, `rom_rel_path`, `local_rom_path`, `rom_sha256`, `device_network_folder`, `device_local_folder` (the last two are transient — they populate the console row's per-console network/local folder config when passed to `set_game_device`); `remove_game_device(slug)` unlinks the game from this device only (`DELETE /games/{slug}/device`, #343), leaving other devices/history untouched — vs. `remove_game(slug)`'s full purge; the CLI's `game remove` defaults to the former (#363); `list_my_game_devices()`, `list_device_games()`, `get_device_consoles()`, `create_rom_transfer()`, `create_pull_request()`, `list_pending_pull_requests()`, `complete_pull_request()` drive push/pull; `download_transfer()` verifies against `X-Rom-Hash`/recorded SHA256, deleting the partial file on mismatch (#214); `list_save_history()`/`restore_save()` (+ state, via private `_list_history`/`_restore` — #240) back history/rollback; `get_console_memcard_meta()`/`pull_console_memcard()`/`push_console_memcard()` are the console-scoped card methods the PS2 `_MemcardClient` drives (#295); supports both file- and folder-based memcards (PCSX2 `.ps2` dirs). **PCSX2 nests each game's saves one level down** (e.g. `GAME1/GAME1`, `GAME1/icon.sys`) — `memcard_bytes(card_path)` walks the *whole tree* (`rglob`, not top-level `iterdir`) and serialises it as a deterministic plain tar (sorted, mtime=0, relative paths) for a stable SHA-256 — a top-level walk silently drops every game's data (#320). `_write_memcard(card, data)` detects tar archives on pull, backs up the **entire memcard folder** as `<card>.bak` (`shutil.copytree`) before extracting through `_safe_extract_tar` (the same path-traversal guard used for state archives); falls back to a raw-file write for a legacy file-based memcard. The `memcard:push`/`memcard:pull` IPCs mirror this: push packs with `tar -cf`, pull probes with `tar -tf`, backs up with `cp -r` to `<name>.bak`, extracts with `tar -xf` |
| `gui/electron/` (main process) | Split into per-domain modules (#222) — `main.ts` is just IPC registration + app lifecycle (calls each module's `register*Ipc()`). Shared mutable state (server/game/daemon process handles, window, console-def caches) lives on the single `rt` object in `runtime.ts` (ES modules only export read-only bindings, so cross-module reassignment needs an object). Modules: `runtime.ts` (constants `CONFIG_PATH`/`SCRIPT`/`PYTHON` + `rt`); `http.ts` (`httpGetJSON` — main process must use Node http, not `fetch`); `window.ts` (`createWindow`); `config-store.ts` (`config:*` IPC + `loadServerCfg`); `server.ts` (server + sync-daemon lifecycle, `server:*`/`daemon:*` IPC, `startServerProcess`/`killServerByPid`/`killOrphanServers`); `game.ts` (`game:*` IPC + `launcher:path`); `files.ts` (dialogs, `files:*`, `device:probe`, `findLatestFileInDir`); `sync.ts` (`save:*`/`state:*`/`rom:push`/`rom:localize`/`rom:delocalize` IPC — localize handlers do the free-space-checked, atomic, master-guarded local copy and update the server game config, #255) is a thin composer calling one `register*Ipc()` per domain, split (#370) into `sync/save.ts` (`save:push`/`save:pull`), `sync/memcard.ts` (console-scoped shared memory card push/pull, PS2/PCSX2, #295), `sync/state.ts` (save-state folder push/pull as tar.gz), `sync/rom.ts` (`rom:push`/`localize`/`delocalize`/`deleteFile`/`uploadMaster`/`setupNetworkPlay` + private helpers `tailSegments`/`consoleSaveStateFolders`/`consoleLocalFolder`/`sha256OfFile`), `sync/recovery.ts` (`recovery:listLocalBackups`/`restoreLocalBackup`, #285) — `main.ts`'s `import { registerSyncIpc } from "./sync"` is unchanged; `emulator/{types,console-defs,detect,scan,ipc}.ts` (import-wizard subsystem — `emulator:consoles`/`detect`/`scan` lazily fetch console defs from the Python API); `steamgriddb.ts` (`getSteamGridDbKey()` + `steamgriddb:getKey`/`setKey`/`openKeyPage` IPC — fetches/sets the shared key via the server API, opens `steamgriddb.com/profile/preferences/api`; `art.ts`'s `art:get` tries SteamGridDB first when a key is configured, falling back to libretro-thumbnails exact-match, #322); `artwork.ts` (`artwork:searchGames`/`listCandidates`/`setArt`/`clearArt`/`getCurrent`/`refreshAll` IPC backing the Artwork tab, #325 — reuses `art.ts`'s exported `ART_DIR`/`ART_TYPES`/`download`/`getSgdbImagesForType`/`makeSteamGridDbClient`/`toDataUrl` rather than duplicating the type→SGDB branch or ESM/CJS workaround). Shared emulator types (`DetectedEmulatorOption`, `EmulatorScanResult`, `RomEntry`) live in `emulator/types.ts`, type-imported by `preload.ts`; `steam.ts` (`steam:addGame` IPC, issue #385 — adds a per-game non-Steam-game shortcut to the local Steam client via the `steam-shortcut-editor` npm package (binary `shortcuts.vdf`, read-modify-write; existing entries are matched by `exe`+`LaunchOptions` with **case-insensitive property names** and quote-stripped exe values — Steam rewrites the file with its own key casing on restart (`exe`→`Exe`, `AppName`→`appname`), so exact-cased matching duplicates the shortcut after a Steam restart; matching entries are filtered out and one canonical entry re-added, which also collapses pre-existing duplicates); the shortcut's `exe`/`LaunchOptions` just re-invoke `emusync run <slug>` via the launcher path, so it never needs to know the actual emulator command; copies EmuSync's already-cached artwork (`art.ts`'s `ART_DIR`) into Steam's `config/grid/<appid>{p,'',_hero,_logo}.png` (portrait grid / wide header capsule / hero / logo) and points the shortcut's `icon` at the cached `icon.png` — the appid keying BOTH the artwork filenames and the vdf entry is the **unsigned 32-bit** `crc32(rawExe+appname)|0x80000000`, where `rawExe` is the *unquoted* launcher path (quotes are serialization-only, not hash input) and the vdf `appid` field stores the same bits as signed int32; the 64-bit `(crc<<32)|0x02000000` variant in community docs is only the legacy Big Picture banner id — either mistake makes Steam silently ignore the art (both confirmed on a real client); best-effort groups the game into a Collection named after the console's full label (resolved abbr→label in `GameConfig` via `emulator:consoles`): modern clients store collections in `config/cloudstorage/cloud-storage-namespace-1.json` — an array of `[key, entry]` pairs where a live `user-collections.<id>` entry's `value` is a JSON string `{id, name, added: [unsigned appids], removed}` and deleted collections persist as `is_deleted` tombstones (never resurrect them); `upsertCloudCollection` reuses an existing live collection with the same *name* (e.g. one made by Steam ROM Manager) else creates `emusync-<base64(name)>` (mirroring SRM's `srm-` convention, with `conflictResolutionMethod: "custom"`/`strMethodId: "union-collections"`), and every write must bump BOTH the entry `version` and namespace 1's version in `cloud-storage-namespaces.json` (Steam reconciles local/cloud by comparing them) — format confirmed against a real 2026 client, #387; the `"user-collections"` key in `localconfig.vdf` (what #385 originally targeted) still exists on modern clients but is legacy and **ignored** — `upsertCollection` (regex-upsert of that key) remains only as the fallback when no cloudstorage store exists; if neither store is recognized, the shortcut/artwork are still applied and a `warning` is returned instead of failing; refuses to write while Steam is running, verified via `~/.steam/steam.pid` liveness on Linux (no equivalent check on Windows); with more than one Steam account's userdata folder present, picks whichever has the most-recently-modified `localconfig.vdf` rather than parsing `loginusers.vdf`'s `mostrecent` flag) |
| `gui/electron/preload.ts` | `contextBridge` — everything in `window.emusync.*` is defined here |
| `gui/renderer/src/api.ts` | Fetch wrapper for the Python REST API; holds `_base` URL + `_token` |
| `gui/renderer/src/gameDelete.ts` | `deleteGame(slug, {deleteLocalRom, removeEverywhere})` (#343) — tiered delete shared by `GameConfig.tsx`'s single-game delete and `GameGrid.tsx`'s bulk delete. Tier 1 (always): `removeGameDevice` unlinks this device. Tier 2 (`deleteLocalRom`): also deletes the local ROM — `rom:delocalize` for a network ROM's localized copy (own empty-dir cleanup), `rom:deleteFile` for a local-source ROM. Tier 3 (`removeEverywhere`): also deletes the network-share master (if network-sourced) then calls the full-purge `removeGame` (every device, save/state history, blobs) |
| `gui/renderer/src/time.tsx` | Timestamp formatting (#216): `formatRelative()` + `<RelTime>` render a relative phrase ("2 hours ago") with the exact local 12-hour time in a hover tooltip. **All timestamps are UTC** (server `isoformat()`, Electron `toISOString()`), and a tz-less ISO string parses as *local* in JS — so `parseUtc()` appends `Z` when no offset/`Z` is present. Used by SaveHistory, DevicesButton, ServerStatusButton, GameConfig |
| `gui/renderer/src/App.tsx` | Root component; screen router; auto-starts server if `is_server=true`; on the console screen the topbar shows the console abbr/label/game-count (reusing `GameGrid`'s `.game-grid-abbr`/`-label`/`-total` classes) next to the "‹ Back" link, grouped in one flex item since `.topbar` uses `justify-content: space-between` (#349); this "‹ Back" link (#351) is the only back control — `GameGrid` dropped its own redundant one (#350); mouse back/forward side buttons also work (`MouseEvent.button === 3`/`4`) via a single always-registered `mouseup` listener driven by refs (not state, so it isn't re-subscribed on screen change): back mirrors "‹ Back" (console→games), forward re-enters the most recently left console, one level deep — only `games`↔`console` history (#354, #356) |
| `gui/renderer/src/components/Setup.tsx` | First-launch onboarding (choose server or join) |
| `gui/renderer/src/components/ServerStatusButton.tsx` | Server control panel modal (start/stop, PIN, LAN discovery, re-pair) |
| `gui/renderer/src/components/DevicesButton.tsx` | Paired devices list modal (count, last sync times, per-device delete) |
| `gui/renderer/src/components/ConsoleGrid.tsx` | Home screen: grid of console cards (one per imported console), icon/abbr/label/game-count with a colour accent; click drills into the game grid. Fetches console-def list via `emulator:consoles` to map stored abbr → key (#304) |
| `gui/renderer/src/components/GameGrid.tsx` | Per-console game grid: `GameCard` tiles split into "On this device"/"On other devices"; live search filter, `GameFilterButton` popover (#345), artwork-type dropdown (grid/wide_grid/hero/logo/icon, persisted to `art_type_by_console` — #324, wide_grid #333; changing it remounts every visible `GameCard` via a type-inclusive `key` so they re-fetch); no back button of its own (dropped as redundant, #350/#351) or `consoleLabel`/`consoleAbbr` props (moved to `App.tsx`'s topbar, #349); opens `GameModal`/`NetworkPlaySetup` as needed (#304); multi-select bulk delete offers the same tiered `deleteGame` checkboxes as `GameConfig.tsx` (#343); a Select All/Deselect All button (`toggleSelectAll`) sits left of Delete, toggling over `filtered` (the currently visible games after search + filter, not the full list — #353); both header buttons always render (disabled when inapplicable) rather than appear/disappear, sized to match the dropdown/search box via `.game-grid-header-btn` (#347) |
| `gui/renderer/src/components/GameFilterButton.tsx` | Filter popover next to the search box (#345): 3 checkbox groups — Artwork (with/without), Saves (on device/not), ROM availability (localized/not) — OR-within-group, AND-across-groups via exported `matchesFilters`. "Localized" checks whether the ROM's bytes are actually on this device right now (`romSource !== "network" \|\| hasLocalCopy`), not just whether the game is network-sourced. Saves reads straight off `GameRow.lastSave`; artwork has no such field, so `GameGrid` lifts each `GameCard`'s `art:get` result via `onArtStatus` into a `hasArt` map instead of a duplicate fetch — an unresolved game (`undefined`) passes the filter rather than being hidden while loading. Closes on outside click; badges the button with the active filter count |
| `gui/renderer/src/components/GameCard.tsx` | Individual game card: fetches artwork via `art:get` (SteamGridDB primary, libretro-thumbnails fallback for grid type), falls back to a colour-gradient placeholder, reports the result up via `onArtStatus(slug, hasArt)` for `GameFilterButton` (#345); `artType` prop picks the tile's CSS treatment (`game-card-art-{grid,wide_grid,hero,logo,icon}`) since Hero/Logo/Icon aren't boxart-shaped (#324, wide_grid #333); clicking anywhere opens the settings modal (`onSettings`) except the ▶ play button and selection checkbox, which `stopPropagation` (#337, replacing a standalone ⚙ button); shows status badges (locked, other-device, network ROM) (#304) |
| `gui/electron/art.ts` | `art:get` IPC: checks `~/.emusync/art/<consoleKey>/<slug>/<type>.png` cache (one folder per console/game, one file per type — `type` resolved per-console from `art_type_by_console`, default `grid`; #324, wide_grid #333), then tries SteamGridDB (`fetchFromSteamGridDb` — resolves the SGDB game via shared `resolveSgdbGameId` (also used by `artwork:refreshAll`'s fallback): reuses `sgdb_game_id` if set, else fuzzy-searches via `searchGame` and **persists the top result as `sgdb_game_id`** via `PUT /games/{slug}` so every later fetch on any device reuses the same match (#339; a manual pick always overwrites it). Then `getSgdbImagesForType` (shared per-type SGDB dispatch — grid calls `getGrids` filtered to `dimensions: ["600x900"]`; wide_grid calls `getGrids` unfiltered and keeps results with `width > height` since exact-dimension filtering under-populated results, #341; hero/logo/icon call their own SGDB methods) fetches the resolved type, using the key from `steamgriddb.ts`; no-op if no key), before falling back — **grid only** — to the exact-filename `raw.githubusercontent.com/libretro-thumbnails/<System>/master/Named_Boxarts/<GameName>.png` lookup; atomic temp→rename write; returns `file://` URL or null (#304, #322, #324) |
| `gui/renderer/src/components/NetworkPlaySetup.tsx` | Play-time cross-device setup modal (#270) — for a game not set up on this device, offers (A) point this device at the same network share (folder-pick a mount root → `rom:setupNetworkPlay` → verify + write network config → play) or (B) pull the ROM from a device that has it via `createPullRequest` (delivered by the source's sync-daemon). Reads `GET /games/{slug}/network-source` + `/games/{slug}/devices` |
| `gui/renderer/src/components/ConflictsButton.tsx` | Top-bar "⚠ Conflicts" panel (#243) — polls `GET /conflicts`, lists auto-resolved divergences, recovers the losing copy by finding it in `save/history` by hash and restoring it (+ `save:pull` if local); shows `.bak` guidance when the loser never reached the server. Only renders when there are open conflicts |
| `gui/renderer/src/components/SaveHistory.tsx` | Per-game save/state recovery modal (#7 + #285) — merges server save **and** state history with this device's local `.bak` losers into one chronological, kind-tagged timeline; flags a damaged current blob (⚠, from `GET /games/{slug}/integrity`) with one-click "Restore last good" (`last_good_version_id`); a normal row Restore makes a version current server-side and (if local) writes it via `save:pull`/`state:pull`; a `local-bak` row recovers via `recovery:restoreLocalBackup`. Suggest-only, never auto-acts. Takes `savePath` + `statePath` props (threaded through `GameModalTarget`/`GameRow`) |
| `gui/renderer/src/components/GameConfig.tsx` | Add/edit game form with file pickers + the rename-heavy `handleSave` (renaming a game renames its on-disk ROM/save/state via `renameGameFiles`, #289); Delete confirm offers the tiered `deleteGame` options (#343) — two checkboxes ("delete ROM from local folders", "remove from all devices and delete network ROM") on top of the always-happening this-device unlink. Split (#372) into `game-config/SyncLine.tsx` (the compact sync-status row, presentational only), `game-config/useGameSync.ts` (save/state/memcard sync state + push/pull handlers + `loadSyncInfo`, parameterized by slug/savePath/statePath/gameConsole/sharedLayout), and `game-config/NetworkRomPanel.tsx` (network-ROM #255 localize/delocalize UI; `localRomPath` stays lifted in `GameConfig` since `handleSave`'s rename logic needs it, passed down with an `onLocalRomPathChange` callback); an existing (non-new) game's form also has an "Add to Steam" button calling `window.emusync.steam.addGame`, surfacing its `ok`/`warning`/`error` result inline (#385) |
| `gui/renderer/src/components/GameModal.tsx` | Tabbed per-game modal (#260): Settings (`GameConfig`), Artwork, Devices, Save history, Run. Owns active-tab state; each tab is a separate embedded component |
| `gui/renderer/src/components/ArtworkTab.tsx` | Artwork tab (#325): search SteamGridDB (`artwork:searchGames`) → scrollable results (~4 rows) → picking a result persists `sgdb_game_id` via `setGameSgdbId` (shared across devices); 5 current-artwork tiles (`artwork:getCurrent`, read-only cache lookup); clicking a tile opens a picker (`artwork:listCandidates`, thumbnails via `<img src>` straight from SteamGridDB's CDN) — if no match is picked/resolved yet it first calls `artwork:resolveMatch` to fuzzy-search-and-persist on demand rather than blocking with "search first" (#339 follow-up, covers art cached before that persistence existed) — with a red-× to clear (`artwork:clearArt`) and click-to-replace (`artwork:setArt`); one Refresh-all button (`artwork:refreshAll`) re-fetches all 5 types bypassing the cache. On mount, an already-set `sgdb_game_id` is resolved to a name via `artwork:getMatchedGame` and shown as "✓ Matched: <name>" (the results list itself starts empty every mount, so without this the pick looked reset on reopen — #335). Derives `consoleKey` from `gameConsole.toLowerCase()` rather than threading a prop — every seeded console's abbr lowercases to its key |
| `gui/renderer/src/components/ConsoleImport.tsx` | "Add Console" wizard modal — console dropdown → emulator detection → ROM scan → import. Thin shell running the `useConsoleImport` state machine and rendering the step component for the current phase (#229). Pieces live in `components/console-import/`: `types.ts`, `helpers.ts` (pure/testable: `slugify`/`getConsoleAbbreviation`/`resolveRomFolder`/`annotateRoms`/`dedupeAndLink`/`groupByDir`/`classifyByRoot`), `useConsoleImport.ts` (the phase state machine + scan/dedup logic; returns a `ConsoleImportVM`) — split (#374) two chunks of async logic that don't touch hook state directly out into sibling modules: `resolveRomPaths.ts`'s `resolveImportPaths(rom, opts)` (per-ROM rename + network upload-to-share/rel-path resolution, called from `_runImport`'s loop) and `postImport.ts` (`prefetchArt`/`pullFromServerIfNewer`/`_serverIsNewer`/`autoPush`, each taking the relevant setters as parameters instead of closing over the hook). Network-source imports (#270) also scan the console's local-copy folder so an already-local ROM is detected — `classifyByRoot` tags each network-only/local-only/both; a local-only ROM is uploaded to the share via `rom:uploadMaster` and registered as already-localized (`local_rom_path` = the existing file); a "both" ROM registers with its local copy already linked; after import, `pullFromServerIfNewer` pulls any save/state (or, for a shared-layout console, the memory card) already on the server and newer than local, so a new device doesn't start from an empty save (#316); one component per phase (`ConsoleStep`/`EmulatorStep`/`ResultsStep`/`DoneStep` + shared `Stepper`/`Spinner`) |

---

## Development commands

```bash
# Full install (run once after cloning)
bash install.sh

# Start Python server manually
make dev-server                  # uses .venv/bin/python

# Start GUI (dev mode with hot reload)
make dev-gui                     # cd gui && npm run dev

# Run tests
make test                        # pytest tests/ -v

# Lint Python
make lint                        # syntax check only (py_compile)

# Build GUI for distribution
make build-gui                   # electron-vite build

# Cut a release (tags + pushes, triggers GitHub Actions)
make release VERSION=v1.2.3

# Install / remove the systemd user service (Steam Deck / headless server)
make install-service             # generates service file, enables + starts it
make uninstall-service           # disables + removes it
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| CLI | Python 3.10+, Click |
| API server | FastAPI + uvicorn |
| Database | SQLite (stdlib `sqlite3`, WAL mode) |
| Service discovery | zeroconf (mDNS) |
| Config | TOML via `tomlkit` |
| GUI shell | Electron 31 |
| GUI framework | React 18 + TypeScript |
| GUI build | electron-vite + Vite 5 |
| HTTP client (renderer) | native `fetch` |
| HTTP client (Python) | httpx |

---

## IPC bridge

`preload.ts` exposes `window.emusync.*` via `contextBridge`. `main.ts` registers matching `ipcMain.handle` handlers.

**Current surface:**

```typescript
window.emusync.config.load()                          // reads ~/.emusync/emusync.toml
window.emusync.config.save(data)                      // writes config
window.emusync.config.exists()                        // boolean
window.emusync.config.getRecentFolders(consoleKey)   // string[] of recent ROM folders for console
window.emusync.config.addRecentFolder(consoleKey, path) // adds folder to recent list (max 10)

window.emusync.server.start()     // spawns emusync.py server start → { ok: boolean }
window.emusync.server.stop()      // SIGKILL server + pkill orphans + clean pid file
window.emusync.server.changePin(pin) // stops server, saves PIN to config, restarts
window.emusync.server.discover()  // runs emusync.py server discover-json → server list
window.emusync.server.localIp()   // this machine's LAN IPv4 (os.networkInterfaces); null if none

window.emusync.dialog.openFile()  // native file picker
window.emusync.dialog.openFolder() // native folder picker

window.emusync.emulator.consoles()          // ordered console list { key, label, abbr }[] for the dropdown (abbr = the game's stored console value — #230)
window.emusync.emulator.detect(consoleKey)  // scans for installed emulators for that console: RetroArch (native+flatpak) cores + standalones (mGBA etc.); looks for console-specific ROM subfolders within the configured ROM dir; resolves per-core save subfolder; returns { options: DetectedEmulatorOption[], suggestions[] }
window.emusync.emulator.scan(consoleKey, emulatorOption, extraPaths[])  // scans only that console's ROM extensions using emulatorOption.saveDir (already core-resolved); returns { emulators, romDirs, roms[] } with consoleName+coreName per entry
window.emusync.files.ensureSave(path)       // creates an empty save file + parent dirs if missing; used during import for games with no existing save
window.emusync.files.getSaveTime(path)      // last-modified ISO string of the save file, or null if missing
window.emusync.files.getLatestInFolder(dir) // {path, time} for the newest file in dir, or null if empty/missing
window.emusync.files.getPs2LastPlayed()      // {slug: ISO} — PS2 per-game last-played, joining ~/.emusync/ps2_serials.json (slug→serial, learned by `emusync run`) with PCSX2's live playtime.dat (serial→last-played); fills the gap left by the shared memory card (#301)
window.emusync.files.renameGameFiles({romPath, savePath, stateFolder, newBase, reorganize, secondaryRomPath?}) // renames a game's ROM (+ optional secondary copy, e.g. a network ROM's local copy) and its save/state to `newBase` (sanitized title); reorganize=true nests a flat ROM under <dir>/<newBase>/, else renames in place; save/state targets recompute from newBase under the same roots, current+legacy files migrated; best-effort no-op on a missing/already-correct source; returns {ok, newRomPath, newSavePath, newStateFolder, newSecondaryRomPath?, error?} (#283, generalises the old move-to-subfolder)

window.emusync.save.push(slug, savePath)   // reads local save, POSTs to /games/{slug}/save; {ok, error?}
window.emusync.save.pull(slug, savePath)   // GETs /games/{slug}/save, backs up existing file to .bak, writes new bytes; {ok, pulled, error?}

window.emusync.state.push(slug, stateFolder) // tar.gz's stateFolder, POSTs to /games/{slug}/state; {ok, error?}
window.emusync.state.pull(slug, stateFolder) // GETs the state archive, backs up existing files to .bak (retained on success — one generation), extracts; restores backups on failure; {ok, pulled, error?}

window.emusync.memcard.push(consoleKey, cardPath) // reads the local card, POSTs to /consoles/{key}/memcard; backs the manual "Push memory card" button for shared-layout consoles (#319); {ok, error?}
window.emusync.memcard.pull(consoleKey, cardPath) // GETs /consoles/{key}/memcard, backs up existing file to .bak, writes new bytes; used by the import wizard post-import (#316) and GameConfig's manual pull (#319); {ok, pulled, error?}

window.emusync.device.probe(ip, port)      // TCP probe: true if ip:port reachable within 2s

window.emusync.rom.push(slug, toDeviceId, consoleName)  // stage a local ROM to another device via the server
window.emusync.rom.localize(slug, destFolder?)          // copy a network ROM onto local disk for offline play (free-space precheck, atomic temp+rename, sha256, updates server config); destFolder used only when no local_rom_path stored; {ok, localPath?, error?} — #255
window.emusync.rom.delocalize(slug)                     // delete the localized copy (never the NAS master) + clear local_rom_path/rom_sha256; {ok, error?} — #255
window.emusync.rom.uploadMaster(localPath, networkPath) // copy a local-only ROM UP to the share so it becomes the master (skip if a master exists; free-space precheck, atomic, sha256-verified); {ok, sha256?, skipped?, error?} — #270
window.emusync.rom.setupNetworkPlay(slug, mountRoot)    // for a game on a share configured by another device, point THIS device at it: verify join(mountRoot, rom_rel_path) exists, derive local save/state paths, write a network-source config; {ok, romPath?, error?} — #270
window.emusync.rom.deleteFile(absolutePath)              // bare unlink; used by the tiered delete flow (gameDelete.ts) for a local-source ROM and a network master — a localized copy instead goes through rom:delocalize; {ok, error?} — #343

window.emusync.recovery.listLocalBackups(savePath, stateFolder) // enumerate on-disk .bak losers: `<save>.bak` + the state folder's `*.bak` (size/mtime); fs touches guarded so a dead mount returns empty, never hangs; {saves: LocalBak[], states: LocalBak[]} — #285
window.emusync.recovery.restoreLocalBackup(bakPath, targetPath) // restore a .bak back into place (reads bak bytes first to avoid the self-overwrite race, atomic, Windows-safe); local-only, no server push; {ok, error?} — #285

window.emusync.launcher.path()             // absolute path to emusync launcher binary

window.emusync.game.launch(slug)           // spawns `emusync run <slug>` (emulator command derived server-side)
window.emusync.game.stop()                 // SIGKILL game process group (in-app launches)
window.emusync.game.stopExternal()         // kill emulator + emusync via .game_pid file (Steam launches)
window.emusync.game.hasPidFile()           // true if .game_pid exists, process is alive, cmdline contains emusync/python
window.emusync.game.isRunning()            // boolean
window.emusync.game.offlineList()          // {slug, name, console, savePath?, statePath?}[] read from ~/.emusync/game_cache/_offline_index.json — fallback game list for when the server can't be reached at all (#383)
window.emusync.game.onExited(cb)           // subscribe to game:exited
window.emusync.game.offExited(cb)          // unsubscribe

window.emusync.art.get(slug, gameName, consoleKey) // fetch this console's configured artwork type: checks ~/.emusync/art/<consoleKey>/<slug>/<type>.png, on miss tries SteamGridDB then (grid only) libretro-thumbnails (Named_Boxarts/<GameName>.png, keyed by consoleKey → libretro system name); caches to disk; file:// URL or null (#304, #324)
window.emusync.art.getConsoleIcon(consoleKey) // fetch the white monochrome system logo: checks ~/.emusync/art/consoles/<key>.png, on miss downloads from libretro/retroarch-assets (xmb/monochrome/png/<SystemName>.png); caches; file:// URL or null (#304)

window.emusync.daemon.start()              // spawn emusync sync-daemon (client devices only; no-op if already running or on the server)
window.emusync.daemon.stop()               // kill the sync daemon if running

window.emusync.steamgriddb.getKey()        // fetches the shared SteamGridDB key from the server; cached in-memory for this process
window.emusync.steamgriddb.setKey(key)     // PUTs a new shared key; only the server device's UI exposes an edit control (#322)
window.emusync.steamgriddb.openKeyPage()   // opens steamgriddb.com/profile/preferences/api

window.emusync.steam.addGame(slug, gameName, consoleName, consoleKey) // adds/updates a Steam non-Steam-game shortcut + artwork + best-effort console Collection; {ok, warning?, error?} (#385)

window.emusync.artwork.searchGames(name)                       // SteamGridDB searchGame — candidates for the Artwork tab's results list (#325)
window.emusync.artwork.getMatchedGame(sgdbGameId)               // SteamGridDB getGameById — resolves an already-picked sgdb_game_id's name for the "✓ Matched" display on reopen (#335)
window.emusync.artwork.resolveMatch(slug, gameName)             // on-demand fuzzy-search-and-persist for a game with no sgdb_game_id yet (#339 follow-up)
window.emusync.artwork.listCandidates(sgdbGameId, type)         // all images of one type for a SteamGridDB game — powers the picker modal
window.emusync.artwork.setArt(slug, consoleKey, type, url)      // downloads a picked candidate into <consoleKey>/<slug>/<type>.png, overwriting
window.emusync.artwork.clearArt(slug, consoleKey, type)         // deletes that type's saved file
window.emusync.artwork.getCurrent(slug, consoleKey)             // read-only: whatever's already cached for all 4 types, no network fetch
window.emusync.artwork.refreshAll(slug, gameName, consoleKey, sgdbGameId) // re-fetches all 4 types fresh, using sgdbGameId if given else name search first
```

When adding a new IPC channel: register the handler in the relevant `gui/electron/` module (via its `register*Ipc()`), add the bridge entry to `preload.ts`, AND add the typed signature to `EmusyncBridge` in `gui/renderer/src/emusync.d.ts` (#228) — `window.emusync` is globally typed from that `.d.ts`, no longer `any`.

---

## Config and data paths

| Path | Contents |
|------|----------|
| `~/.emusync/emusync.toml` | Per-device config (server host/port/PIN, device ID/name, is_server flag, recent ROM folders) |
| `~/.emusync/emusync.db` | SQLite database (devices, games, saves, locks) |
| `~/.emusync/.server_pid` | PID of the running server process (written on start, deleted on clean exit) |
| `~/.emusync/server.log` | Rotating mirror of the server's timestamped stdout log (stdout only), capped ~5MB with up to 3 backups (`.1`–`.3`); written by `_RotatingLogWriter` via `_TimestampedStream` (#268) |
| `~/.emusync/.game_pid` | Two-line file: line 1 = emusync run PID, line 2 = emulator child PID (written by `emusync run`, deleted on exit) |
| `~/.emusync/blobs/{saves,states}/{row-id}` | Save/state blob bytes (one file per retained generation); `saves`/`states` rows hold only metadata. `blobs/.uploads/` holds in-flight streamed uploads (#239) |
| `~/.emusync/rom_staging/` | Staged ROM files for pending transfers (`{transfer_id}{ext}`); created by `POST /games/{slug}/rom-transfer` |
| `~/.emusync/game_cache/{slug}.json` | Cached per-device game config, written by `emusync run` on each online launch so an offline launch knows the paths |
| `~/.emusync/game_cache/_offline_index.json` | `{slug: {name, console}}`, upserted alongside the per-slug cache on each online launch; read by the GUI's `game:offlineList` IPC to show a fallback game list when the server is unreachable at startup (#383) |
| `~/.emusync/offline_plays.json` | Append-only log of offline plays (`slug`, `started_at`, `ended_at`, save mtime/hash) for save-conflict resolution (#5) |
| `~/.emusync/ps2_serials.json` | `{slug: serial}` map for PS2 games, learned by `emusync run` from PCSX2's `playtime.dat` at session exit; joined with the live `playtime.dat` by `files:get-ps2-last-played` so the GUI shows per-game last-played despite the shared card (#301) |
| `~/.emusync/art/<consoleKey>/<slug>/<type>.png` | Cached artwork, one file per SteamGridDB asset type (`grid`/`wide_grid`/`hero`/`logo`/`icon`) so switching a console's type never deletes another's cache; downloaded by `art:get` (#304, #322, #324, #333) |
| `~/.emusync/save_conflicts.json` | Append-only log of auto-resolved save divergences (`slug`, `resolved_at`, `winner`, local/server hashes), written by `emusync run` on true divergence (#5) |

Config fields: `server_host`, `server_port`, `data_dir`, `device_id`, `device_name`, `is_server`, `server_pin` (optional — blank = open access), `recent_import_folders` (dict console key → recent folder paths), `watch_saves` (opt-in background save/state watcher, #242), `import_rom_source` (console key → `"local"`/`"network"`) and `import_local_folder` (console key → local-copy destination, both #255), `art_type_by_console` (console key → `"grid"`/`"wide_grid"`/`"hero"`/`"logo"`/`"icon"`, default `"grid"`, #324; `wide_grid` = SteamGridDB's 460x215 landscape "header capsule", #333).

---

## Server process lifecycle

- **Initialization (zero-config, #268):** `emusync server start` on a fresh device (`is_server=false`) auto-initializes with preset defaults, no interactive prompt. `_auto_initialize_server` sets `is_server=true` and persists; port stays the default (8765), PIN stays blank. The PIN is changed afterwards via the GUI (`server:change-pin`) or by editing `server_pin` in the TOML. The GUI's auto-start path sees the flag on the next launch.
- **Single Ctrl+C shutdown (#268):** `uvicorn.run(..., timeout_graceful_shutdown=3)` — one Ctrl+C exits cleanly. Without it uvicorn waits indefinitely on the long-lived `/events/stream` SSE connections, forcing a second Ctrl+C. After the 3s timeout uvicorn force-cancels those tasks (the SSE generator handles `CancelledError`), then `finally` runs normal teardown.
- **Duplicate-launch detection:** checks `.server_pid` and whether the process exists; if running, exits gracefully with the PID and port. Stale PID files are cleaned up automatically.
- **Start:** `startServerProcess()` spawns Python with `PYTHONUNBUFFERED=1`, waits for the startup signal in stdout, returns `{ ok }`. Renderer health-polls to confirm readiness.
- **Stop:** GUI "Stop Server" or CLI `emusync server stop`. GUI: SIGKILL `serverProcess` + read `.server_pid` and SIGKILL that PID + `pkill -9 -f "emusync.py server start"`. CLI: checks `.server_pid`, kills it, echoes "server not running" if inactive. Both clean up the PID file; GUI resets `serverStartedByApp`.
- **Restart:** `emusync server restart` — stops then starts, for applying config changes.
- **App close:** `window-all-closed` only kills the server if the GUI spawned it (`serverStartedByApp=true`, set only when `startServerProcess()` sees "Pairing token:" in stdout, not on duplicate-launch exit) — so a terminal-started server survives closing the GUI.
- **Auto-start:** `App.tsx` calls `server.start()` on init if `is_server=true`. If a server is already running externally, Python exits gracefully via duplicate-launch detection and the GUI doesn't manage its lifecycle.

---

## Server activity logging (terminal output)

The server prints real-time activity to stdout for operator visibility. **Every line is timestamped** with `[YYYY-MM-DD HH:MM:SS] `:

```
[2026-06-09 14:03:18] EmuSync server ready
[2026-06-09 14:03:18] EmuSync server running on :8765
[2026-06-09 14:03:21] new device paired called steamdeck at ip:192.168.1.42
[2026-06-09 14:05:02] steamdeck online
[2026-06-09 14:10:44] Pokemon Emerald is running on steamdeck
[2026-06-09 14:10:45] save pulled: Pokemon Emerald by steamdeck
[2026-06-09 14:55:12] save pushed: Pokemon Emerald from steamdeck
[2026-06-09 14:55:13] Pokemon Emerald stopped on steamdeck
[2026-06-09 15:01:00] steamdeck went offline
[2026-06-09 15:30:00] steamdeck unpaired
```

**Timestamping** — `cli/server.py`'s `_TimestampedStream` (a thin `sys.stdout` wrapper), installed via `_install_timestamped_stdout(log_path)` at the top of `_do_start_server`, prefixes every newly started line (thread-safe, `\r`-aware) so all current and future stdout lines — `click.echo`, `print`, `api._print_activity`, the transfer-daemon log — are timestamped uniformly without touching each call site. Does **not** wrap stderr (mDNS warnings) or uvicorn's own logs. Stamped chunks also mirror to `~/.emusync/server.log` via `_RotatingLogWriter` (size-capped, rotating, stdout-only — #268); the writer is closed in `finally`.

**Full set of server stdout lines:**

| Line | Where | When |
|------|-------|------|
| `EmuSync server ready` / `EmuSync server running on :<port>` | `cli/server.py` | startup (`main.ts` matches `EmuSync server ready` via `.includes()` — keep that substring intact) |
| `EmuSync server is already running …`, `Server (PID …) stopped.`, `server not running`, init/clear-devices messages | `cli/server.py` | lifecycle commands |
| `new device paired called <name> at ip:<ip>` | `api._auth()` | first INSERT for a device (`ensure_device` returns `is_new=True`) |
| `<name> online` | `api._auth()` | a known device requests while not in `_online_devices` |
| `<name> went offline` | `_monitor_presence()` daemon thread | device idle > 5 min (checked every 30s) |
| `<name> unpaired` | `DELETE /devices/{id}` | device removed (printed before deletion) |
| `<game> is running on <device>` | `POST /games/{slug}/lock` | lock acquired |
| `<game> stopped on <device>` | `DELETE /games/{slug}/lock` | lock released |
| `save pushed: <game> from <device>` / `save pulled: <game> by <device>` | `POST`/`GET /games/{slug}/save` | save sync (pull only logs on a real hit, not a 204) |
| `state pushed: <game> from <device>` / `state pulled: <game> by <device>` | `POST`/`GET /games/{slug}/state` | state sync (pull only logs on a real hit) |
| `ROM pushed: <game> from <device> → <target> (queued)` | `POST /games/{slug}/rom-transfer` | ROM staged for delivery |
| `ROM pulled: <game> by <device>` | `GET /rom-transfers/{id}/file` | target device downloads the staged ROM |

`api._print_activity(msg)` is the single sink for API-side lines — one atomic `sys.stdout.write` so concurrent worker threads can't interleave. `_game_label(slug)`/`_device_label(device_id)` resolve human-readable names (device names from the `_device_names` cache `_auth` populates, falling back to a `list_devices` scan, then the raw id).

**Thread safety:** `_online_devices`/`_device_names` are protected by `_presence_lock` (`_auth` may run on concurrent worker threads). `_TimestampedStream` has its own lock so writes from those threads stay line-atomic.

---

## Authentication (PIN-only model)

- **Server PIN:** `server_pin` config field. All clients send `Authorization: Bearer {PIN}`.
- **Device registration:** devices auto-register on first authenticated request via `X-Device-ID`/`X-Device-Name` headers. No explicit pair/token step.
- **Blank PIN:** empty `server_pin` allows any request (open access — trusted LANs).
- **Changing the PIN:** `server:change-pin` saves the new PIN and restarts the server; existing device records persist, they just need the new PIN to reconnect.
- **Client connection:** on first launch the user enters host/port/PIN; renderer calls `configure(host, port, pin)` and `configureDevice(deviceId, deviceName)` (or these auto-load from config). All API calls include PIN + device headers.

---

## Testing

```bash
make test                          # run all tests
.venv/bin/python -m pytest tests/test_integration.py::test_name -v  # single test
```

Integration tests use a real SQLite DB (no mocks), spinning up the full store and API via `httpx.AsyncClient` + `ASGITransport`. Set `EMUSYNC_CONFIG_DIR` to isolate config between test runs.

**Do not mock the database.** Past incident: mock/prod divergence masked a broken migration.

### Claude agents — testing requirements

**Before marking any task complete, run `make test` and confirm it passes.**

Write tests when:
- You added a new API route (relevant `server/api/` router) → integration test for the happy path + main error case (404/403/409/etc.)
- You added a new `Store` method (relevant `server/store/` mixin) → test via `Store(tmpdir)` or through the API
- You added a CLI subcommand (`cli/` package) → note it in the PR; tests optional but preferred for logic-heavy commands
- You fixed a bug → add a regression test that would have caught it

**How to write a test** — follow the pattern in `tests/test_integration.py`:

```python
MASTER_PIN = "test-master-pin"
AUTH = {
    "Authorization": f"Bearer {MASTER_PIN}",
    "X-Device-ID": "device-abc",
    "X-Device-Name": "test-pc",
}

@pytest.mark.asyncio
async def test_your_scenario(client):          # client fixture = fresh DB + app
    r = await client.post("/your-route", json={...}, headers=AUTH)
    assert r.status_code == 200
```

Multi-device tests / custom PINs:

```python
def _device_auth(device_id: str, device_name: str, pin: str) -> dict:
    return {
        "Authorization": f"Bearer {pin}",
        "X-Device-ID": device_id,
        "X-Device-Name": device_name,
    }

# Device 1 and 2 both connect with same PIN
auth1 = _device_auth("d1", "PC", MASTER_PIN)
auth2 = _device_auth("d2", "Steam Deck", MASTER_PIN)
```

Blank-PIN (open access) or direct store access:

```python
with tempfile.TemporaryDirectory() as tmpdir:
    store = Store(tmpdir)
    api_module.init(store, "")   # blank PIN = open access
    async with AsyncClient(transport=ASGITransport(app=api_module.app), base_url="http://test") as c:
        ...
```

**Never use mocks.** Real SQLite only.

---

## Release process

```bash
make release VERSION=v1.2.3
```

1. Creates a git tag locally
2. Pushes the tag to origin
3. GitHub Actions (`release.yml`) triggers: runs tests, builds a Linux AppImage on `ubuntu-latest`, builds a Windows NSIS installer on `windows-latest`, publishes a GitHub Release with both artifacts

Artifact naming: `EmuSync-{version}-linux-x86_64.AppImage`, `EmuSync-{version}-windows-x64-setup.exe`.

To re-cut a failed release: delete the tag remotely and locally, fix the issue, re-tag.

---

## Execution approval policy

Applies to every Claude agent and skill working in this repo (`/issue`, `/plan`, `/implement`, and any added later):

- Read-only commands (curl GET, `gh issue/pr list|view`, `git status|log|branch|fetch|diff`, `make test`, lint/build checks) always run automatically — never pause to ask first.
- GitHub issue creation, PR creation, and git commits/pushes are pre-approved — create/commit/push/open-PR without asking "should I proceed?".
- Only pause for the user's explicit go-ahead when a step would directly modify something on the machine *outside* this repo (e.g. deleting unrelated files, changing system config, killing unrelated processes). Editing tracked files, opening a PR, or filing an issue does not require a pause.
- Clarifying questions about ambiguous requirements are not permission requests — always fine to ask those.

---

## Development workflow — before touching code

**Applies to both human developers and Claude Code agents. Claude: do not start writing or editing code until these steps are complete.**

Automated path: the `/issue`, `/plan`, and `/implement` skills (`.claude/skills/`) run Steps 1–4 below end to end — `/issue` finds-or-files the issue and cuts the branch, `/plan` reads it and drafts an implementation plan, `/implement` executes the plan and opens the PR. The manual steps below are the reference for what those skills automate, and the fallback for ad-hoc work outside that pipeline.

### Step 1 — find or create an issue

```bash
curl -s "https://api.github.com/repos/alekoHalkias/Emusync/issues?state=open&per_page=50"
```

Read the list. If an existing issue covers the work, use it; if not, create one before proceeding — it's the paper trail for why a change was made.

**Claude agents:** if given a task without an issue mentioned, check the list yourself. If none matches, create one directly using the method below and note the issue number — see Execution approval policy above, issue creation needs no confirmation pause.

#### How Claude agents create issues

Check for tools in this order:

```bash
# 1. Preferred — gh CLI (handles auth transparently)
which gh && gh issue create --repo alekoHalkias/Emusync --title "..." --body "..."

# 2. Fallback — curl with GITHUB_TOKEN env var
curl -s -X POST https://api.github.com/repos/alekoHalkias/Emusync/issues \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d '{"title":"...","body":"..."}'
```

If neither works (no `gh`, no `GITHUB_TOKEN`), tell the user:
> "I need GitHub access to create the issue. Run `gh auth login` or set `GITHUB_TOKEN=<your PAT>` in your shell, then ask again."

To set up `gh` on this machine (WSL2/Linux):
```bash
curl -sL https://github.com/cli/cli/releases/download/v2.71.0/gh_2.71.0_linux_amd64.tar.gz \
  | tar xz -C /tmp && mkdir -p ~/.local/bin && mv /tmp/gh_2.71.0_linux_amd64/bin/gh ~/.local/bin/gh
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.bashrc to persist
gh auth login
```

**Always prefix gh commands with `export PATH="$HOME/.local/bin:$PATH"` in this project** until it's on the system PATH.

### Step 2 — check for conflicting branches

```bash
git fetch --prune && git branch -r
```

Look for any `feature/*` or `copilot/*` branch likely to touch the same files. If one exists, stop and flag it before writing any code — two branches editing `api.py` or `server/store/` simultaneously produces a painful merge.

### Step 3 — create a linked branch

Name the branch after the issue: `feature/<issue-number>-short-description`

```bash
git checkout main && git pull && git checkout -b feature/10-event-log
```

**Claude agents:** skip this if already on a correctly-named branch. If on `main` or an unlinked branch, create the right one before making any edits.

### Step 4 — reference the issue in the PR

Use `Closes #N` in the PR body so GitHub auto-closes the issue on merge.

---

**Stop and warn the user if:**
- Another open branch is already modifying the same key files
- An open issue is assigned to someone else or has recent activity suggesting active work
- The current branch name has no issue number and `--no-verify` would be needed to commit

---

## Active branches / conventions

- `main` — stable, release-ready
- Feature branches cut from `main`, merged via PR — named `feature/<issue-number>-description`
- The branch `feature/server-control-panel` contains the server modal UI and PIN system (merged into main)
- No `--no-verify` or `--amend` on published commits

---

## State File Syncing

In addition to save files (SRAM), EmuSync syncs **save states** (snapshots). RetroArch stores these in `states/<CoreName>/game.state` parallel to `saves/<CoreName>/game.sav`. State syncing mirrors save syncing at every layer:

- **DB schema**: `states` table; `state_path` column on `game_devices` via migration
- **API**: `/games/{slug}/state` routes (GET/POST) and `/games/{slug}/state/meta`
- **CLI (`emusync run`)**: pulls state before launch, pushes after exit (opt-in if `state_path` configured); auto-detects the real save/state extension and updates config if needed
- **Electron**: detects `savestate_directory` from `retroarch.cfg`, scans for `.state`/`.state.auto` per ROM
- **GUI**: wizard shows `✓ State found`/`⊕ State will be created` badges; never pre-creates files, only tracks paths

State sync is **opt-in** — an empty `state_path` is skipped silently. The scan handler checks both the per-core subfolder and the root `states/` dir for backwards compatibility.

**Auto-detection of the real save/state path (extension *and* folder)** — Import registers a default path derived from the ROM filename (e.g. `saves/SNES/game.sav`), but RetroArch names files after the **content name**, which differs by launch method: the ROM filename when loaded by path, or the **database/playlist label** when loaded from a playlist (e.g. `states/Pokémon Pinball_ Ruby & Sapphire [2003]/` — `:`→`_`, `[year]` appended). So the real save/state can sit under a different extension and/or folder. After exit, `emusync run` records a pre-launch timestamp and detects what was actually written **this session** (`_resolve_written_save`/`_resolve_written_state` in `cli/run.py`): if the configured location was written, it's kept; otherwise the wrapper adopts the newest save file/state folder written under the saves/states root (`.bak` excluded) and updates the `game_device` config (preserving `rom_folder_path`). Conservative policy — a working config is never switched away from. **Limitation:** EmuSync only sees what RetroArch wrote during a wrapped launch; a save from a pure RetroArch-direct session is only picked up once a wrapped launch writes to the same folder (#210).

---

## ROM Folder Tracking

During import, `rom_folder_path` is extracted from each ROM's full path and saved with the game config — enabling future re-scans of specific folders, tracking which folder held each game's ROM, and managing multiple games from one directory. Returned by `GET /games/{slug}/device` alongside `rom_path`/`save_path`/`state_path`/`launch_command`.

---

## ROM Transfer (`emusync push` / `emusync pull`)

### `emusync push` — send a ROM to another device

Interactive wizard transferring ROM files to another device via the central server:

1. Lists this device's games that have a `rom_path`
2. User multi-selects games (`1`, `1,3`, `1-4`)
3. Lists paired devices with online/offline status
4. User selects target device
5. Per game: checks if the target has the console configured (via `consoles`/`game_devices`); proposes the known ROM folder or asks for a custom path
6. Streams each ROM to server staging via `POST /games/{slug}/rom-transfer`
7. Server creates a `rom_transfers` record (status=pending), responds with `target_online`
8. CLI shows "queued — device is online" or "⚠ offline — will be delivered when it comes online"

### `emusync pull` — request a ROM from another device

The reverse: this device requests a ROM from a source device, fulfilled by the source's sync-daemon.

1. Lists paired devices with online/offline status
2. User selects the source device
3. Lists the source's games with a `rom_path` (via `GET /devices/{id}/game-devices`)
4. User multi-selects games to pull
5. Per game: checks if this device has the console configured locally; proposes the local ROM folder or asks for a custom path
6. Sends `POST /games/{slug}/rom-pull-request` with `from_device_id` and `destination_path`
7. Server creates a `rom_pull_requests` record, SSE-notifies the source
8. CLI shows "request sent — source is online" or "⚠ offline — ROM will be sent when it comes online"
9. Source's sync-daemon handles `rom_pull_requested`: looks up the local ROM, calls `create_rom_transfer`, marks the request fulfilled
10. Requester's sync-daemon receives `rom_transfer_queued` and downloads normally

**API surface:**
- `POST /games/{slug}/rom-transfer` — streams ROM bytes with `X-To-Device-ID`, `X-Destination-Path`, `X-Filename` headers; stages to `~/.emusync/rom_staging/{transfer_id}/{filename}`, hashing the stream (SHA256) into `rom_transfers.sha256`; returns `{transfer_id, status, target_online}`. The hash surfaces in the pending-transfer list, the `rom_transfer_queued` SSE event, and the `X-Rom-Hash` download header, so `download_transfer` can verify integrity and reject a corrupt transfer (#214)
- `GET /game-devices` — all games configured for the calling device
- `GET /devices/{id}/game-devices` — all games configured for any device
- `GET /devices/{id}/consoles` — console configs (name, ROM folder, save folder, emulator) for any device
- `POST /games/{slug}/rom-pull-request` — creates a pull request (`{from_device_id, destination_path}`), SSE-notifies the source, returns `{pull_request_id, status, source_online}`
- `GET /rom-pull-requests/pending` — pending requests where the calling device is the source
- `PUT /rom-pull-requests/{id}` — mark a pull request `fulfilled`/`failed` (source device only)

**Staging dir:** `~/.emusync/rom_staging/{transfer_id}/{original_filename}` — one subdirectory per transfer, original filename preserved. Deleted once the receiver marks the transfer `completed`/`failed` (`_remove_staging_dir` in `server/api/_core.py`); `api.init()` runs `_sweep_stale_staging()` on startup to drop any subdir whose transfer is gone or no longer pending (#202).

**Auto-delivery via `emusync sync-daemon`**: run on any device to handle both sides automatically. On startup drains pending transfers and pull requests, then holds an SSE connection open, handling `rom_transfer_queued` (download + register) and `rom_pull_requested` (look up local ROM, upload via `create_rom_transfer`). Reconnects on connection loss. Built into `emusync server start` as a background thread on server devices.

**`sync_client.py` delivery methods**: `list_pending_transfers()`, `download_transfer(id, dest)`, `complete_transfer(id)`, `list_pending_pull_requests()`, `complete_pull_request(id)`, `list_device_games(device_id)`, `create_pull_request(slug, from_device_id, destination_path)`, `stream_events()` (SSE generator).

---

## Debug tools

```bash
# Scan a folder for ROMs from the CLI (no Electron needed)
node scripts/scan-roms.mjs <folder> [--ext gba,sfc] [--depth 3] [--verbose]

# Example: find all GBA ROMs up to 3 dirs deep
node scripts/scan-roms.mjs ~/Games/GBA --ext gba --verbose
```

The `emulator:scan` IPC handler emits `[scan]` lines to stderr in dev mode — visible in the `make dev-gui` terminal.

---

## Common gotchas

**Shared-save-layout consoles (PS2) — never treat the save/state as per-game** — For consoles where the save (and states) live in ONE shared location across every game (PS2's `memcards/Mcd001.ps2` + `sstates/`, #294/#295), the per-game save/state must not be renamed, moved, or pushed per-game. The renderer gates this via `usesSharedSaveLayout(consoleKeyOrAbbr)` in `console-import/helpers.ts` (currently `{ps2}`): import (`useConsoleImport`) passes empty save/state to `renameGameFiles` and skips per-game `autoPush`; `GameConfig` skips the save/state rename on a name-change and hides the manual **per-game** sync panel (a per-game state pull there would `.bak` every game's slots) but shows a console-scoped memcard push/pull `SyncLine` instead (#319), since pushing/pulling the whole card on demand is safe (e.g. a card edited outside EmuSync). CLI mirror: `run.py`'s `_SHARED_MEMCARD_CONSOLES`/`_SHARED_STATE_CONSOLES` and `scan.ts`'s `SHARED_MEMCARD`. Keep all four in sync if adding a shared-layout console. **Import-time pull (#316):** `useConsoleImport`'s `pullFromServerIfNewer` pulls the console-scoped card via `window.emusync.memcard.pull` right after import if the server's copy is newer (or local has none) — the pull counterpart to `autoPush`, console-keyed. Shared save *states* are deliberately NOT pulled at import time — keyed by game serial with no console-scoped endpoint, so only `emusync run`'s per-launch serial-filtered sync touches them.

**Orphaned server processes** — If Electron exits abnormally, uvicorn can keep running. The stop handler uses three kill strategies (see Server process lifecycle). "Port already in use": run `pkill -9 -f "emusync.py server start"`. `emusync server start` now detects a running server and exits gracefully instead of duplicating it.

**SIGKILL skips Python finally blocks** — `.server_pid`/`.server_token` may survive a hard kill; the stop handler manually deletes them.

**WSL2 + Electron** — requires `--no-sandbox` (baked into `npm run dev`) and `DISPLAY=:0`. dbus errors in the output are harmless.

**Stale DB schema** — `sqlite3.OperationalError: no such column` → delete `~/.emusync/emusync.db` and restart the server.

**TypeScript on `window.emusync`** — globally typed via `EmusyncBridge` in `gui/renderer/src/emusync.d.ts` (#228), the source of truth mirroring `preload.ts`. New IPC channel → add its signature there too, or renderer call sites won't be type-checked. `config.load`/`save` and `emulator.detect`/`scan` returns are intentionally loose (`Record<string, any>`/`any[]`) — config is an open TOML dict, emulator result types live in the electron package.

**RetroArch config paths use `~`, which Node.js doesn't expand** — `retroarch.cfg` often stores `savefile_directory = "~/.config/retroarch/saves"`. `parseRetroArchCfg` in `main.ts` expands leading `~/` to the real home dir so `existsSync`/`mkdirSync`/`join` work. Always pass `home`; never use a raw config value as a filesystem path without checking for tilde. `rgui_browser_directory = "default"` is RetroArch's "not configured" placeholder — filtered out, never passed as a ROM directory.

**RetroArch per-core save directory is always `saves/<CoreName>/`** — `detectEmulatorsForConsole` uses `join(ra.saveDir, core.folderName)` unconditionally. The old fallback to the root saves dir (when the subfolder didn't exist yet) caused saves to land in the wrong place on fresh installs. The scan handler still checks the root dir as a fallback when looking for *existing* saves written before per-core organisation.

**RetroArch "Sort saves/states by content directory"** — canonical model: saves at `savesRoot/GameName/GameName.srm`, states as a FOLDER at `statesRoot/GameName/` (all slots live there). `state_path` in `game_devices` stores the FOLDER, not a file. Both the GUI IPC (`state:push`/`state:pull`) and `sync_client.py` (`push_state`/`pull_state`) detect a directory `state_path` and pack/extract all files as a **tar.gz** so every slot (`.state`, `.state1`, `.state.auto`, …) syncs. `emusync run` always pushes the whole folder after exit (no hash comparison for folders). **State pulls are non-destructive:** the folder extractor backs up every overwritten file to `.bak` and *retains* it (one generation, `os.replace`/unlink-then-rename, Windows-safe) — the old code deleted backups on success, losing the overwritten state (#204). `push_state`/`state:push` **exclude `.bak` files** so backups never propagate. `pull_state` falls back to writing raw bytes as `GameName.state` if the server blob isn't a valid tar (legacy compat). `emulator:scan` computes target paths using the content-dir pattern, checking legacy core-subfolder/flat-root paths only as fallbacks for detecting existing files; the default registered path always uses the content-dir pattern even before the file/folder exists.

**`store.add_game` is INSERT OR IGNORE, not INSERT OR REPLACE** — only inserts new rows, never overwrites. Use `update_game_name(slug, name)` to rename. The original `INSERT OR REPLACE` bug cascade-deleted `game_devices`/`saves`/`locks` on every rename, emptying the game list after a config save.

**Duplicate-launch guard in `emusync run`** — before acquiring the lock, if it's already held (by this or another device), `_show_game_running_popup` shows "\<game\> is already running. Please close it on \<device\>." and exits. Fallback chain — `notify-send` → `zenity` → `kdialog` → `xmessage` → tkinter — works across Wayland, X11, Steam Deck Gaming Mode (gamescope), and environments missing `libtk`. `notify-send` fires first (non-blocking, auto-dismisses), then the chain continues to the first available blocking dialog. The race-condition path (409 from `acquire_lock`) follows the same flow.

**DB thread safety — one connection per thread, not shared** — `server/store/connection.py`'s `_ThreadLocalConnection` lazily creates one `sqlite3.Connection` per thread (cached in `threading.local`). The store is hit from uvicorn's worker-thread pool *and* the `_monitor_presence` daemon thread; a shared connection can't handle concurrent cursor access safely — one thread's `execute`/`commit` landing between another's `execute()` and `fetchone()`/`fetchall()` corrupts the in-flight statement and raises `sqlite3.InterfaceError`, wedging the connection (#200). With WAL (per-connection) this gives concurrent readers + a single writer; the 30s busy timeout handles writer contention. **`PRAGMA foreign_keys` is per-connection** — set on every connection in the factory, don't assume it's on otherwise. Each connection uses `check_same_thread=False`. Schema init (`server/store/_base.py`) runs on fresh DBs only, each statement executed individually (`executescript()` is deprecated and WAL-incompatible). Don't reintroduce a shared connection guarded by a lock that releases before fetch — that's the exact bug that was removed.

**DB schema versioning — use `PRAGMA user_version`, not try/except** — `server/store/schema.py` tracks the version in `PRAGMA user_version` (currently `_SCHEMA_VERSION = 15`). A migration moving data onto disk (e.g. v8) takes the blob dir via `_migrate(conn, from_version, blob_dir)`, passed by `_base.py`. Adding a migration: (1) add an `if from_version < N:` block in `_migrate()`, (2) bump `_SCHEMA_VERSION`, (3) add the new table/column to `_SCHEMA` so fresh DBs get it without migrating. Don't add bare `try/except ALTER TABLE` outside `_migrate()` — warm-start DBs skip `_migrate()` entirely via the version check. **Fresh DBs are stamped with `PRAGMA user_version = _SCHEMA_VERSION`** right after `_SCHEMA` is applied (`_base.py`) — don't remove that stamp, or every new install re-runs the whole migration chain against the schema it just created (#202).

**`config:load` returns `null` when config is absent** — `main.ts`'s `config:load` returns `null` both when the TOML file is missing and when it fails to parse. Check for `null` rather than calling the separate `config:exists` first (kept only for backwards compatibility, now redundant).

**mDNS runs in a background thread** — in `emusync.py server start`, mDNS advertisement runs `daemon=True` so the pairing token prints (and Electron can resolve) without waiting on socket/network probing. The `finally` block joins the thread (2s timeout) before unregistering the service.

**Token is printed before uvicorn binds** — `emusync.py server start` prints `Pairing token:` before `uvicorn.run()`. Code calling `server.start()` and immediately hitting the API will get connection refused — always poll `/health` first (both `App.tsx` and `Setup.tsx` do this, including before `/pair`).

**Blank PIN servers must match in the token regex** — `startServerProcess` in `main.ts` looks for `Pairing token: (\S*)` (zero-or-more). `server_pin` defaults to `""`, so the printed line is `"Pairing token: "` with no value; `\S+` would never match and fall through to the 5s timeout.

**Electron main process must use `fetch`, not `http.get`** — `sync.ts`/`steamgriddb.ts` establish `fetch()` as the main-process pattern (a prior "use http.get" rule here is stale). The renderer process also uses normal `fetch()`.

**`server_host` is empty string on server devices** — they store `server_host = ""` since they connect to themselves. Any `main.ts` code reading `cfg.server_host` must fall back to `"localhost"` when empty: `const host = (cfg.server_host as string) || "localhost"`. Never use `!cfg.server_host` as a "not configured" guard — check `!cfg.server_port` instead.

---

## Keeping this file updated

Update this file when:
- CLI subcommands are added/removed (`cli/` package)
- IPC channels are added/removed (`main.ts`/`preload.ts`)
- New React components land in `gui/renderer/src/components/`
- Config fields are added/removed (`server/config.py`)
- New data files are written to `~/.emusync/`
- Python or Node dependencies change (`requirements.txt`, `package.json`)
- Release or CI/CD process changes
- `install.sh`, `Makefile`, or `emusync-server.service` change

A pre-commit hook (`.git/hooks/pre-commit`) warns when architecture files change without this file being updated. Run `bash install.sh` to install it.
