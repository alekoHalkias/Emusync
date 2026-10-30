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

Stack: Python 3.10+/Click, FastAPI+uvicorn, SQLite, zeroconf, tomlkit, httpx; Electron 31, React 18, TS, electron-vite.

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
Releases: delete tag remotely+locally, fix, re-tag. Artifacts: `EmuSync-{version}-linux-x86_64.AppImage`, `EmuSync-{version}-windows-x64-setup.exe`.

## Rules (details in src/docs/GOTCHAS.md)

**Saves / sync**
- Shared-memcard flag is DB-backed `console_defs.shared_memcard/shared_state`, sourced from `src/cli/consoles_data.py` — never re-hardcode a set (#490). Shared-layout consoles (PS2/DC/GC/PSP/3DS) never sync per-game; they use `/consoles/{key}/memcard` + `_MemcardClient`, with their own history (`console_save_history`), baseline (`console_save_sync_baseline`) and conflicts (`console_save_conflicts`) tables. Only PS2 shares states.
- Conflict = both sides moved past this device's `save_sync_baseline`, not just a hash mismatch (#460).
- Blobs carry a transfer envelope (`_pack_envelope`/`_unpack_envelope`, #478): don't add byte sniffers; keep un-enveloped fallbacks for old blobs; **hash envelope-free** (`_memcard_payload_bytes`), never hash `memcard_bytes()`.
- GUI manual push/pull shell out to CLI (`game push-save`/`pull-save`/`push-state`/`pull-state`, `console push-memcard`/`pull-memcard`); exit 0 ok, 2 nothing on server, else error. No TS tar/sniff logic (#479).
- Switch: whole-folder ROM sync (#441); saves matched by stored `switch_title_id` with self-heal (#443); mods = communal name-only pool, first push wins, no delete propagation (#444); Eden roots include `~/Emulation/storage/eden/`; title ID also discoverable by name (#448). Wii/PS3 saves are per-game, location learned post-launch (#431, #422).
- Dolphin GC card format mismatch detected via `Dolphin.ini` (#428). RetroArch: saves `saves/<Core>/`; state_path may be a folder (tar.gz, `.bak` excluded from push, pulls non-destructive); expand `~` in cfg paths.
- `%ROM%` token in `launch_command`, resolved at run time (#518).
- `SyncClient.health()` retries opt-in (`retries=2` only in `run.py`, #458). Lock heartbeat ≤120s, must stay under the 5-min offline timeout (#458).
- `store.add_game` is INSERT OR IGNORE; rename via `update_game_name`. `upsert_console_for_game` only fills blank folders (#539).

**Config / paths / DB**
- Never hardcode paths: use `src/server/paths.py` / `src/gui/electron/paths.ts` (XDG dirs; `EMUSYNC_*_DIR` disables migration; #564).
- GUI-only settings go in `display.json`, not `emusync.toml` (Python drops unknown keys, #499). All config writes atomic + 0600; corrupt TOML renamed `.corrupt-<ms>` (#535).
- Big Picture themes (#527, #595): folders in `<configDir>/themes/<id>/` (`theme.json`, CSS, assets, `logos/<consoleKey>.svg`), served via `emusync-theme://` (IPC `theme:list`, `theme:get`, `theme:import` for `.theme`/`.zip` archives); selected id is `theme` in `display.json`. `src/gui/electron/themes.ts` exposes `ThemeEngine` with `list()`, `get()`, `importZip()`, `importFolder()`, `registerIpc()`. Default look = `src/gui/renderer/src/themes/default.css` (base layer); gamepad focus styles stay in base `src/gui/renderer/src/styles.css` so themes cannot break navigation.
- Game metadata (`game_metadata`, #578): keyless Wikipedia fetch, gated by `auto_fetch_metadata` (toml, default true); `source=manual` rows are never overwritten by auto-fetch (src/docs/GOTCHAS.md).
- Schema change: add `if from_version < N` in `_migrate()`, bump `_SCHEMA_VERSION`, add to `_SCHEMA`; keep the fresh-DB `user_version` stamp. One SQLite connection per thread. `no such column` → delete `emusync.db`.
- New IPC channel → also add to `src/gui/renderer/src/emusync.d.ts`. Main process uses `fetch`, not `http.get`.
- `server_host` is `""` on server devices (fall back to localhost; guard on `server_port`). `config:load` returns `null` if absent/corrupt. Pairing token regex `Pairing token: (\S*)` (blank PIN). Token prints before uvicorn binds — poll `/health`. `server:start` returns `{ok:false,error}` on early exit (#534). `install.sh`/`server:preflight` check Python/venv (#536).

**GUI**
- Console images: `getConsoleIcon` (mono, desktop) vs `getConsoleLogo` (colour, Big Picture; 3DS/Switch/PS3 come from `ART_BOOK_LOGO`); add one `CARBON_FOLDER` entry for new wheel logos (#505). New console in `src/cli/consoles_data.py` needs a `folder_names` list (#462). Bulk Steam button add-or-remove by selection (#516). Live-only per-game fetches need an offline cache fallback (#464). Manual push/pull now checks for divergence via new REST conflict-check endpoints (`/games/{slug}/conflicts/check`, `/games/{slug}/state/conflicts/check`) and shows `SyncConflictModal` when both sides moved past baseline (#579). New IPC channel: `files:getFileHash` (SHA-256 of single file). New IPC channel: `files:exists` (bare `existsSync`, drives the Refresh locations broken-ROM badge, #616). Play on a missing local ROM opens `LocationResolverModal`, re-links via `PUT /games/{slug}/device` (`useBrokenRoms.ts`), and auto-fixes sibling broken games by filename in the new folder and its parent. Refresh also sets `rom_source` local/network from which console folder (`device_local_folder`/`device_game_folder` vs `device_network_folder`, longest prefix) contains the ROM (#618). Local ROM outside the console's `device_local_folder` gets a "Move to console folder" button (`MoveLocalRomPanel`, IPC `rom:moveToConsoleFolder`: rename, EXDEV copy+verify fallback, then PUT new `rom_path`/launch command, #622). A same-size file already in the console folder is adopted instead: the game is re-pathed to it, the stored path is re-read to verify, the original is kept, and the result carries `adopted: true` (#631); a different-size file still errors.

**Ops**
- Orphaned server: `pkill -9 -f "src/emusync.py server start"`; SIGKILL leaves `.server_pid`/`.server_token`. WSL2 Electron needs `--no-sandbox`, `DISPLAY=:0`. Fresh `npm install` in `src/gui/`: if electron binary missing, `npm install-scripts approve electron esbuild && npm rebuild electron esbuild`. Duplicate-launch guard shows a popup (notify-send→zenity→kdialog→xmessage→tk). mDNS runs in a daemon thread.

## Keeping docs updated

Update this file when policy, workflow, or a rule changes (put long explanations in src/docs/GOTCHAS.md). Update src/docs/ARCHITECTURE.md when CLI subcommands/IPC/components, config fields/data files, or server lifecycle/auth/ROM protocol change.

## Output limits
- Always write code to files using the Write/Edit tools. Never paste full files into the chat.
- When changing a file, use Edit on the specific section. Do not rewrite the whole file.
- One task per turn. Finish it, summarize in a few lines, and stop.
- Keep files under ~300 lines; split larger ones into modules.
- Don't repeat code or plans that are already written.