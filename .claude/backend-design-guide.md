# Backend Design Guide

## Console Definitions (`cli/consoles_data.py`)
- Standalone emulator defs are module-level dicts (`_PCSX2`, `_DOLPHIN`, etc.) with: `id`, `label`, `native_bins`, optional `flatpak_id`/`flatpak_exec`, optional `launch_args`, `dirs` with `native`/`flatpak` sub-dicts containing `save`, `state`, `memcard` paths (all `~`-templated).
- Console entries go in `_IMPORT_CONSOLES` list. Standalone-only consoles omit `system_keys`, declare `rom_extensions` explicitly, and use `databases` for core matching.
- Shared-memcard consoles set `shared_memcard=True`; shared-state adds `shared_state=True`.
- `_ROM_EXTENSIONS` set at module bottom must include every new extension — it gates the GUI scanner.

## Shared Memcard Resolution (`cli/detect.py`)
- `_resolve_shared_memcard_save_state(emu, console_abbr)` returns `(save_match, state_match)`.
- Each shared-memcard console gets a `elif console_abbr == "X"` branch probing candidates (first existing wins, else canonical default).
- The `emu` dict carries `save_dir`, `state_dir`, `core_folder` (None for standalones).

## Run-time Shared Memcard (`cli/run_ps2.py`)
- `_SHARED_MEMCARD_CONSOLES` / `_SHARED_STATE_CONSOLES` derived from console defs at import — no manual list to maintain.
- `_MemcardClient` adapts per-game save API to console-scoped endpoints; no per-console subclassing needed.

## Store (`server/store/blobs.py`)
- Console saves stored as `blobs/console_saves/<key>`. Methods: `push_console_save_file()`, `pull_console_save_path()`, `get_console_save_meta()`.
- History, baseline, conflicts tracked in separate tables (`console_save_history`, `console_save_sync_baseline`, `console_save_conflicts`).

## Server API (`server/api/blobs.py`)
- Console memcard endpoints: `GET/POST /consoles/{key}/memcard`, `GET /consoles/{key}/memcard/meta`, `GET /consoles/{key}/memcard/sync-baseline`, `GET /consoles/{key}/memcard/history`, `POST /consoles/{key}/memcard/restore`.
- Auth: `device_id = Depends(_auth)`.

## Sync Client (`server/sync_client.py`)
- Wrapper methods: `get_console_memcard_meta()`, `pull_console_memcard()`, `push_console_memcard()`, `get_console_save_sync_baseline()`, `report_console_conflict()`.

## CLI Console Commands (`cli/console.py`)
- `console push-memcard <key> <path>` / `console pull-memcard <key> <path>` shell out to sync client.
- Import wizard calls `_resolve_shared_memcard_save_state()` for shared-memcard consoles.
