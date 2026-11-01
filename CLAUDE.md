# EmuSync — CLAUDE.md

LAN save-file sync for emulators: one machine runs a Python/FastAPI server; other devices pair and sync automatically. GUI = Electron + React wrapping the Python CLI. No cloud/accounts.

Deep references (read on demand, don't preload): **[docs/ARCHITECTURE.md](src/docs/ARCHITECTURE.md)** (modules, IPC, config/data paths, lifecycle, auth, ROM transfer, envelope) and **[docs/GOTCHAS.md](src/docs/GOTCHAS.md)** (long write-ups behind the rules below, with issue numbers).

## Layout

```
src/emusync.py          thin CLI shim (must stay at this path: install.sh/Makefile/Electron spawn/pkill)
src/cli/                Click CLI, one module per command group (server/device/game/console/sync/transfer/watch/run/rom/mod); consoles_data.py/detect.py = console + emulator detection
src/server/api/         FastAPI, one APIRouter per domain; PIN + device-header auth
src/server/store/       SQLite (stdlib, WAL), one mixin per table-group; schema in schema.py (PRAGMA user_version)
src/server/             config.py (TOML), paths.py, mdns.py, sync_client.py (HTTP client for run/push/pull)
src/gui/electron/       main process, per-domain modules; shared state on `rt` in runtime.ts; preload.ts = window.emusync.*
src/gui/renderer/src/   React; api.ts = REST fetch wrapper; components/
src/tests/              integration tests, real SQLite
```

Flow: Electron spawns `src/emusync.py server start` → renderer hits REST (`localhost:8765`) via `api.ts`; IPC handles config, server lifecycle, dialogs, launch. `emusync run <slug>`: reconcile save (push if local newer, else pull) → launch → push → release lock; server unreachable → launch offline; true divergence → newest-wins + stderr/notification/`save_conflicts.json`.

## Commands

```bash
bash install.sh        # once after clone
make dev-server | dev-gui | test | test-changed | lint | build-gui
make release VERSION=v1.2.3     # tag+push; Actions builds AppImage + NSIS
make install-service | uninstall-service   # systemd user unit (needs `sudo loginctl enable-linger $USER`, #468)
node src/scripts/scan-roms.mjs <folder> [--ext gba,sfc] [--depth 3] [--verbose]
```

Stack: Python 3.10+/Click, FastAPI+uvicorn, SQLite, zeroconf, tomlkit, httpx; Electron 45, electron-builder 26, React 18, TS, electron-vite, electron-updater.

Build toolchain pin (#682): electron-vite 2.x peers Vite 4/5 only, so Vite stays on 5.x and `@vitejs/plugin-react` on 5.x until electron-vite is bumped (#681); Vite 6+/plugin-react 6 follow that.

## Testing

- **Before marking a task complete run `make test-changed`** (falls back to full suite). CI runs `make test`.
- **No mocks, real SQLite only** (a mock/prod divergence once masked a broken migration). Pattern: `src/tests/test_integration.py` — `client` fixture, `AUTH` headers (`Bearer <pin>`, `X-Device-ID`, `X-Device-Name`); blank PIN: `api_module.init(Store(tmpdir), "")`. Set `EMUSYNC_CONFIG_DIR` to isolate.
- Write tests for: new API route (happy + main error), new Store method, bug fix (regression). CLI subcommands: note in PR.

## Execution approval policy

No permission pause for anything scoped to this repo or its GitHub (read, edit, `gh`/`git`/build/test, issue/PR creation, commit/push). Pause only for changes outside the repo, or irreversible git ops (`push --force`, `reset --hard`, `checkout --`/`restore` over uncommitted work, `branch -D`, `--no-verify`, `--amend` on published commits). Verify external state (e.g. "PR merged?") via `gh`/`git`. Clarifying questions are fine.

## Workflow — mandatory skills pipeline

Every code change goes through `/issue` → `/design` → `/fplan` or `/bplan` → `/merge` (if both) → `/tplan` → `/implement` → `/review` → `/ship` → `/cleanup` (`.claude/skills/`). No exceptions for "small" fixes.

- **Detect new issues.** If the user describes a feature, bug, or change they want (even casually, without saying "issue"), invoke `/issue` with that description before anything else. Do not start reading-to-fix or editing.
- **No code edits outside `/implement`.** Do not edit, write, or delete any tracked file except via `/implement` working an approved plan file `tools/plans/<N>-*.md` on its `feature/<N>-*` branch. Each skill writes to `tools/plans/<N>-handoff.md` (the workflow state carrier) and its own outputs. If asked to change code directly, refuse briefly and route through the pipeline: `/issue` for new work, or `/plan <N>` / `/implement <N>` to resume.
- **Enforced** by the PreToolUse hook `.claude/hooks/require_plan.py`: Edit/Write on repo files outside `tools/plans/` and `.claude/` is blocked unless the branch's plan has `Status: implementing` (set by `/implement`). Never edit around it via shell.
- **Resume, don't restart.** Given an issue or PR number, resolve the stage per `/plan`'s "Resolve" section and continue there.
- **Exempt:** read-only investigation and answering questions; editing `.claude/skills/` itself when the user explicitly asks to change the workflow.
- **Handoff file:** `tools/plans/<N>-handoff.md` is the workflow state carrier. Every skill reads it first, writes its section, and passes it forward. It carries state through the entire pipeline — never rely on conversation memory. See `.claude/skills/SKILLS_OVERVIEW.md` for its structure.
- No emojis in issues, plans, commits, or PRs. Never commit to `main`. PR body uses `Closes #N`.

Stop and warn if: another branch edits the same key files; the issue is assigned/active elsewhere; branch has no issue number.
Releases: delete tag remotely+locally, fix, re-tag. Artifacts: `EmuSync-linux-x86_64.AppImage` (version-free so a Steam non-Steam shortcut survives updates, #668; the version shows in the settings Details panel via `updater:getVersion`), `EmuSync-{version}-windows-x64-setup.exe`, plus `latest.yml`/`latest-linux.yml` for electron-updater. Build jobs run `electron-builder --publish never`; only the release job publishes (#638). `build.publish` needs `owner` and `repo` as separate fields, otherwise the update feed URL is malformed (#640).

## Rules (details in src/docs/GOTCHAS.md)

**Saves / sync**
- Shared-memcard flag is DB-backed `console_defs.shared_memcard/shared_state`, sourced from `src/cli/consoles_data.py` — never re-hardcode a set (#490). Shared-layout consoles (PS2/DC/GC/PSP/3DS) never sync per-game; they use `/consoles/{key}/memcard` + `_MemcardClient`, with their own history (`console_save_history`), baseline (`console_save_sync_baseline`) and conflicts (`console_save_conflicts`) tables. Only PS2 shares states.
- Conflict = both sides moved past this device's `save_sync_baseline`, not just a hash mismatch (#460).
- Blobs carry a transfer envelope (`_pack_envelope`/`_unpack_envelope`, #478): don't add byte sniffers; keep un-enveloped fallbacks for old blobs; **hash envelope-free** (`_memcard_payload_bytes`), never hash `memcard_bytes()`.
- Archive restores extract to a temp dir then swap (`_extract_tar_to_tmp`), never delete/rename the target first; merge backs up by member relative path; state extract moves files individually (#692).
- GUI manual push/pull shell out to CLI (`game push-save`/`pull-save`/`push-state`/`pull-state`, `console push-memcard`/`pull-memcard`); exit 0 ok, 2 nothing on server, else error. No TS tar/sniff logic (#479).
- No chunked upload API (#703): the unfinished `/chunks` routes were removed; saves/states/memcards go through the single streamed `POST` (`_stage_upload`).
- Switch: whole-folder ROM sync (#441); saves matched by stored `switch_title_id` with self-heal (#443); mods = communal name-only pool, first push wins, no delete propagation (#444); Eden roots include `~/Emulation/storage/eden/`; title ID also discoverable by name (#448). Wii/PS3 saves are per-game, location learned post-launch (#431, #422).
- Dolphin GC card format mismatch detected via `Dolphin.ini` (#428). RetroArch: saves `saves/<Core>/`; state_path may be a folder (tar.gz, `.bak` excluded from push, pulls non-destructive); expand `~` in cfg paths.
- API boundary hygiene (#693): `_core._safe_segment` validates path segments (Switch mod `title_id`/`mod_name`); `_core._clean_header` strips control chars from `X-Device-ID/Name`; ROM uploads capped at `transfers._MAX_UPLOAD_BYTES` (413) and staging dir removed on stream failure; `run.py:_release` retries lock release once.
- Trust boundaries (#705): `transfer._destination_allowed` confines received ROM writes to configured ROM folders (rom-folder never onto a console root); CORS `null` origin is a documented limitation (GOTCHAS).
- Client run/extract safety (#699): SIGHUP/SIGINT use `run.py:_interrupt_handler` (graceful push + release, no `sys.exit`); `_safe_extract_tar` uses `filter="data"` or rejects special members; whole-blob transfers use `sync_client._TRANSFER_TIMEOUT`, never `timeout=30`.
- Transfer data-loss guards (#715): ROM downloads stream to `<dest>.part` and `os.replace` after the hash check (never write the real path first); the save/memcard pull baseline is recorded by a `BackgroundTask` after the body is sent, not before; `_stage_upload` rejects empty bodies (400).
- `%ROM%` token in `launch_command`, resolved at run time (#518).
- `SyncClient.health()` retries opt-in (`retries=2` only in `run.py`, #458). Lock heartbeat ≤120s, must stay under the 5-min offline timeout (#458).
- `store.add_game` is INSERT OR IGNORE; rename via `update_game_name`. `upsert_console_for_game` only fills blank folders (#539) and routes a game folder the console doesn't cover into `consoles.device_extra_folders` instead of a new row (#629; never a folder inside `device_network_folder`). `ConsoleFoldersModal` = one block per console, label-only emulator select, extras list; `sourceFor` treats extras as local.

**Config / paths / DB**
- Never hardcode paths: use `src/server/paths.py` / `src/gui/electron/paths.ts` (XDG dirs; `EMUSYNC_*_DIR` disables migration; #564).
- Device dedupe (#656): `touch_device` merges device rows sharing a server-resolved ARP MAC (`devices.mac`, schema v32, `server/arp.py`, `merge_devices` + `_DEVICE_REFS` in `store/devices.py`: add any new device-id column there). `device_id` is also backed up to `<data_dir>/device_id` and restored by `config.load()`. See GOTCHAS.
- GUI-only settings go in `display.json`, not `emusync.toml` (Python drops unknown keys, #499). All config writes atomic + 0600; corrupt TOML renamed `.corrupt-<ms>` (#535).
- Game metadata (`game_metadata`, #578): keyless Wikipedia fetch, gated by `auto_fetch_metadata` (toml, default true); `source=manual` rows are never overwritten by auto-fetch (src/docs/GOTCHAS.md).
- Schema change: add `if from_version < N` in `_migrate()`, bump `_SCHEMA_VERSION`, add to `_SCHEMA`; keep the fresh-DB `user_version` stamp. Never reuse a schema number a deployed (even closed/unmerged) branch may have stamped: a DB already at N skips `from_version < N`, so take the next free number (#647; v30 is intentionally empty). One SQLite connection per thread. `no such column` → delete `emusync.db`.
- New IPC channel → also add to `src/gui/renderer/src/emusync.d.ts`. Main process uses `fetch`, not `http.get`.
- `server_host` is `""` on server devices (fall back to localhost; guard on `server_port`). `config:load` returns `null` if absent/corrupt. Pairing token regex `Pairing token: (\S*)` (blank PIN). Token prints before uvicorn binds — poll `/health`. `server:start` returns `{ok:false,error}` on early exit (#534). `install.sh`/`server:preflight` check Python/venv (#536).

**GUI**
- Console images: `getConsoleIcon` (mono). New console in `src/cli/consoles_data.py` needs a `folder_names` list (#462). Bulk Steam button add-or-remove by selection (#516). Live-only per-game fetches need an offline cache fallback (#464). Manual push/pull now checks for divergence via new REST conflict-check endpoints (`/games/{slug}/conflicts/check`, `/games/{slug}/state/conflicts/check`) and shows `SyncConflictModal` when both sides moved past baseline (#579). New IPC channel: `files:getFileHash` (SHA-256 of single file). New IPC channel: `files:exists` (bare `existsSync`, drives the Refresh locations broken-ROM badge, #616). Play on a missing local ROM opens `LocationResolverModal`, re-links via `PUT /games/{slug}/device` (`useBrokenRoms.ts`), and auto-fixes sibling broken games by filename in the new folder and its parent. Refresh also sets `rom_source` local/network from which console folder (`device_local_folder`/`device_game_folder` vs `device_network_folder`, longest prefix) contains the ROM (#618). Local ROM outside the console's `device_local_folder` gets a "Move to console folder" button (`MoveLocalRomPanel`, IPC `rom:moveToConsoleFolder`: rename, EXDEV copy+verify fallback, then PUT new `rom_path`/launch command, #622). A same-size file already in the console folder is adopted instead: the game is re-pathed to it, the stored path is re-read to verify, the original is kept, and the result carries `adopted: true` (#631); a different-size file still errors. Same panel's "Add to network drive" uploads via `rom:uploadMaster` and PUTs `rom_source=network` + master `rom_path` + `local_rom_path` (#624). Refresh locations collects local-source games (`useBrokenRoms.refresh` -> `candidates`) and opens `LocalToNetworkModal` to bulk move them into the console folder and/or add them to the network drive via shared `game-config/localToNetwork.ts:uploadLocalRom` (#626). Auto-update: `src/gui/electron/updater.ts` wraps `electron-updater` (`registerUpdaterIpc()`, `updater:check/download/install/getVersion/getEnabled/setEnabled`, events forwarded via `updater:change`); `autoUpdateEnabled` in `display.json` gates checks; `UpdateBanner` component shows available/downloaded states (#634).

- Network share identity (#644): a console's network folder holds `.emusync-share-id` (UUID, IPC `files:ensure-share-marker`, created if absent); it is stored per device as `consoles.network_share_id` (schema v30) and equal IDs on different devices mean the same share despite different mount paths. `GET /consoles/{name}/shares` lists other devices' IDs; the console import wizard compares them and auto-links existing games on a match (`useNetworkShare.ts`). Unwritable share = no ID ("Unverified", no auto-link).

- Import ignore list (#646): per-device, per-console ROM paths hidden from the console import wizard, stored as `import_ignored_roms[consoleKey]` in emusync.toml (declared on `Config` in `server/config.py`, or Python drops it, #499). Read/written via `console-import/ignoredRoms.ts`; managed from the "Ignored games" panel in `ConsoleFoldersModal`. Ignoring never touches files or imported games; a ROM with a network + local copy ignores both paths.

- Refresh finds new games (#650): `GameGrid`'s Refresh locations also calls `console-import/scanNewRoms.ts` (this console's ROM, extra, local and network folders; emulator picked by `device_emulator` label else first detected; ignore list and games already linked on this device are dropped; network+local copies merged), reports the count, and its "Review and import" button opens `ConsoleImport` with `initialConsole`/`initialRomDirs`/`initialNetworkRoot`/`initialLocalRoot` seeded from the console row. Nothing is imported without confirmation.

- Network ROM upload requests (#660): a device asks another to put its local-only ROM on the console's network drive via `POST /games/{slug}/rom-pull-request` with `kind="network-upload"` (reuses `rom_pull_requests`, no schema change; 400 if the owner has no local ROM, 409 if already on a network drive, repeat asks return the pending id; `GET /rom-pull-requests/outgoing` shows the requester's own). The owner fulfils on sync-daemon start/SSE (`cli/netrom.py:upload_to_network`, verifies the `.emusync-share-id` marker, never overwrites a master); ROMs over `network_upload_auto_max_mb` (toml, default 512, declared on `Config`) stay pending for GUI approval (IPC `rom:fulfillNetworkUpload` shells out to CLI `rom fulfill-network-upload <id> [--decline]`). `GET /games/{slug}/network-source` returns the source console's `share_id`; equal IDs let a device use its own console network folder with no setup (`NetworkPlaySetup`; it also offers "Request upload" and shows request status; `NetworkUploadPrompt` banner in `App.tsx` lists pending large requests).

**Ops**
- AppImage runtime (#677): the AppImage bundles the CLI (`build.extraResources` in `src/gui/package.json`; `test_bundle.py` fails if a `src/` package is missing) and `runtimeSetup.ts:ensureRuntime()` copies it to `<cacheDir>/runtime/src` and builds `<cacheDir>/runtime/.cache/.venv` from system python3 (same layout as a checkout, stamped by app version and requirements hash, retries after failure). `runtime.ts` `RUNTIME_DIR`/`USE_RUNTIME_DIR` (packaged AppImage, no `EMUSYNC_SCRIPT`) point `SCRIPT`/`PYTHON`/`LAUNCHER` into it; server start, sync daemon, `server:preflight` and `steam:addGame` await `ensureRuntime()` first, so Steam shortcuts target `<cacheDir>/runtime/src/emusync`, never the AppImage mount. `src/requirements.txt` is runtime-only; tests/CI/`install.sh` use `requirements-dev.txt`. See GOTCHAS.
- Dependencies (#679): audited against all code; `adm-zip` removed (unused). Python floors in `src/requirements*.txt` track the versions CI/tests verify. `uvicorn[standard]` is kept for uvloop/httptools speed (websockets/watchfiles unused). Electron 45, electron-builder 26, electron-vite 6, Vite 8, plugin-react 6, React 19 and TypeScript 7 are current (#681, #682, #683, #684, #689); the Vite 8 toolchain needs Node ^20.19 or >=22.12, so CI uses Node 22. `renderer/src/vite-env.d.ts` declares CSS side-effect imports, which TS 7 requires. `tsc --noEmit` has known pre-existing errors (files.ts, steam.ts, GameConfig, GameGrid, SyncConflictModal).
- Orphaned server: `pkill -9 -f "src/emusync.py server start"`; SIGKILL leaves `.server_pid`/`.server_token`. WSL2 Electron needs `--no-sandbox`, `DISPLAY=:0`. Fresh `npm install` in `src/gui/`: if electron binary missing, `npm install-scripts approve electron esbuild && npm rebuild electron esbuild`. Duplicate-launch guard shows a popup (notify-send→zenity→kdialog→xmessage→tk). mDNS runs in a daemon thread.

## Keeping docs updated

Update this file when policy, workflow, or a rule changes (put long explanations in src/docs/GOTCHAS.md). Update src/docs/ARCHITECTURE.md when CLI subcommands/IPC/components, config fields/data files, or server lifecycle/auth/ROM protocol change.

## Output limits
- Always write code to files using the Write/Edit tools. Never paste full files into the chat.
- When changing a file, use Edit on the specific section. Do not rewrite the whole file.
- One task per turn. Finish it, summarize in a few lines, and stop.
- Keep files under ~300 lines; split larger ones into modules.
- Don't repeat code or plans that are already written.