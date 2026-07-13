# EmuSync — Architecture Reference

Detailed module-by-module reference, split out of CLAUDE.md so it's read on demand rather than loaded on every turn. CLAUDE.md has the short index and the standing rules (workflow, gotchas, testing); this file has the exhaustive "what does X own and how does it work" detail. Read the relevant section when you're about to touch that area — don't load the whole file speculatively.

For *why* something is the way it is, `git log`/`git blame` on the file in question is the source of truth, not this doc.

---

## Key files (full detail)

| File | Owns |
|------|------|
| `emusync.py` | Thin entry-point shim: bootstraps `sys.path`, calls `cli()` from `cli/`. Must stay at this path — `install.sh`, `Makefile`, Electron's `spawn` in `main.ts`, and `pkill -f "emusync.py server start"` invoke it by path. No command logic here |
| `cli/` | Click CLI, one module per command group. `root.py` = root `cli` group; `__init__.py` imports every command module and re-exports `cli`. `common.py` = shared helpers (`_client`, `_print_table`, `_get_device_name`, `_show_game_running_popup`, `_fmt_time`/`_relative`/`_parse_iso_utc`); `consoles_data.py` = hardcoded `_IMPORT_CONSOLES`/`_IMPORT_SYSTEMS`/extension sets + `_prepare_console_seed_data` (seeds the server's global console defs; each console declares `databases`, its libretro database names, for core matching); `detect.py` = RetroArch/core/ROM detection + scan helpers (mirrors `detect.ts`) — returns every installed core (not just first-match) and discovers unlisted cores from RetroArch's own `.info` metadata (`_discover_cores_by_info`: a core's `database` field matched against the console def's `databases`, save folder from `corename`; the hardcoded `_IMPORT_SYSTEMS` core lists remain as preferred ordering + fallback for installs without info files); standalone emulator detection reads `save_dir`/`state_dir` from a standalone def's `dirs.native`/`dirs.flatpak` (expanded via `_expand_home`, mirroring `detect.ts`'s `expand()`); `server.py` = `server` group (start/stop/restart/clear-devices/discover-json) + lifecycle helpers + embedded transfer daemon; `device.py` = `device` group (`connect`/`list`/`compare`); `game.py` = `game` group (`add`/`list`/`edit`/`remove` — `remove` defaults to unlinking this device only via `client.remove_game_device`; `--everywhere` opts into full-purge via `client.remove_game`); `console.py` = `console` group (`list` + `import`, the wizard mirroring the GUI Add Console flow: detect RetroArch/cores/standalones → scan ROM folder → bulk import; ROM extension matching falls back to `rom_extensions` when `system_keys` is empty, and a shared-save console's save resolves to its per-console card path via `cli.detect._resolve_shared_memcard_save_state` rather than a per-game filename match — states stay per-game except PS2's shared sstates); `sync.py` = `sync status` + `sync history <slug>` / `sync restore <slug> <version-id>` (save/state rollback — `--state` targets states); `transfer.py` = top-level `push`/`pull`/`sync-daemon` + the transfer daemon loop; `watch.py` = opt-in background save/state watcher: `run_save_watcher`/`SaveWatcher` poll each local game's `save_path`/`state_path` and push on change (so saves from a non-EmuSync-wrapped session still sync); dependency-free polling, a file must be *settled* before pushing, reuses `_save_is_safe_to_push`, skips a game locked by another device; `run.py` = the `run` command + the SIGTERM handler that kills the emulator child + `_resolve_launch_command` + `_start_lock_heartbeat`; split into sibling modules re-exported from `run.py`: `run_reconcile.py` (`_reconcile_save`/`_decide_save_action` — newest-wins: push if local mtime > server `pushed_at`, else pull, loser kept as `.bak`; post-launch written-path detection via `_resolve_written_save`/`_resolve_written_state`); `run_ps2.py` (shared-save-layout adapter for `_SHARED_MEMCARD_CONSOLES` — `_reconcile_save` runs against the console card via the `_MemcardClient` adapter, mapping the per-game save API onto `/consoles/{key}/memcard`; PCSX2 save states live in one SHARED folder named per game serial, so for `_SHARED_STATE_CONSOLES` states sync filtered by serial via `_ps2_state_serial_prefix`; also `_learn_ps2_serial`/`_read_pcsx2_playtime`); `run_conflicts.py` (save-safety + conflict surfacing — a true divergence surfaces via `_warn_save_conflict`: stderr + `_notify` + `_log_save_conflict` → `save_conflicts.json` + `_report_conflict_to_server`; the post-game save push is gated by `_save_is_safe_to_push` — a 0-byte save, or one that shrank below 50% of the server's previous copy, is **not** pushed); `run_offline.py` (`_launch_and_wait` + offline fallback — if `client.health()` fails, launches anyway and logs the play to `offline_plays.json`; `_cache_game_device`/`_load_cached_game_device` persist each game's paths under `game_cache/`; `_cache_game_device` also upserts a sibling `game_cache/_offline_index.json` for the GUI's offline game list). `_child_proc` lives in `run_offline.py`; `run.py`'s SIGTERM handler reads it via the module, not a re-exported name, since a plain import wouldn't see later reassignment; `netrom.py` = network-ROM helpers: `path_is_reachable` (bounded mount-liveness probe), rel-path `normalize`/`sanitize`/`compute_rel_path`/`join_network`, `localize_rom`/`delocalize_rom` (free-space-checked, atomic, master-guarded copy), `upload_to_master`; `rom.py` = `rom` group (`list`/`localize`/`delocalize`) |
| `server/api/` | FastAPI app, split into per-domain `APIRouter` modules: `_core.py` owns the `app`, shared mutable state, `init()`, `_auth`, activity-log helpers, ROM-staging helpers, `/health`; `devices.py`/`games.py`/`transfers.py`/`blobs.py`/`locks.py`/`defs.py`/`conflicts.py` are the routers; `__init__.py` re-exports `app`+`init` and `include_router`s them. Routers reach reassigned globals via accessors (`_get_store()`, `get_data_dir()`), never by re-importing rebindable names. Auth via `Authorization: Bearer {PIN}` + `X-Device-ID`/`X-Device-Name`; routes: `/health`, `/games`, `/games/overview` (per-device batch: lock + last save + config for every game in one call), `/devices`, `/whoami`, `/saves`, `/states`, `/locks`, `/events`, `/events/stream` (SSE), `/games/{slug}/devices`, `/games/{slug}/network-source`, `/game-devices`, `/devices/{id}/consoles`, `/devices/{id}/game-devices`, `/games/{slug}/rom-transfer`, `/rom-transfers/pending`, `/rom-transfers/{id}/file`, `/rom-transfers/{id}`, `/games/{slug}/rom-pull-request`, `/rom-pull-requests/pending`, `/rom-pull-requests/{id}`, `/console-defs`, `/system-defs`, `/console-folder-names`, `/standalones/{console_key}`; save/state history + rollback: `GET /games/{slug}/save/history` + `POST /games/{slug}/save/restore` (+ `/state/` equivalents); in `blobs.py` save/state routes are thin wrappers over shared `_BlobKind`-parametrised handlers dispatching to uniform store methods; save/state integrity: `GET /games/{slug}/integrity`, `GET /integrity` (library-wide summary from the at-rest snapshot) + `POST /integrity/rescan` — the snapshot builds in `_core._run_integrity_sweep()` on startup, no schema column, computed from row metadata + on-disk bytes; console-scoped shared memory card (`blobs.py`): `GET/POST /consoles/{console_key}/memcard` + `GET /consoles/{console_key}/memcard/meta` — one card per console keyed by abbr, shared across the console's games; `_auth` auto-registers devices on first request; `GET /devices` includes `is_online`; `settings.py` = shared SteamGridDB API key (`GET`/`PUT /settings/steamgriddb-key`), a generic `server_settings` key-value store entered from any device and fetched by every connected device's Electron process; `games.py`'s `GameRequest`/`PUT /games/{slug}` also accepts optional `sgdb_game_id`; `DELETE /games/{slug}/device` unlinks the game from the calling device only (idempotent) vs. `DELETE /games/{slug}` which fully purges the game everywhere |
| `server/store/` | SQLite via stdlib `sqlite3`, split into a package: `__init__.py` composes `Store` from one mixin per table-group; `connection.py` = `_ThreadLocalConnection` (one SQLite connection per thread); `schema.py` = `_SCHEMA`/`_SCHEMA_VERSION`/`_migrate`; `models.py` = row dataclasses; `_base.py` = `StoreBase`; `devices.py`/`games.py`/`blobs.py`/`locks.py`/`events.py`/`transfers.py`/`consoles.py`/`console_defs.py` = per-domain CRUD mixins. Tables: `devices`, `consoles`, `games`, `game_devices`, `saves`, `states`, `locks`, `events`, `rom_transfers`, `rom_pull_requests`, `console_defs`, `system_defs`, `core_defs`, `console_folder_names`, `standalone_emulators`, `save_conflicts`, `console_saves`, `server_settings`. Current schema highlights: `console_defs.databases` (';'-joined libretro database names matched against installed cores' `.info` files — server-owned seed data, `seed_console_defs` overwrites it on every startup so mapping fixes reach existing DBs); `games.sgdb_game_id` (a manually-picked SteamGridDB match shared across devices, untouched by a plain rename); `server_settings` generic key-value table; `console_saves` (one memory card per `console_key` shared across a console's games, single generation, bytes under `blobs/console_saves/<key>`); `console_defs.rom_extensions` decoupling scannable extensions from core-derived `systemKeys`; `standalone_emulators.dirs_json`, an extensible `~`-templated per-emulator dir-path blob keyed native/flatpak → save/state/memcard; network-ROM source columns on `consoles`/`game_devices`; `save_conflicts` table. `blobs.py` (`SaveStateMixin`) stores blob **bytes on disk** under `<data_dir>/blobs/<saves|states>/<row id>` — only metadata lives in the row, keeping the DB small. **Keeps history**: `_push_blob`/`_push_blob_file` append a new generation (deduping identical consecutive content), `_prune_history` prunes to the newest `HISTORY_LIMIT` (20) per game; the *current* blob is the most recent row. `push_save_file`/`pull_save_path` (+ state) stream uploads to a staged temp file and serve pulls via `FileResponse` with no in-memory buffering; `remove_game` calls `delete_blobs_for_game` before the FK cascade; `remove_game_device(slug, device_id)` deletes just one `game_devices` row. `list_save_history`/`restore_save` (+ state) back rollback — `restore` re-inserts a past version as a new generation so history only grows forward; `integrity_for_game(slug)`/`sweep_integrity()` + private `_classify_blob`/`_last_good_version` classify a game's current blob ok/damaged/missing (0-byte, shrank below `_SHRINK_FLOOR`=0.5, hash mismatch, or file gone); `ensure_device()` returns `(device, is_new)`; `upsert_console_for_game(store, device_id, console_name, rom_path, save_path, rom_folder_path)` infers emulator/folder paths and creates-or-updates the `Console` row |
| `server/config.py` | TOML config dataclass; load/save `~/.emusync/emusync.toml` |
| `server/mdns.py` | mDNS advertise + LAN discovery via `zeroconf` |
| `server/sync_client.py` | HTTP client wrapping all server endpoints (used by `emusync run`, `push`, `pull`); persistent `httpx.Client`; sends PIN + device headers; `GameDeviceConfig` holds `rom_path`, `save_path`, `launch_command`, `state_path`, `rom_folder_path`, `rom_source`, `rom_rel_path`, `local_rom_path`, `rom_sha256`, `device_network_folder`, `device_local_folder`; `remove_game_device(slug)` unlinks the game from this device only vs. `remove_game(slug)`'s full purge; `list_my_game_devices()`, `list_device_games()`, `get_device_consoles()`, `create_rom_transfer()`, `create_pull_request()`, `list_pending_pull_requests()`, `complete_pull_request()` drive push/pull; `download_transfer()` verifies against `X-Rom-Hash`/recorded SHA256, deleting the partial file on mismatch; `list_save_history()`/`restore_save()` back history/rollback; `get_console_memcard_meta()`/`pull_console_memcard()`/`push_console_memcard()` are the console-scoped card methods the shared-save `_MemcardClient` drives — supports both file- and folder-based memcards. **PCSX2 nests each game's saves one level down** (e.g. `GAME1/GAME1`, `GAME1/icon.sys`) — `memcard_bytes(card_path)` walks the *whole tree* (`rglob`, not top-level `iterdir`) and serialises it as a deterministic plain tar (sorted, mtime=0, relative paths) for a stable SHA-256 — a top-level walk silently drops every game's data. `_write_memcard(card, data)` detects tar archives on pull, backs up the **entire memcard folder** as `<card>.bak` before extracting through `_safe_extract_tar` (the same path-traversal guard used for state archives); falls back to a raw-file write for a legacy file-based memcard. The `memcard:push`/`memcard:pull` IPCs mirror this: push packs with `tar -cf`, pull probes with `tar -tf`, backs up with `cp -r` to `<name>.bak`, extracts with `tar -xf` |
| `gui/electron/` (main process) | Split into per-domain modules — `main.ts` is just IPC registration + app lifecycle (calls each module's `register*Ipc()`). Shared mutable state lives on the single `rt` object in `runtime.ts` (ES modules only export read-only bindings, so cross-module reassignment needs an object). Modules: `runtime.ts` (constants + `rt`); `http.ts` (`httpGetJSON` — main process must use Node http, not `fetch`, for this one helper); `window.ts` (`createWindow`); `config-store.ts` (`config:*` IPC + `loadServerCfg`); `server.ts` (server + sync-daemon lifecycle, `server:*`/`daemon:*` IPC); `game.ts` (`game:*` IPC + `launcher:path`); `files.ts` (dialogs, `files:*`, `device:probe`, `findLatestFileInDir`); `sync.ts` (thin composer calling one `register*Ipc()` per domain) split into `sync/save.ts`, `sync/memcard.ts` (console-scoped shared memory card push/pull), `sync/state.ts` (save-state folder push/pull as tar.gz), `sync/rom.ts` (`rom:push`/`localize`/`delocalize`/`deleteFile`/`uploadMaster`/`setupNetworkPlay`), `sync/recovery.ts` (`recovery:listLocalBackups`/`restoreLocalBackup`); `emulator/{types,console-defs,detect,scan,ipc}.ts` (import-wizard subsystem — `emulator:consoles`/`detect`/`scan` lazily fetch console defs from the Python API); `steamgriddb.ts` (`getSteamGridDbKey()` + `steamgriddb:getKey`/`setKey`/`openKeyPage` IPC; `art.ts`'s `art:get` tries SteamGridDB first when a key is configured, falling back to libretro-thumbnails exact-match); `artwork.ts` (`artwork:searchGames`/`listCandidates`/`setArt`/`clearArt`/`getCurrent`/`refreshAll` IPC backing the Artwork tab — reuses `art.ts`'s exported helpers rather than duplicating the type→SGDB branch). Shared emulator types live in `emulator/types.ts`, type-imported by `preload.ts`; `steam.ts` (`steam:addGame` IPC — adds a per-game non-Steam-game shortcut to the local Steam client via `steam-shortcut-editor` (binary `shortcuts.vdf`, read-modify-write; existing entries matched by `exe`+`LaunchOptions` with **case-insensitive property names** and quote-stripped exe values, since Steam rewrites the file with its own key casing on restart); the shortcut's `exe`/`LaunchOptions` re-invoke `emusync run <slug>`; copies EmuSync's cached artwork into Steam's `config/grid/<appid>{p,'',_hero,_logo}.png` and points `icon` at the cached `icon.png` — the appid keying BOTH the artwork filenames and the vdf entry is the **unsigned 32-bit** `crc32(rawExe+appname)|0x80000000` (the 64-bit `(crc<<32)|0x02000000` variant in community docs is only the legacy Big Picture banner id — either mistake makes Steam silently ignore the art); best-effort groups the game into a Collection named after the console's full label: modern clients store collections in `config/cloudstorage/cloud-storage-namespace-1.json` — an array of `[key, entry]` pairs where a live `user-collections.<id>` entry's `value` is a JSON string `{id, name, added, removed}` and deleted collections persist as `is_deleted` tombstones (never resurrect them); `upsertCloudCollection` reuses an existing live collection with the same *name* else creates `emusync-<base64(name)>`, and every write must bump BOTH the entry `version` and namespace 1's version in `cloud-storage-namespaces.json`; the legacy `"user-collections"` key in `localconfig.vdf` is ignored on modern clients, kept only as fallback; refuses to write while Steam is running (`steamIsRunning()`, `~/.steam/steam.pid` liveness on Linux; no equivalent check on Windows) — the renderer checks `steam:isRunning` first and offers `SteamRestartModal`: Yes runs `steam:shutdown` (graceful, polled up to 30s + 2s flush grace — never a pid kill) → the normal add flow → detached `steam:launch`; with more than one Steam account present, picks whichever has the most-recently-modified `localconfig.vdf`) |
| `gui/electron/preload.ts` | `contextBridge` — everything in `window.emusync.*` is defined here |
| `gui/renderer/src/api.ts` | Fetch wrapper for the Python REST API; holds `_base` URL + `_token` |
| `gui/renderer/src/gameDelete.ts` | `deleteGame(slug, {deleteLocalRom, removeEverywhere})` — tiered delete shared by `GameConfig.tsx`'s single-game delete and `GameGrid.tsx`'s bulk delete. Tier 1 (always): unlink this device. Tier 2: also delete the local ROM. Tier 3: also delete the network-share master then full-purge |
| `gui/renderer/src/time.tsx` | Timestamp formatting: `formatRelative()` + `<RelTime>` render a relative phrase with the exact local 12-hour time in a hover tooltip. **All timestamps are UTC**, and a tz-less ISO string parses as *local* in JS — so `parseUtc()` appends `Z` when no offset/`Z` is present |
| `gui/renderer/src/App.tsx` | Root component; screen router; auto-starts server if `is_server=true`; console-screen topbar shows abbr/label/game-count next to "‹ Back" (the only back control); mouse back/forward side buttons also work via a single always-registered `mouseup` listener driven by refs — only `games`↔`console` history |
| `gui/renderer/src/components/Setup.tsx` | First-launch onboarding (choose server or join) |
| `gui/renderer/src/components/ServerStatusButton.tsx` | Server control panel modal (start/stop, PIN, LAN discovery, re-pair, shared SteamGridDB key editor — editable from any device) |
| `gui/renderer/src/components/DevicesButton.tsx` | Paired devices list modal (count, last sync times, per-device delete) |
| `gui/renderer/src/components/ConsoleGrid.tsx` | Home screen: grid of console cards, click drills into the game grid. Fetches console-def list to map stored abbr → key |
| `gui/renderer/src/components/GameGrid.tsx` | Per-console game grid: `GameCard` tiles split into "On this device"/"On other devices"; live search filter, `GameFilterButton` popover, artwork-type dropdown persisted to `art_type_by_console`; opens `GameModal`/`NetworkPlaySetup`; multi-select bulk delete with tiered `deleteGame` checkboxes; Select All/Deselect All over the currently-filtered list; bulk "Download" (localizes every selected network-sourced game via `rom:localize`, driving a byte-level `DownloadProgressModal`) and "Add to Steam" (adds every selected game via `steam:addGame`, skipping already-added slugs) |
| `gui/renderer/src/components/GameFilterButton.tsx` | Filter popover: 4 checkbox groups — Artwork, Saves, ROM availability, Steam — OR-within-group, AND-across-groups via exported `matchesFilters`. "Localized" checks whether the ROM's bytes are actually on this device right now |
| `gui/renderer/src/components/GameCard.tsx` | Individual game card: fetches artwork via `art:get`, falls back to a colour-gradient placeholder, reports the result up via `onArtStatus` for `GameFilterButton`; `artType` prop picks the tile's CSS treatment; clicking anywhere opens the settings modal except ▶ play and the selection checkbox |
| `gui/electron/art.ts` | `art:get` IPC: checks `~/.emusync/art/<consoleKey>/<slug>/<type>.png` cache, then tries SteamGridDB (resolves the SGDB game via shared `resolveSgdbGameId`: reuses `sgdb_game_id` if set, else fuzzy-searches and **persists the top result** so every later fetch on any device reuses the same match), then `getSgdbImagesForType` (shared per-type SGDB dispatch), before falling back — **grid only** — to the exact-filename libretro-thumbnails lookup; atomic temp→rename write; returns `file://` URL or null |
| `gui/renderer/src/components/NetworkPlaySetup.tsx` | Play-time cross-device setup modal — for a game not set up on this device, offers (A) point this device at the same network share or (B) pull the ROM from a device that has it |
| `gui/renderer/src/components/ConflictsButton.tsx` | Top-bar "⚠ Conflicts" panel — polls open conflicts, lists auto-resolved divergences, recovers the losing copy by finding it in save history by hash and restoring it |
| `gui/renderer/src/components/SteamRestartModal.tsx` | "Steam is open — restart it?" yes/no confirm, shared by single and bulk add. Purely presentational; each caller owns the shutdown → add → launch orchestration |
| `gui/renderer/src/components/DownloadProgressModal.tsx` | Byte-level progress modal for the bulk ROM download. Purely presentational; `GameGrid` owns the loop, progress subscription, and cancellation |
| `gui/renderer/src/components/SaveHistory.tsx` | Per-game save/state recovery modal — merges server save **and** state history with this device's local `.bak` losers into one chronological, kind-tagged timeline; flags a damaged current blob with one-click "Restore last good"; suggest-only, never auto-acts |
| `gui/renderer/src/components/GameConfig.tsx` | Add/edit game form with file pickers + the rename-heavy `handleSave`; tiered delete confirm. Split into `game-config/SyncLine.tsx` (presentational sync-status row), `game-config/useGameSync.ts` (save/state/memcard sync state + push/pull handlers, parameterized by shared-layout flags), `game-config/NetworkRomPanel.tsx` (network-ROM localize/delocalize UI); has an "Add to Steam" button, rendered disabled as "✓ In Steam" when the shortcut already exists |
| `gui/renderer/src/components/GameModal.tsx` | Tabbed per-game modal: Settings, Artwork, Devices, Save history, Run |
| `gui/renderer/src/components/ArtworkTab.tsx` | Artwork tab: search SteamGridDB → picking a result persists `sgdb_game_id` (shared across devices); 5 current-artwork tiles; clicking one opens a picker; a red-× clears, click-to-replace; one Refresh-all button re-fetches all 5 types bypassing the cache |
| `gui/renderer/src/components/ConsoleImport.tsx` | "Add Console" wizard modal — console dropdown → emulator detection → ROM scan → import. Thin shell running the `useConsoleImport` state machine. Pieces live in `components/console-import/`: `types.ts`, `helpers.ts` (pure/testable), `useConsoleImport.ts` (the phase state machine), `resolveRomPaths.ts` (per-ROM rename + network upload-to-share/rel-path resolution), `postImport.ts` (`prefetchArt`/`pullFromServerIfNewer`/`autoPush`). Network-source imports also scan the console's local-copy folder so an already-local ROM is detected; after import, `pullFromServerIfNewer` pulls any save/state (or, for a shared-layout console, the memory card) already on the server and newer than local |

---

## IPC bridge (full surface)

`preload.ts` exposes `window.emusync.*` via `contextBridge`. `main.ts` registers matching `ipcMain.handle` handlers. When adding a new channel: register the handler in the relevant `gui/electron/` module (via its `register*Ipc()`), add the bridge entry to `preload.ts`, AND add the typed signature to `EmusyncBridge` in `gui/renderer/src/emusync.d.ts` — `window.emusync` is globally typed from that `.d.ts`.

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

window.emusync.emulator.consoles()          // ordered console list { key, label, abbr }[] for the dropdown
window.emusync.emulator.detect(consoleKey)  // scans for installed emulators: RetroArch (native+flatpak) cores + standalones; returns { options: DetectedEmulatorOption[], suggestions[] }
window.emusync.emulator.scan(consoleKey, emulatorOption, extraPaths[])  // scans only that console's ROM extensions; returns { emulators, romDirs, roms[] } with consoleName+coreName per entry
window.emusync.files.ensureSave(path)       // creates an empty save file + parent dirs if missing
window.emusync.files.getSaveTime(path)      // last-modified ISO string of the save file, or null if missing
window.emusync.files.getLatestInFolder(dir) // {path, time} for the newest file in dir, or null if empty/missing
window.emusync.files.getPs2LastPlayed()      // {slug: ISO} — PS2 per-game last-played, joining ps2_serials.json with PCSX2's live playtime.dat
window.emusync.files.renameGameFiles({romPath, savePath, stateFolder, newBase, reorganize, secondaryRomPath?}) // renames a game's ROM (+ optional secondary copy) and its save/state to `newBase`; reorganize=true nests a flat ROM under <dir>/<newBase>/; returns {ok, newRomPath, newSavePath, newStateFolder, newSecondaryRomPath?, error?}

window.emusync.save.push(slug, savePath)   // reads local save, POSTs to /games/{slug}/save; {ok, error?}
window.emusync.save.pull(slug, savePath)   // GETs /games/{slug}/save, backs up existing file to .bak, writes new bytes; {ok, pulled, error?}

window.emusync.state.push(slug, stateFolder) // tar.gz's stateFolder, POSTs to /games/{slug}/state; {ok, error?}
window.emusync.state.pull(slug, stateFolder) // GETs the state archive, backs up existing files to .bak (retained on success), extracts; restores backups on failure; {ok, pulled, error?}

window.emusync.memcard.push(consoleKey, cardPath) // reads the local card, POSTs to /consoles/{key}/memcard; {ok, error?}
window.emusync.memcard.pull(consoleKey, cardPath) // GETs /consoles/{key}/memcard, backs up existing file to .bak, writes new bytes; {ok, pulled, error?}

window.emusync.device.probe(ip, port)      // TCP probe: true if ip:port reachable within 2s

window.emusync.rom.push(slug, toDeviceId, consoleName)  // stage a local ROM to another device via the server
window.emusync.rom.localize(slug, destFolder?)          // copy a network ROM onto local disk for offline play; {ok, localPath?, error?}
window.emusync.rom.delocalize(slug)                     // delete the localized copy (never the NAS master); {ok, error?}
window.emusync.rom.uploadMaster(localPath, networkPath) // copy a local-only ROM UP to the share so it becomes the master; {ok, sha256?, skipped?, error?}
window.emusync.rom.setupNetworkPlay(slug, mountRoot)    // point THIS device at a network share configured by another device; {ok, romPath?, error?}
window.emusync.rom.deleteFile(absolutePath)              // bare unlink; used by the tiered delete flow; {ok, error?}
window.emusync.rom.localizeSizes(slugs)                  // stat each slug's network master, {slug: bytes} — batch total for the download modal's overall bar
window.emusync.rom.cancelLocalize()                      // cancel the in-flight localize; its .part is cleaned up; returns {ok:false, cancelled:true}
window.emusync.rom.onLocalizeProgress(cb)                // subscribe to rom:localize-progress ({slug, copied, total}); returns the listener for offLocalizeProgress
window.emusync.rom.offLocalizeProgress(listener)         // unsubscribe

window.emusync.recovery.listLocalBackups(savePath, stateFolder) // enumerate on-disk .bak losers; {saves: LocalBak[], states: LocalBak[]}
window.emusync.recovery.restoreLocalBackup(bakPath, targetPath) // restore a .bak back into place; local-only, no server push; {ok, error?}

window.emusync.launcher.path()             // absolute path to emusync launcher binary

window.emusync.game.launch(slug)           // spawns `emusync run <slug>`
window.emusync.game.stop()                 // SIGKILL game process group (in-app launches)
window.emusync.game.stopExternal()         // kill emulator + emusync via .game_pid file (Steam launches)
window.emusync.game.hasPidFile()           // true if .game_pid exists, process is alive, cmdline contains emusync/python
window.emusync.game.isRunning()            // boolean
window.emusync.game.offlineList()          // {slug, name, console, savePath?, statePath?}[] — fallback game list when the server can't be reached
window.emusync.game.onExited(cb)           // subscribe to game:exited
window.emusync.game.offExited(cb)          // unsubscribe

window.emusync.art.get(slug, gameName, consoleKey) // fetch this console's configured artwork type; SteamGridDB then (grid only) libretro-thumbnails; caches to disk; file:// URL or null
window.emusync.art.getConsoleIcon(consoleKey) // fetch the white monochrome system logo; caches; file:// URL or null

window.emusync.daemon.start()              // spawn emusync sync-daemon (client devices only)
window.emusync.daemon.stop()               // kill the sync daemon if running

window.emusync.steamgriddb.getKey()        // fetches the shared SteamGridDB key from the server; cached in-memory for this process
window.emusync.steamgriddb.setKey(key)     // PUTs a new shared key; editable from any device's settings panel
window.emusync.steamgriddb.openKeyPage()   // opens steamgriddb.com/profile/preferences/api

window.emusync.steam.addGame(slug, gameName, consoleName, consoleKey) // adds/updates a Steam non-Steam-game shortcut + artwork + best-effort console Collection; {ok, updated?, warning?, error?}
window.emusync.steam.isAdded(slug)         // read-only: whether this game already has an EmuSync Steam shortcut
window.emusync.steam.addedSlugs()          // read-only batch form: every slug with an EmuSync Steam shortcut
window.emusync.steam.isRunning()           // Linux pid-file liveness (false on Windows)
window.emusync.steam.shutdown()            // graceful `steam -shutdown`, polls up to 30s + 2s flush grace; {ok, error?}
window.emusync.steam.launch()              // detached Steam relaunch after the writes; {ok, error?}

window.emusync.artwork.searchGames(name)                       // SteamGridDB searchGame — candidates for the Artwork tab's results list
window.emusync.artwork.getMatchedGame(sgdbGameId)               // resolves an already-picked sgdb_game_id's name for the "✓ Matched" display on reopen
window.emusync.artwork.resolveMatch(slug, gameName)             // on-demand fuzzy-search-and-persist for a game with no sgdb_game_id yet
window.emusync.artwork.listCandidates(sgdbGameId, type)         // all images of one type for a SteamGridDB game — powers the picker modal
window.emusync.artwork.setArt(slug, consoleKey, type, url)      // downloads a picked candidate, overwriting
window.emusync.artwork.clearArt(slug, consoleKey, type)         // deletes that type's saved file
window.emusync.artwork.getCurrent(slug, consoleKey)             // read-only: whatever's already cached for all 4 types
window.emusync.artwork.refreshAll(slug, gameName, consoleKey, sgdbGameId) // re-fetches all 4 types fresh
```

---

## Config and data paths

| Path | Contents |
|------|----------|
| `~/.emusync/emusync.toml` | Per-device config (server host/port/PIN, device ID/name, is_server flag, recent ROM folders) |
| `~/.emusync/emusync.db` | SQLite database (devices, games, saves, locks) |
| `~/.emusync/.server_pid` | PID of the running server process (written on start, deleted on clean exit) |
| `~/.emusync/server.log` | Rotating mirror of the server's timestamped stdout log, capped ~5MB with up to 3 backups |
| `~/.emusync/.game_pid` | Two-line file: line 1 = emusync run PID, line 2 = emulator child PID |
| `~/.emusync/blobs/{saves,states}/{row-id}` | Save/state blob bytes (one file per retained generation); `blobs/.uploads/` holds in-flight streamed uploads |
| `~/.emusync/rom_staging/` | Staged ROM files for pending transfers |
| `~/.emusync/game_cache/{slug}.json` | Cached per-device game config, written by `emusync run` on each online launch |
| `~/.emusync/game_cache/_offline_index.json` | `{slug: {name, console}}`, upserted alongside the per-slug cache; read by the GUI's `game:offlineList` IPC |
| `~/.emusync/offline_plays.json` | Append-only log of offline plays for save-conflict resolution |
| `~/.emusync/ps2_serials.json` | `{slug: serial}` map for PS2 games, learned from PCSX2's `playtime.dat`; joined with the live file so the GUI shows per-game last-played despite the shared card |
| `~/.emusync/art/<consoleKey>/<slug>/<type>.png` | Cached artwork, one file per SteamGridDB asset type |
| `~/.emusync/save_conflicts.json` | Append-only log of auto-resolved save divergences |

Config fields: `server_host`, `server_port`, `data_dir`, `device_id`, `device_name`, `is_server`, `server_pin` (optional — blank = open access), `recent_import_folders`, `watch_saves` (opt-in background save/state watcher), `import_rom_source`/`import_local_folder` (network-ROM config), `art_type_by_console` (`"grid"`/`"wide_grid"`/`"hero"`/`"logo"`/`"icon"`, default `"grid"`).

---

## Server process lifecycle

- **Initialization (zero-config):** `emusync server start` on a fresh device auto-initializes with preset defaults, no interactive prompt. Port stays the default (8765), PIN stays blank; changed afterward via the GUI or the TOML.
- **Single Ctrl+C shutdown:** `uvicorn.run(..., timeout_graceful_shutdown=3)` — one Ctrl+C exits cleanly despite the long-lived `/events/stream` SSE connections.
- **Duplicate-launch detection:** checks `.server_pid` and whether the process exists; if running, exits gracefully with the PID and port. Stale PID files are cleaned up automatically.
- **Start:** `startServerProcess()` spawns Python with `PYTHONUNBUFFERED=1`, waits for the startup signal in stdout, returns `{ ok }`. Renderer health-polls to confirm readiness.
- **Stop:** GUI: SIGKILL `serverProcess` + read `.server_pid` and SIGKILL that PID + `pkill -9 -f "emusync.py server start"`. CLI: checks `.server_pid`, kills it, echoes "server not running" if inactive.
- **Restart:** `emusync server restart` — stops then starts, for applying config changes.
- **App close:** `window-all-closed` only kills the server if the GUI spawned it — so a terminal-started server survives closing the GUI.
- **Auto-start:** `App.tsx` calls `server.start()` on init if `is_server=true`. If a server is already running externally, Python exits gracefully and the GUI doesn't manage its lifecycle.

---

## Server activity logging (terminal output)

The server prints real-time activity to stdout for operator visibility, every line timestamped with `[YYYY-MM-DD HH:MM:SS] `:

```
[2026-06-09 14:03:18] EmuSync server ready
[2026-06-09 14:03:21] new device paired called steamdeck at ip:192.168.1.42
[2026-06-09 14:10:44] Pokemon Emerald is running on steamdeck
[2026-06-09 14:10:45] save pulled: Pokemon Emerald by steamdeck
[2026-06-09 14:55:12] save pushed: Pokemon Emerald from steamdeck
[2026-06-09 15:30:00] steamdeck unpaired
```

`cli/server.py`'s `_TimestampedStream` (a thin `sys.stdout` wrapper), installed at the top of `_do_start_server`, prefixes every newly started line so all current and future stdout lines are timestamped uniformly without touching each call site. Does **not** wrap stderr or uvicorn's own logs. Stamped chunks also mirror to `~/.emusync/server.log` via `_RotatingLogWriter`.

| Line | Where | When |
|------|-------|------|
| `EmuSync server ready` / `EmuSync server running on :<port>` | `cli/server.py` | startup (`main.ts` matches `EmuSync server ready` via `.includes()` — keep that substring intact) |
| `new device paired called <name> at ip:<ip>` | `api._auth()` | first INSERT for a device |
| `<name> online` / `<name> went offline` | presence tracking | device seen / idle > 5 min |
| `<name> unpaired` | `DELETE /devices/{id}` | device removed |
| `<game> is running on <device>` / `stopped on` | lock acquire/release | |
| `save pushed`/`pulled`, `state pushed`/`pulled` | save/state sync | pull only logs on a real hit, not a 204 |
| `ROM pushed`/`pulled` | ROM transfer | staged / downloaded |

`api._print_activity(msg)` is the single sink for API-side lines — one atomic write so concurrent worker threads can't interleave. `_online_devices`/`_device_names` are protected by `_presence_lock`; `_TimestampedStream` has its own lock so writes from concurrent threads stay line-atomic.

---

## Authentication (PIN-only model)

- **Server PIN:** `server_pin` config field. All clients send `Authorization: Bearer {PIN}`.
- **Device registration:** devices auto-register on first authenticated request via `X-Device-ID`/`X-Device-Name` headers. No explicit pair/token step.
- **Blank PIN:** empty `server_pin` allows any request (open access — trusted LANs).
- **Changing the PIN:** `server:change-pin` saves the new PIN and restarts the server; existing device records persist, they just need the new PIN to reconnect.
- **Client connection:** on first launch the user enters host/port/PIN; renderer calls `configure(host, port, pin)` and `configureDevice(deviceId, deviceName)`. All API calls include PIN + device headers.

---

## State File Syncing

RetroArch stores save states in `states/<CoreName>/game.state` parallel to `saves/<CoreName>/game.sav`. State syncing mirrors save syncing at every layer (DB `states` table, `/games/{slug}/state` routes, `emusync run` pulls-before/pushes-after, Electron `savestate_directory` detection, GUI wizard badges). State sync is **opt-in** — an empty `state_path` is skipped silently.

**Auto-detection of the real save/state path** — Import registers a default path derived from the ROM filename, but RetroArch names files after the **content name**, which differs by launch method: the ROM filename when loaded by path, or the database/playlist label when loaded from a playlist. So the real save/state can sit under a different extension and/or folder. After exit, `emusync run` records a pre-launch timestamp and detects what was actually written **this session** (`_resolve_written_save`/`_resolve_written_state` in `cli/run.py`): if the configured location was written, it's kept; otherwise the wrapper adopts the newest save file/state folder written under the saves/states root and updates the `game_device` config. Conservative policy — a working config is never switched away from. **Limitation:** EmuSync only sees what RetroArch wrote during a wrapped launch; a save from a pure RetroArch-direct session is only picked up once a wrapped launch writes to the same folder.

---

## ROM Folder Tracking

During import, `rom_folder_path` is extracted from each ROM's full path and saved with the game config — enabling future re-scans of specific folders and managing multiple games from one directory. Returned by `GET /games/{slug}/device`.

---

## ROM Transfer (`emusync push` / `emusync pull`)

### `emusync push` — send a ROM to another device

1. Lists this device's games that have a `rom_path`
2. User multi-selects games (`1`, `1,3`, `1-4`)
3. Lists paired devices with online/offline status
4. User selects target device
5. Per game: checks if the target has the console configured; proposes the known ROM folder or asks for a custom path
6. Streams each ROM to server staging via `POST /games/{slug}/rom-transfer`
7. Server creates a `rom_transfers` record (status=pending), responds with `target_online`
8. CLI shows "queued — device is online" or "⚠ offline — will be delivered when it comes online"

### `emusync pull` — request a ROM from another device

The reverse: this device requests a ROM from a source device, fulfilled by the source's sync-daemon.

1. Lists paired devices with online/offline status
2. User selects the source device
3. Lists the source's games with a `rom_path`
4. User multi-selects games to pull
5. Per game: checks if this device has the console configured locally; proposes the local ROM folder or asks for a custom path
6. Sends `POST /games/{slug}/rom-pull-request` with `from_device_id` and `destination_path`
7. Server creates a `rom_pull_requests` record, SSE-notifies the source
8. CLI shows "request sent" or "⚠ offline — will be sent when it comes online"
9. Source's sync-daemon handles `rom_pull_requested`: looks up the local ROM, calls `create_rom_transfer`, marks the request fulfilled
10. Requester's sync-daemon receives `rom_transfer_queued` and downloads normally

**API surface:** `POST /games/{slug}/rom-transfer` (streams ROM bytes with `X-To-Device-ID`, `X-Destination-Path`, `X-Filename` headers; stages to `~/.emusync/rom_staging/{transfer_id}/{filename}`, hashing the stream into `rom_transfers.sha256`), `GET /game-devices`, `GET /devices/{id}/game-devices`, `GET /devices/{id}/consoles`, `POST /games/{slug}/rom-pull-request`, `GET /rom-pull-requests/pending`, `PUT /rom-pull-requests/{id}`.

**Staging dir:** `~/.emusync/rom_staging/{transfer_id}/{original_filename}` — deleted once the receiver marks the transfer `completed`/`failed`; `api.init()` sweeps stale staging dirs on startup.

**Auto-delivery via `emusync sync-daemon`**: run on any device to handle both sides automatically. On startup drains pending transfers and pull requests, then holds an SSE connection open, handling `rom_transfer_queued` (download + register) and `rom_pull_requested` (upload via `create_rom_transfer`). Reconnects on connection loss. Built into `emusync server start` as a background thread on server devices.

**`sync_client.py` delivery methods**: `list_pending_transfers()`, `download_transfer(id, dest)`, `complete_transfer(id)`, `list_pending_pull_requests()`, `complete_pull_request(id)`, `list_device_games(device_id)`, `create_pull_request(slug, from_device_id, destination_path)`, `stream_events()` (SSE generator).
