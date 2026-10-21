# EmuSync — CLAUDE.md

LAN save-file sync for emulators: one machine runs a Python/FastAPI server; other devices pair and sync automatically. GUI = Electron + React wrapping the Python CLI. No cloud/accounts.

Deep references (read on demand, don't preload): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** (modules, IPC, config/data paths, lifecycle, auth, ROM transfer, envelope) and **[docs/GOTCHAS.md](docs/GOTCHAS.md)** (long write-ups behind the rules below, with issue numbers).

## Layout

```
emusync.py          thin CLI shim (must stay at this path: install.sh/Makefile/Electron spawn/pkill)
cli/                Click CLI, one module per command group (server/device/game/console/sync/transfer/watch/run/rom/mod); consoles_data.py/detect.py = console + emulator detection
server/api/         FastAPI, one APIRouter per domain; PIN + device-header auth
server/store/       SQLite (stdlib, WAL), one mixin per table-group; schema in schema.py (PRAGMA user_version)
server/             config.py (TOML), paths.py, mdns.py, sync_client.py (HTTP client for run/push/pull)
gui/electron/       main process, per-domain modules; shared state on `rt` in runtime.ts; preload.ts = window.emusync.*
gui/renderer/src/   React; api.ts = REST fetch wrapper; components/
tests/              integration tests, real SQLite
```

Flow: Electron spawns `emusync.py server start` → renderer hits REST (`localhost:8765`) via `api.ts`; IPC handles config, server lifecycle, dialogs, launch. `emusync run <slug>`: reconcile save (push if local newer, else pull) → launch → push → release lock; server unreachable → launch offline; true divergence → newest-wins + stderr/notification/`save_conflicts.json`.

## Commands

```bash
bash install.sh        # once after clone
make dev-server | dev-gui | test | test-changed | lint | build-gui
make release VERSION=v1.2.3     # tag+push; Actions builds AppImage + NSIS
make install-service | uninstall-service   # systemd user unit (needs `sudo loginctl enable-linger $USER`, #468)
node scripts/scan-roms.mjs <folder> [--ext gba,sfc] [--depth 3] [--verbose]
```

Stack: Python 3.10+/Click, FastAPI+uvicorn, SQLite, zeroconf, tomlkit, httpx; Electron 31, React 18, TS, electron-vite.

## Testing

- **Before marking a task complete run `make test-changed`** (falls back to full suite). CI runs `make test`.
- **No mocks, real SQLite only** (a mock/prod divergence once masked a broken migration). Pattern: `tests/test_integration.py` — `client` fixture, `AUTH` headers (`Bearer <pin>`, `X-Device-ID`, `X-Device-Name`); blank PIN: `api_module.init(Store(tmpdir), "")`. Set `EMUSYNC_CONFIG_DIR` to isolate.
- Write tests for: new API route (happy + main error), new Store method, bug fix (regression). CLI subcommands: note in PR.

## Execution approval policy

No permission pause for anything scoped to this repo or its GitHub (read, edit, `gh`/`git`/build/test, issue/PR creation, commit/push). Pause only for changes outside the repo, or irreversible git ops (`push --force`, `reset --hard`, `checkout --`/`restore` over uncommitted work, `branch -D`, `--no-verify`, `--amend` on published commits). Verify external state (e.g. "PR merged?") via `gh`/`git`. Clarifying questions are fine.

## Workflow — before touching code

Skills `/issue` → `/plan` → `/implement` automate this. Manual:
1. Find/create an issue (`gh issue list --repo alekoHalkias/Emusync`; create with `gh issue create`, fallback `curl` + `$GITHUB_TOKEN`; if neither, tell the user to `gh auth login`).
2. `git fetch --prune && git branch -r` — stop and flag if a `feature/*`/`copilot/*` branch touches the same files.
3. Branch `feature/<issue>-short-desc` from fresh `main` (skip if already on one). Never commit to `main`.
4. PR body uses `Closes #N`.

Stop and warn if: another branch edits the same key files; the issue is assigned/active elsewhere; branch has no issue number.
Releases: delete tag remotely+locally, fix, re-tag. Artifacts: `EmuSync-{version}-linux-x86_64.AppImage`, `EmuSync-{version}-windows-x64-setup.exe`.

## Rules (details in docs/GOTCHAS.md)

**Saves / sync**
- Shared-memcard flag is DB-backed `console_defs.shared_memcard/shared_state`, sourced from `cli/consoles_data.py` — never re-hardcode a set (#490). Shared-layout consoles (PS2/DC/GC/PSP/3DS) never sync per-game; they use `/consoles/{key}/memcard` + `_MemcardClient`, with their own history (`console_save_history`), baseline (`console_save_sync_baseline`) and conflicts (`console_save_conflicts`) tables. Only PS2 shares states.
- Conflict = both sides moved past this device's `save_sync_baseline`, not just a hash mismatch (#460).
- Blobs carry a transfer envelope (`_pack_envelope`/`_unpack_envelope`, #478): don't add byte sniffers; keep un-enveloped fallbacks for old blobs; **hash envelope-free** (`_memcard_payload_bytes`), never hash `memcard_bytes()`.
- GUI manual push/pull shell out to CLI (`game push-save`/`pull-save`/`push-state`/`pull-state`, `console push-memcard`/`pull-memcard`); exit 0 ok, 2 nothing on server, else error. No TS tar/sniff logic (#479).
- Switch: whole-folder ROM sync (#441); saves matched by stored `switch_title_id` with self-heal (#443); mods = communal name-only pool, first push wins, no delete propagation (#444); Eden roots include `~/Emulation/storage/eden/`; title ID also discoverable by name (#448). Wii/PS3 saves are per-game, location learned post-launch (#431, #422).
- Dolphin GC card format mismatch detected via `Dolphin.ini` (#428). RetroArch: saves `saves/<Core>/`; state_path may be a folder (tar.gz, `.bak` excluded from push, pulls non-destructive); expand `~` in cfg paths.
- `%ROM%` token in `launch_command`, resolved at run time (#518).
- `SyncClient.health()` retries opt-in (`retries=2` only in `run.py`, #458). Lock heartbeat ≤120s, must stay under the 5-min offline timeout (#458).
- `store.add_game` is INSERT OR IGNORE; rename via `update_game_name`. `upsert_console_for_game` only fills blank folders (#539).

**Config / paths / DB**
- Never hardcode paths: use `server/paths.py` / `gui/electron/paths.ts` (XDG dirs; `EMUSYNC_*_DIR` disables migration; #564).
- GUI-only settings go in `display.json`, not `emusync.toml` (Python drops unknown keys, #499). All config writes atomic + 0600; corrupt TOML renamed `.corrupt-<ms>` (#535).
- Game metadata (`game_metadata`, #578): keyless Wikipedia fetch, gated by `auto_fetch_metadata` (toml, default true); `source=manual` rows are never overwritten by auto-fetch.
- Schema change: add `if from_version < N` in `_migrate()`, bump `_SCHEMA_VERSION`, add to `_SCHEMA`; keep the fresh-DB `user_version` stamp. One SQLite connection per thread. `no such column` → delete `emusync.db`.
- New IPC channel → also add to `gui/renderer/src/emusync.d.ts`. Main process uses `fetch`, not `http.get`.
- `server_host` is `""` on server devices (fall back to localhost; guard on `server_port`). `config:load` returns `null` if absent/corrupt. Pairing token regex `Pairing token: (\S*)` (blank PIN). Token prints before uvicorn binds — poll `/health`. `server:start` returns `{ok:false,error}` on early exit (#534). `install.sh`/`server:preflight` check Python/venv (#536).

**GUI**
- Console images: `getConsoleIcon` (mono, desktop) vs `getConsoleLogo` (colour, Big Picture; 3DS/Switch/PS3 come from `ART_BOOK_LOGO`); add one `CARBON_FOLDER` entry for new wheel logos (#505). New console in `consoles_data.py` needs a `folder_names` list (#462). Bulk Steam button add-or-remove by selection (#516). Live-only per-game fetches need an offline cache fallback (#464).

**Ops**
- Orphaned server: `pkill -9 -f "emusync.py server start"`; SIGKILL leaves `.server_pid`/`.server_token`. WSL2 Electron needs `--no-sandbox`, `DISPLAY=:0`. Fresh `npm install` in `gui/`: if electron binary missing, `npm install-scripts approve electron esbuild && npm rebuild electron esbuild`. Duplicate-launch guard shows a popup (notify-send→zenity→kdialog→xmessage→tk). mDNS runs in a daemon thread.

## Keeping docs updated

Update this file when policy, workflow, or a rule changes (put long explanations in docs/GOTCHAS.md). Update docs/ARCHITECTURE.md when CLI subcommands/IPC/components, config fields/data files, or server lifecycle/auth/ROM protocol change.

## Output limits
- Always write code to files using the Write/Edit tools. Never paste full files into the chat.
- When changing a file, use Edit on the specific section. Do not rewrite the whole file.
- One task per turn. Finish it, summarize in a few lines, and stop.
- Keep files under ~300 lines; split larger ones into modules.
- Don't repeat code or plans that are already written.