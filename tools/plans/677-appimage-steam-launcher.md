# Plan: #677 Let the AppImage add Steam shortcuts without EMUSYNC_SCRIPT

Issue: #677
Branch: feature/677-appimage-steam-launcher
PR: none
Status: implementing
Fix attempts: 0

## Goal
Ship the Python CLI inside the AppImage and run it from a stable per-user runtime directory with the same layout as a dev checkout, so Steam shortcuts, the server, the sync daemon and `run <slug>` all work with no repo and no env var.

## Debt-avoidance decisions
- One layout: `<cacheDir>/runtime/src/...` plus `<cacheDir>/runtime/.cache/.venv`, identical to a checkout. The existing `src/emusync` wrapper, `PYTHON` venv lookup and `pkill -f "src/emusync.py server start"` need no change and no second code path.
- `SCRIPT`, `PYTHON` and `LAUNCHER` stay module constants in runtime.ts, computed from a deterministic path. No picker, no repoPath setting, no directory-guessing list (the earlier #677 draft), and the #676 `LAUNCHER_STABLE` guard is deleted.
- Python interpreter is resolved in exactly one function (`PYTHON` in runtime.ts, plus the venv-creation call in the bootstrap). Swapping to a bundled interpreter later (python-build-standalone) changes only those two spots.
- Runtime and test dependencies are split so the AppImage never installs pytest, and CI/install.sh stay one-line changes.
- A Python test fails the build when a new top-level package under `src/` is not bundled, so the bundle list cannot silently rot.

## Design Alignment
- **Visual Pattern**: no new UI. Bootstrap failures surface through the existing Setup `preflightError` text and the `{ ok, error }` result of `steam:addGame`.
- **Recommendations**: none.

## Steps
- [x] 1. Split dependencies: `src/requirements.txt` keeps runtime packages only; new `src/requirements-dev.txt` is `-r requirements.txt` plus pytest, pytest-asyncio. Point `install.sh`, `Makefile` install, `.github/workflows/ci.yml` and the release.yml test job at requirements-dev.txt; check `.githooks/pre-commit` for a hard-coded reference.
  - Files: src/requirements.txt, src/requirements-dev.txt, install.sh, Makefile, .github/workflows/ci.yml, .github/workflows/release.yml, .githooks/pre-commit (if needed)
  - Reuses: existing install paths
  - New: requirements-dev.txt - the test deps currently sit in the same file, and the runtime venv must not install them.
- [x] 2. Bundle the CLI: add `build.extraResources` copying `emusync.py`, `emusync`, `requirements.txt`, `cli/**`, `server/**`, `shared/**` from `..` to `src`, excluding `__pycache__`, tests, gui, docs, scripts. Files land in `<resources>/src/`.
  - Files: src/gui/package.json
  - Reuses: electron-builder `extraResources`
  - New: none
- [x] 3. Runtime paths in runtime.ts: when `EMUSYNC_SCRIPT` is unset and the app is a packaged Linux AppImage (`app.isPackaged` and `process.env.APPIMAGE`), `RUNTIME_DIR = join(cacheDir(), "runtime")`, `SCRIPT = RUNTIME_DIR/src/emusync.py`, and `PYTHON` checks `RUNTIME_DIR/.cache/.venv/bin/python` through the existing venv lookup (it already derives from `dirname(SCRIPT)/../.cache/.venv`). Otherwise unchanged. Delete `LAUNCHER_STABLE`.
  - Files: src/gui/electron/runtime.ts
  - Reuses: runtime.ts:SCRIPT/PYTHON/LAUNCHER, paths.ts:cacheDir
  - New: RUNTIME_DIR constant - the bootstrap and the paths must agree on one directory.
- [x] 4. New `runtimeSetup.ts` with `ensureRuntime(): Promise<{ ok: boolean; error?: string }>`, a no-op returning ok when not a packaged AppImage. Steps: (a) if `RUNTIME_DIR/.version` differs from `app.getVersion()`, remove `RUNTIME_DIR/src`, `fs.cpSync` from `process.resourcesPath/src`, mark the wrapper executable, write `.version`; (b) if `RUNTIME_DIR/.requirements-hash` differs from the SHA-256 of the copied requirements.txt or the venv python is missing, run `python3 -m venv RUNTIME_DIR/.cache/.venv` then `pip install -r requirements.txt`, then write the hash; (c) memoize the in-flight promise so concurrent callers share one run; (d) failures return a readable error (python3 missing, venv module missing with the apt hint from install.sh, pip/network failure with its last stderr line) and never leave a stamp, so the next call retries.
  - Files: src/gui/electron/runtimeSetup.ts
  - Reuses: runtime.ts constants, files.ts/server.ts spawn patterns, install.sh error wording
  - New: runtimeSetup.ts - no existing module copies or provisions anything at startup.
- [x] 5. Wire it in: `server:start` and `daemon` start await `ensureRuntime()` and return `{ ok:false, error }` on failure (reusing the #534 early-exit shape); `server:preflight` awaits it first and returns its error; `steam:addGame` awaits it and returns its error before touching shortcuts.vdf; remove the #676 LAUNCHER_STABLE branch and message in steam.ts.
  - Files: src/gui/electron/server.ts, src/gui/electron/steam.ts
  - Reuses: server.ts start/preflight handlers, steam.ts `{ ok, error }` returns
  - New: none
- [x] 6. Guard tests (Python, no mocks): `src/tests/test_bundle.py` (a) loads `src/gui/package.json` and asserts every directory under `src/` that contains `.py` files, except the explicit exclude list (gui, tests, scripts, docs), is covered by an `extraResources` filter, and `emusync.py`/`emusync`/`requirements.txt` are present; (b) asserts `requirements.txt` contains no pytest entries and `requirements-dev.txt` includes it.
  - Files: src/tests/test_bundle.py
  - Reuses: existing pytest setup (`Path(__file__)` repo-root pattern from test_launcher_wrapper_finds_a_python)
  - New: one test file - nothing existing checks the bundle config.
- [x] 7. Release smoke check: after `Build AppImage` in release.yml, extract the AppImage (`--appimage-extract`) and fail if `squashfs-root/resources/src/emusync.py` is missing.
  - Files: .github/workflows/release.yml
  - Reuses: existing build step
  - New: one workflow step - the only place the packaged layout is observable.
- [ ] 8. Docs: CLAUDE.md (replace the #675 Steam rule with the runtime-dir design, deps split, no EMUSYNC_SCRIPT needed), src/docs/ARCHITECTURE.md (runtime dir, bootstrap lifecycle, data paths), GOTCHAS.md (read-only mount, cacheDir wipe self-heals on next launch, first-run needs system python3 + venv + network).
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md, src/docs/GOTCHAS.md

## Testing
- **Test File**: src/tests/test_bundle.py (Python); electron code has no harness, covered by a manual build.
- **Test Cases**:
  - Bundle covers every Python package under src/ except the exclude list.
  - requirements.txt has no test packages; requirements-dev.txt includes it.
  - Manual, built AppImage on a machine with no repo: first launch provisions the runtime; Add to Steam creates a shortcut targeting `<cacheDir>/runtime/src/emusync`; the shortcut launches a game after the app is closed.
  - Manual: second launch skips copy and pip; bumping the app version recopies but keeps the venv.
- **Edge Cases**:
  - python3 or venv module missing, or offline: preflight and addGame show the error, retry succeeds once fixed, no stamp written on failure.
  - Cache dir wiped: next app start re-provisions; the shortcut works again.
  - Two callers at once (server start and preflight): one bootstrap run.
  - Dev checkout, EMUSYNC_SCRIPT set, and Windows packaged: `ensureRuntime` is a no-op, behavior unchanged.
- **Integration Points**: `make test-changed` and `make test`; electron-vite build; release.yml smoke step.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (new `<cacheDir>/runtime/` tree and stamp files; requirements split).

## Not in this plan
Bundling a Python interpreter; Windows bootstrap or Windows Steam shortcuts; a progress UI for first-run pip install; macOS.

## Log
Step 3: also removed the #676 LAUNCHER_STABLE guard from steam.ts here (the constant is gone), and PYTHON points at the runtime venv unconditionally when USE_RUNTIME_DIR so it is correct after the first-run bootstrap. Step 5 still awaits ensureRuntime in addGame.
