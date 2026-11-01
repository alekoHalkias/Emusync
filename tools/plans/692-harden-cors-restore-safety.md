# Plan: #692 Harden CORS, PIN check, external URLs and archive restore safety

Issue: #692
Branch: feature/692-harden-cors-restore-safety
PR: none
Status: planned
Fix attempts: 0

## Goal
Close the CORS/PIN/openExternal holes and make memcard and state restores failure-safe, with regression tests.

## Design Alignment
- **Backend Pattern**: stay in the existing module-level helpers (`_safe_extract_tar`, `.bak` one-generation convention, `os.replace`); no new modules, no schema/config change.
- **Recommendations**: CORS decision = origin allowlist, not mandatory PIN (blank PIN is the supported default, so a PIN requirement would break pairing). Allow `null` (Electron `file://` renderer), `http://localhost[:port]`, `http://127.0.0.1[:port]` via `allow_origin_regex`. Residual: any sandboxed iframe also sends `null`; PIN remains the real control for exposed servers. Document in GOTCHAS.md.

## Steps
- [ ] 1. CORS allowlist in `_core.py`: replace `allow_origins=["*"]` with `allow_origin_regex=r"null|https?://(localhost|127\.0\.0\.1)(:\d+)?"` (Starlette fullmatches it).
  - Files: src/server/api/_core.py
  - Reuses: existing CORSMiddleware registration
  - New: none
- [ ] 2. Constant-time PIN: `import hmac`; replace `pin != _master_pin` (line ~225) with `not hmac.compare_digest(pin.encode(), _master_pin.encode())` (encode so non-ASCII does not raise TypeError).
  - Files: src/server/api/_core.py
  - Reuses: existing check
  - New: none
- [ ] 3. Shared temp-extract helper in `sync_client.py`: `_extract_tar_to_tmp(tar_bytes, mode, parent) -> Path` that opens the tar in a `with` (closes it), makes `tempfile.mkdtemp(dir=parent, prefix=".emusync-")`, runs `_safe_extract_tar` into it, and on any exception `shutil.rmtree`s the temp dir and re-raises. Used by steps 4-6.
  - Files: src/server/sync_client.py
  - Reuses: `_safe_extract_tar`
  - New: one small helper - the three restores need the same extract-then-swap logic; nothing existing does it.
- [ ] 4. `_write_memcard_tar_bytes`: extract to temp (sibling of `card`, same filesystem) FIRST; only on success back up (`bak` rmtree if present; dir -> `os.replace(card, bak)`; file -> `copy2` to bak then unlink) and `os.replace(tmp, card)`. On TarError the card is untouched and `TarError` still propagates so `_write_memcard`'s raw-file fallback keeps working. Tarfile closed via helper.
  - Files: src/server/sync_client.py
  - Reuses: `_extract_tar_to_tmp`, existing `.bak` naming
  - New: none
- [ ] 5. `_extract_state_folder`: for the tar.gz branches (envelope TARGZ and legacy sniff) extract to temp first; only then rename existing non-`.bak` files to `.bak` and move temp children into `folder` (`os.replace`), then remove the temp dir. Legacy fallback on `TarError` writes raw `<name>.state` as before (extract failed before any rename, so nothing is lost). RAW branch unchanged order (backup then write).
  - Files: src/server/sync_client.py
  - Reuses: `_extract_tar_to_tmp`
  - New: none
- [ ] 6. `_merge_extract_state_folder`: extract to temp, then for each file under temp (`rglob`) compute `rel`, `dest = folder / rel`; if `dest` exists `os.replace(dest, dest + ".bak")`; `dest.parent.mkdir`; `os.replace(src, dest)`. Backup path now equals the written path (fixes subfolder members), and `../` members are rejected by `_safe_extract_tar` before any backup. Remove the inner `_merge` closure.
  - Files: src/server/sync_client.py
  - Reuses: `_extract_tar_to_tmp`
  - New: none
- [ ] 7. Electron `window.ts` (main process only, no IPC): add `const openSafe = (u) => { if (/^https?:\/\//i.test(u)) shell.openExternal(u); }` used by `setWindowOpenHandler`; add `webContents.on("will-navigate", (e, url) => { if (url !== webContents.getURL()) { e.preventDefault(); openSafe(url); } })` (allow reload/same-document, block everything else; dev server and `file://` index are loaded via `loadURL/loadFile`, which do not fire will-navigate).
  - Files: src/gui/electron/window.ts
  - Reuses: existing `setWindowOpenHandler`
  - New: tiny inline `openSafe` - the same check is needed in two handlers.
- [ ] 8. Tests: new `src/tests/test_restore_safety.py` (real FS; API cases use conftest `client`/`AUTH`/`make_client`). Cases listed in ## Testing.
  - Reuses: conftest.py client fixtures, test_memcard_folder_sync.py `_make_folder_card`/`memcard_bytes` pattern
  - New: one test file - restore helpers have no dedicated safety tests; kept separate from the memcard pack tests to stay small
- [ ] 9. Docs: add a GOTCHAS.md entry (CORS decision, temp-extract-then-swap restores, merge backup by relative path) and one line in CLAUDE.md Rules (Saves / sync).

## Testing
- **Test File**: src/tests/test_restore_safety.py
- **Test Cases**:
  - cors_allowed_origin: async `client` OPTIONS `/health` (or any route) with `Origin: null` and `Origin: http://localhost:5173` + `Access-Control-Request-Method: GET` returns `access-control-allow-origin` echoing the origin.
  - cors_foreign_origin: `Origin: https://evil.example` preflight has no `access-control-allow-origin` header.
  - pin_constant_time: correct PIN accepted, wrong PIN 401/403 via existing `AUTH`; non-ASCII PIN header does not 500.
  - memcard_restore_failure_keeps_card: `_write_memcard_tar_bytes(card, corrupt_tar)` raises `tarfile.TarError`, card folder content unchanged, no `.emusync-*` temp dirs left, no empty card.
  - memcard_restore_success_backs_up: valid tar replaces folder, `<card>.bak` holds old tree (covered by existing test; add file-card to folder-card case).
  - state_extract_failure_no_rename: `_extract_state_folder` with an enveloped corrupt tar.gz leaves existing state files and creates no `.bak`.
  - state_extract_success: files replaced, previous ones in `.bak`.
  - merge_backup_subfolder: shared folder with `sub/a.state`; merging an archive containing `sub/a.state` leaves `sub/a.state.bak` with old content, new content in place; untouched siblings unchanged.
  - merge_traversal_rejected: archive with `../x` raises/ignores before any `.bak` is made.
- **Edge Cases**:
  - Legacy (un-enveloped) raw state blob still written as `<Folder>.state`.
  - Legacy raw-file memcard fallback (`_write_memcard` with non-tar bytes) still works (existing test must keep passing).
  - Existing `.bak` is overwritten, not accumulated.
- **Integration Points**:
  - `_write_memcard` TarError fallback to `_write_memcard_raw_bytes` depends on step 4 still raising TarError.
  - `run`/pull-state callers of these helpers unchanged in signature.
  - window.ts: no automated harness; manual check (external https link opens, `javascript:`/`file:` ignored, in-app navigation blocked), tsc.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Requiring a PIN on blank-PIN servers; hashing/envelope changes; renderer CSP; the `_write_memcard_raw_bytes` path (single file, already backs up before write).

## Log
