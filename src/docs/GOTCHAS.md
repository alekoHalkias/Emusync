# EmuSync — gotchas

One-line rules live in CLAUDE.md; this is the "why". Read the entry for the area you're touching. History: `git log`/`git blame` and the issue numbers.

## Sync correctness

**Conflict = both sides moved past this device's baseline (#460, #481).** A plain local≠server hash is also true for routine catch-up (A pushes, B's untouched copy differs). `save_sync_baseline` / `console_save_sync_baseline` store the hash each device last agreed on; conflict requires `local != baseline AND server != baseline`. No baseline → old always-check behavior. Baselines are written server-side by the push/pull handlers in `server/api/blobs.py` (saves + memcards, never states), so every caller gets them. Separate table, not a `game_devices` column, because `set_game_device` does `INSERT OR REPLACE` and would wipe it. `_reconcile_save` is generic over its client — `_MemcardClient` just supplies real baseline data.

**Transfer envelope (#478).** Every save/state/memcard/mod blob = `b"ES1\0"` + format byte (`0` raw, `1` tar, `2` tar.gz) + payload, via `_pack_envelope`/`_unpack_envelope`. Never add a byte-sniffer. Blobs without the magic predate #478 — the sniff-by-parsing fallbacks are load-bearing, keep them. **Hash envelope-free**: `_memcard_payload_bytes()` for compares; `_stage_upload` hashes minus the 5-byte header. Hashing enveloped bytes once changed every stored hash and turned #460 into a false-conflict storm on every game (`tests/test_saves.py::test_push_save_hash_excludes_transfer_envelope`). `memcard_bytes()` is wire-only.

**GUI manual push/pull shells out to the CLI (#479).** `gui/electron/sync/{save,state,memcard}.ts` spawn `emusync game push-save|pull-save|push-state|pull-state <slug> <path>` / `emusync console push-memcard|pull-memcard <key> <path>`; exit `0` ok, `2` nothing on server (`pulled:false`, not an error), else error. No TS tar/envelope logic — extend a CLI subcommand instead. Memcard goes through `_MemcardClient` so GC gets the card-format check (#428).

**Post-game push safety.** `_save_is_safe_to_push` refuses a 0-byte save or one that shrank below 50% of the server copy. Integrity sweep uses the same `_SHRINK_FLOOR`.

**IGDB metadata endpoint.** `GET /games/{slug}/metadata` fetches and caches metadata from IGDB. Auto‑fetch is enabled by default and can be disabled via `auto_fetch_metadata` config. The endpoint returns cached data if present or fetches from IGDB if allowed.

**Manual override.** The client can request a fresh fetch by including `force=true` query parameter; the server will ignore the cache and store the new result. This is useful when the cached data is stale or incorrect.


**Health retries are opt-in (#458).** One missed `/health` used to send the whole session down the silent offline path. `health(retries=N)` defaults to 0; only `cli/run.py`'s pre-launch check passes `retries=2` (and warns if it still goes offline). Don't add retries to one-shot callers — latency only.

**Lock heartbeat ≤120s (#458).** A headless `emusync run` (Steam Deck Gaming Mode, no GUI `/whoami` pings) is only "online" via its lock re-acquire. `_HEARTBEAT_INTERVAL_SECONDS` is capped at 120s, under `OFFLINE_TIMEOUT_SECONDS` (5 min) plus the monitor's 30s poll; otherwise the lock gets force-released mid-game and another device races in. `tests/test_lock_heartbeat_interval.py` asserts it — change both together.

**Duplicate-launch guard.** If the lock is already held, `_show_game_running_popup` exits; fallback chain `notify-send` → `zenity` → `kdialog` → `xmessage` → tkinter.

## Shared-save-layout consoles (PS2 / DC / GC / PSP / 3DS)

**Single source of truth is `shared_memcard`/`shared_state` on each console dict in `cli/consoles_data.py` (#490).** Seeds `console_defs` columns, served via `/console-defs` as `sharedMemcard`/`sharedState`. Consumers: `run_ps2.py` derives its sets from `consoles_data.py` at import (no network); `scan.ts` reads `rt.cachedConsoleDefs`; `console-import/helpers.ts` reads a cache `App.tsx` fills from `emulator.consoles()`. The three old hardcoded copies had drifted (`"gc"` vs `"gamecube"`). New shared console = one flag.

**Never treat these saves as per-game.** Sync as one console card via `/consoles/{key}/memcard` + `_MemcardClient`. Card paths (first existing candidate): PS2 `memcards/Mcd001.ps2`; DC `saves/vmu_save_A1.bin` (A1 only); GC Dolphin `User/GC`; PSP `PPSSPP/PSP/SAVEDATA`; 3DS (Azahar) `sdmc/Nintendo 3DS/<ID0>/<ID1>/title` (probe existing hash dirs, else all-zeros). **States are separate:** only PS2 shares states (serial-named `sstates/`, filtered by `_ps2_state_serial_prefix`); others are per-game; 3DS states not synced (#418).

**Parallel tables, not reused ones.** `console_saves` = single current card (overwritten). History is `console_save_history` (#480), restore re-pushes a past generation (history only grows). Conflicts go in `console_save_conflicts` (#482) because `save_conflicts.game_slug` FKs `games`; `list_open_conflicts` is a `UNION ALL` (console rows have `console_key`, null `game_slug`); `dismiss_conflict` tries both (UUID ids). GUI: `SaveHistory`'s `consoleKey` prop is the console **abbr** (`"PS2"`, `"GC"`), not `GameModalTarget.consoleKey` (lowercase, for art) — the wrong one silently matches nothing. `ConflictsButton` branches on `!!c.console_key` and finds the card path via `listMyGameDevices()`.

**PCSX2 nests saves one level down.** `memcard_bytes` walks the whole tree (`rglob`), deterministic tar (sorted, mtime=0). A top-level walk drops every game. `_write_memcard` backs up the whole card as `<card>.bak` and extracts through `_safe_extract_tar`.

**Dolphin GC card format comes from `Dolphin.ini` (#428).** `MemoryCard` file vs `GCIFolder` tree is per-device (`[Core] SlotA/SlotB`). Pulls extract on top without clearing, so mismatched devices silently pile up both formats. `_dolphin_card_format` reads the ini (native + flatpak paths), never guesses from disk. Pushes send `X-Card-Format` (stored in `console_saves.card_format`); a pull with a known, differing format skips extraction and reports via stderr, a notification and `card_format_mismatch.json`. `"unknown"` never blocks. No conversion — that's Dolphin's "Convert File".

## Learned save paths (Switch / Wii / PS3)

Import leaves `save_path` blank; it's adopted after a session from whichever single folder was written (more than one written = ambiguous → skip + warn). A filename-derived guess is actively wrong for these.

**Wii (#431):** `Wii/title/00010000/<hex-game-id>/data/`. Never touch `content/` or `00000001/*` (system titles). No title-ID guessing — wrong guess seeds the wrong NAND folder.

**PS3 (#422):** `dev_hdd0/home/00000001/savedata/<TITLE_ID>/` (native/flatpak/EmuDeck roots). Only `.iso`/`.pkg` scan; `PS3_GAME/` folders don't. Layout from RPCS3 docs, not verified on a real install.

**Switch (#443, #448, #456):**
- Saves are matched by `games.switch_title_id` (shared across devices). Sources, in order: bracketed 16-hex tag in the ROM filename (`_switch_title_id_from_rom`); exact-name match against blawar/titledb in `switchtitledb.ts` (cached `<cache dir>/switch_titledb.json`; **no fuzzy match** — wrong ID seeds the wrong folder); self-heal from the adopted Eden folder's basename (many dumps have no tag).
- Pre-reconcile: `_find_local_switch_save` looks for a non-empty `<profile>/<title-id>` in every Eden profile and adopts it. No local save + server has one → `_seed_switch_save` seeds every profile with mtime before `launch_start`, so post-launch detection still finds exactly one.
- `emusync game ensure-switch-save-folder` creates empty placeholders (inert; excluded from the "has data" check).
- GUI sync panel shows for Switch with blank `save_path`; Pull → `emusync game pull-switch-save` (seeds and persists `save_path` immediately).
- **Eden roots:** `~/.local/share/eden/` **and** EmuDeck's `~/Emulation/storage/eden/` (`_SWITCH_NAND_ROOTS`, `_SWITCH_LOAD_ROOTS`). A missing root looks exactly like "saves don't sync", with no error — check for a third convention before blaming sync logic.
- Eden has no save states; `SaveHistory` `hideStates` for Switch.

**Switch ROM = whole folder (#441).** Push/pull tars the ROM's containing folder (base + update/DLC) as `kind="rom-folder"`. Eden can't install updates headlessly and its NAND content store is shared, so folder-as-unit is the design. Don't add a separate update-management tool.

**Switch mods = communal name-keyed pool (#444).** `load/<title-id>/<mod>/`, can be GBs. `switch_mods` keyed `(title_id, mod_name)`: first push wins, no history, no delete propagation. `_sync_switch_mods` runs a name-only diff each launch (never re-hashes); failures never block launch. GUI "Sync now" shells out to `emusync mod sync`.

## RetroArch

- Config paths use `~` → `parseRetroArchCfg` expands it; never use a raw cfg value as a path. `rgui_browser_directory = "default"` means unset — filtered.
- Per-core saves always `saves/<CoreName>/`; scan still checks root for pre-per-core saves.
- "Sort by content directory": `state_path` is a **folder** (`statesRoot/GameName/`), synced as tar.gz. State pulls are non-destructive (overwritten files kept as `.bak`); pushes exclude `.bak`.
- Content name ≠ ROM filename when launched from a playlist → `_resolve_written_save/_state` adopt what was actually written this session; a working config is never switched away from. Saves from non-wrapped sessions are only seen by the opt-in `watch_saves` watcher.

## Config / paths / DB

**XDG dirs, never hardcode (#564).** Use `server/paths.py` / `gui/electron/paths.ts` (`tests/test_paths.py` checks they agree; `paths.ts` reads `data_dir` from TOML). `paths.migrate_legacy()` (via `emusync migrate`, `config.load()`, Electron `migrate.ts`, imported first in `main.ts`) moves `~/.emusync`: never overwrites, refuses if an old server is running or the target has `emusync.db`, leaves `MOVED_TO_XDG.txt`. **Any `EMUSYNC_*_DIR` override disables migration**; `tests/conftest.py` sets them so tests never touch real files. Update every device — an old build recreates an empty `~/.emusync`.

**GUI-only settings → `display.json` (#499).** `config.save()` rebuilds TOML from the dataclass, dropping unknown keys. `display.ts` owns `{scale, fullscreen}`; `bigPicture` follows fullscreen (no separate toggle), sets `html[data-bigpicture]`, swaps `ConsoleGrid` → `ConsoleWheel`. Desktop styles must never depend on it.

**Config writes atomic + 0600; corrupt ≠ missing (#535).** A parse error used to look like "no config" → Setup re-ran and overwrote `device_id`/PIN. Corrupt file → renamed `emusync.toml.corrupt-<ms>`. All writers write `.tmp` 0600 + rename; never a bare `writeFileSync(CONFIG_PATH, …)`. `config:load` returns `null` for missing or corrupt.

**Schema migrations.** `PRAGMA user_version`: add `if from_version < N` to `_migrate()`, bump `_SCHEMA_VERSION`, add to `_SCHEMA`. Fresh DBs are stamped with `_SCHEMA_VERSION` — keep the stamp or every install replays the chain. `no such column` → delete `<data dir>/emusync.db`.

**One SQLite connection per thread** (`_ThreadLocalConnection`): uvicorn workers and the presence-monitor thread both hit the store. `PRAGMA foreign_keys` is per-connection, set in the factory.

**`store.add_game` is INSERT OR IGNORE**; rename with `update_game_name`.

**`upsert_console_for_game` fills blanks only (#539)** so `ConsoleFoldersModal` edits stick; stale folders no longer self-correct. A console is one primary row; a game folder it does not cover is appended to `device_extra_folders` (#629) rather than creating a second row (never a folder inside `device_network_folder`, which `sourceFor` would misclassify as local). Older multi-row consoles keep their rows and show read-only in the modal.

**`%ROM%` in `launch_command` (#518).** `emusync run` shlex-splits and runs it; `_resolve_launch_command` substitutes the ROM in use (local, network master, or offline copy). `GameConfig` converts legacy literal paths on load; literal-path rewrites remain only for legacy commands.

## Server / Electron

- **Orphaned server:** `pkill -9 -f "emusync.py server start"`. SIGKILL skips `finally`, so `.server_pid`/`.server_token` can survive — the stop handler deletes them. `server start` detects a running one and exits.
- **systemd user service dies on logout without linger (#468):** looks like random offline until someone SSHes in. `sudo loginctl enable-linger $USER`; `make install-service` warns.
- **Token prints before uvicorn binds** — poll `/health`. Blank PIN prints `"Pairing token: "` → regex `Pairing token: (\S*)`.
- **`server:start` failures (#534):** keeps a ~1.5KB stdout/stderr tail, returns `{ok:false,error}` on non-zero exit before ready (exit 0 = already running). `Setup.tsx` reverts `is_server` if `/health` never answers. The 5s "assume ready" fallback stays; the renderer's health poll is the real check. Ready-line match is `.includes("EmuSync server ready")` — keep that substring.
- **Preflight (#536):** `install.sh` fails early on Python <3.10 or missing `venv`/`ensurepip` (Debian: `python3-venv`), skips GUI on Node <18. `server:preflight` IPC test-imports server deps; `PYTHON` is `.cache/.venv/Scripts/python.exe` on Windows.
- **mDNS** runs in a daemon thread so the token prints immediately; `finally` joins (2s) before unregistering.
- **`server_host` is `""` on server devices** → fall back to localhost; use `!cfg.server_port` as the "not configured" check.
- **Main process HTTP:** use `fetch` (`sync.ts`, `steamgriddb.ts`, `sync/rom.ts`); `http.ts`'s `httpGetJSON` is a legacy Node-http helper.
- **New IPC channel** → handler in its module's `register*Ipc()`, entry in `preload.ts`, signature in `gui/renderer/src/emusync.d.ts` (`EmusyncBridge`), or call sites aren't type-checked.
- **WSL2:** `--no-sandbox` (in `npm run dev`) + `DISPLAY=:0`; dbus errors harmless. `--ozone-platform-hint=auto` picks Wayland when present (#439).
- **Fresh `npm install` in `gui/`:** npm's install-scripts gate can skip electron/esbuild postinstall (`Error: Electron uninstall`). `allowScripts` in `package.json` pre-approves; otherwise `npm install-scripts approve electron esbuild && npm rebuild electron esbuild`.

## GUI

- **Offline modal data (#464):** `useGameList` falls back to `game_cache/`; `GameConfig` uses `game:offlineDeviceConfig`. Other per-game tabs doing live-only fetches (Devices/History/Artwork/Mods) have no fallback — wire one per tab if needed.
- **Library import (#462)** reuses `ConsoleImport` verbatim per `{folder, consoleKey}` queue item (advances on `onClose`; no batch cancel). Folder matching depends on `console_folder_names` — a new console in `consoles_data.py` needs a realistic `folder_names` list (`ps1`, `megadrive`…; key/abbr/label already match).
- **Two console-image sources (#505):** `getConsoleIcon` = RetroArch XMB mono glyphs (desktop grid); `getConsoleLogo` = es-theme-carbon colour SVGs via `CARBON_FOLDER` (Big Picture wheel); 3DS/Switch/PS3 from art-book-next-es-de `ART_BOOK_LOGO` (no license — fetch at runtime, never bundle). Fallback: mono icon → abbr text.
- **Bulk Steam button (#516):** adds the not-yet-added ones; only an all-added selection flips to Remove (shortcut only; art/collection left inert).
- **Timestamps are UTC;** a tz-less ISO string parses as local in JS → use `parseUtc()` in `time.tsx`.

## Game metadata (#578)

- Manual rows (`source='manual'`) are protected in `Store.set_metadata` itself, not in the route, so no caller can clobber them. DELETE is the only way back to auto-fetch.
- Wikipedia is a fuzzy keyless match (`"<name> video game"`, first hit). It yields synopsis and thumbnail only; there is no release date, so that field is manual-only. Wrong match: PUT the right text.
- Fetch never raises and retries once (1s) on 429/5xx. `WIKI_BASE` is a module constant so tests can point it at a local stub server.
- `auto_fetch_metadata` is written to `emusync.toml` only when false (default true).
