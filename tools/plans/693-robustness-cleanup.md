# Plan: #693 Clean up upload failure, mod validation, lock release and log sanitization

Issue: #693
Branch: feature/693-robustness-cleanup
PR: #695
Status: implementing
Fix attempts: 0

## Goal
Fix five low-severity robustness/hygiene defects (staging leak, unvalidated mod path, lock release retry, log forging, tracked build artifacts) with the smallest backend diff.

## Design Alignment
- **Backend Pattern**: validation lives at the API boundary as `HTTPException(400)` (as in transfers.py header checks); shared helpers live in `server/api/_core.py` next to `_remove_staging_dir`; CLI keeps `click.echo(..., err=True)` warnings.
- **Recommendations**: none. No schema, config, IPC or CLI change.

## Steps
- [x] 1. Staging cleanup + size cap on ROM upload: in `upload_rom_transfer` wrap the write loop in `try/except BaseException`, call `_remove_staging_dir(str(staged_path))` and re-raise; count bytes and raise 413 once over `_MAX_UPLOAD_BYTES` (module constant, 64 GiB, ponytail: fixed ceiling, make it a Config field if users hit it).
  - Files: src/server/api/transfers.py
  - Reuses: src/server/api/_core.py:_remove_staging_dir (already guards to dirs directly under the staging root)
  - New: `_MAX_UPLOAD_BYTES` constant - no existing upload limit to reuse.
- [x] 2. Safe path segment helper + mod validation: add `_safe_segment(value, what) -> str` to `_core.py` (400 if empty, `.`/`..`, contains `/`, `\`, NUL or any control char, or length > 255). Call it on `title_id` and `mod_name` in all three routes of `mods.py` (list/pull/push), before any store call. Validate before the upload body is streamed in push.
  - Files: src/server/api/_core.py, src/server/api/mods.py
  - Reuses: HTTPException pattern in _core/transfers; store untouched (boundary validation per issue)
  - New: `_safe_segment` - nothing existing validates path segments; it is a few lines and used 3x.
- [x] 3. Sanitize device name: add `_clean_header(value) -> str` in `_core.py` (drop non-printable chars incl. `\r\n`, strip, cap 64 chars). In `_auth` apply it to `x_device_name` (and `x_device_id`) before `ensure_device`, falling back to the id when the result is empty. Because `_device_names` and all `_print_activity` labels come from `device.name`, this covers log output and stored names.
  - Files: src/server/api/_core.py
  - Reuses: `_auth` existing `x_device_name or x_device_id` fallback
  - New: `_clean_header` - one-liner using `str.isprintable`; no existing sanitizer.
- [x] 4. Lock release retry: in `run.py:_release` try `client.release_lock` up to 2 attempts; set `lock_released = True` only on success; if both fail, warn on stderr (existing message) and leave the flag False so a later `_release()` call (finally/signal path) retries.
  - Files: src/cli/run.py
  - Reuses: existing `_release` closure and warning text
  - New: none (loop inside existing function)
- [x] 5. Repo hygiene: `git rm --cached src/gui/tsconfig.node.tsbuildinfo src/gui/tsconfig.web.tsbuildinfo` (they are tracked), add `*.tsbuildinfo` and the root-level `/emusync` wrapper to `.gitignore`.
  - Files: .gitignore, the two tsbuildinfo files (untrack only)
  - Reuses: existing "Build artifacts" sections of .gitignore
  - New: none. (`/emusync` is anchored so `src/emusync.py` and `src/emusync` launcher paths are unaffected; verify with `git check-ignore`.)
- [x] 6. Tests (see Testing). No mocks, real SQLite.
- [x] 7. Docs: CLAUDE.md one-line rule on `_safe_segment`/`_clean_header`; docs/GOTCHAS.md short note; ARCHITECTURE.md none needed (no route/IPC/config change).

## Testing
- New `src/tests/test_hardening_693.py` using the `client`/`AUTH` fixtures from test_integration.py.
- Upload failure: monkeypatch-free approach: POST rom-transfer with a body that exceeds a lowered `transfers._MAX_UPLOAD_BYTES` (set via attribute assignment in the test), assert 413 and `rom_staging` has no leftover subdir. Under-cap upload still succeeds (regression).
- Mods: parametrize title_id/mod_name in (`..`, `.`, `a%2Fb` encoded slash, `a%5Cb`, `%00`, `x%0Ay`) on GET list, GET pull, POST push -> 400; valid `0100000000010000` / `My Mod` push then list/pull -> 200 and blob is under `blobs/switch_mods/<title_id>/`.
- Sanitization: request with `X-Device-Name: "evil\r\nfake line"` -> stored device name has no control chars (via GET /devices); capsys-captured activity line is single line; empty-after-clean name falls back to device id; 64-char cap.
- Lock release: `src/tests/test_lock_release_retry.py` (or in the above file) drive a stub `SyncClient` subclass whose `release_lock` fails once -> called twice, succeeds. Needs `_release` reachable: if the closure is not testable, extract nothing and instead run `run` through existing patterns in test_locks.py/test_lock_heartbeat_interval.py; fall back to asserting via CliRunner with a real local server.
- Hygiene: `git ls-files` contains no tsbuildinfo (manual check).

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no (.gitignore only).

## Not in this plan
- Size cap on mod uploads; configurable upload cap; store-level path validation; hex-only title_id enforcement (title IDs may be discovered by name, #448).

## Conflicts with #691 / #692
- #691 edits the filename handling in `transfers.py` (same function and lines as step 1) and `_monitor_presence` in `_core.py`; textual conflict likely in `upload_rom_transfer`. Land #691 first or rebase; step 1 should wrap whatever staging-path construction #691 leaves.
- #692 edits `_core.py` PIN compare and CORS (top of file / start of `_auth`) and `sync_client.py`; step 3 edits later lines of `_auth`, so likely a clean or trivial merge. No overlap with `sync_client.py`.

## Log
Step 6: lock-release retry test omitted (closure inside run command not reachable without a full run harness); encoded-slash mod names return 404 (route does not match) rather than 400, both safe.
