# Plan: #741 Rebuild runtime venv when system Python version changes

Issue: #741
Branch: feature/741-runtime-venv-python-version
PR: none
Status: planned
Fix attempts: 0

## Goal
A venv that can no longer import its dependencies (system Python minor upgrade) is rebuilt automatically by both `ensureRuntime()` and the `src/emusync` launcher, and the launcher never silently falls back to bare `python3` when a venv exists.

## Design Alignment
- **Backend Pattern**: The runtime dir keeps the checkout layout (GOTCHAS #677: no second layout). Staleness is detected by probing the venv interpreter with the same import list `server:preflight` already uses (`fastapi, uvicorn, click, tomlkit, zeroconf, httpx`), instead of a new Python-version stamp file. Rationale: the probe tests the actual failure (deps not importable under the interpreter the symlink now points at), covers version and path changes and half-installed venvs, and adds no state to keep in sync. This satisfies acceptance criterion 1 in spirit; recorded as a deliberate deviation.
- **Recommendations**: Add a GOTCHAS line: the venv's `bin/python` symlinks to the system interpreter, so a minor upgrade orphans `lib/pythonX.Y/site-packages`; rebuild via `venv --clear`, never patch paths.

## Steps
- [ ] 1. `src/emusync` launcher: for the first existing venv dir (`-x $v/bin/python`), probe `"$v/bin/python" -c 'import fastapi, uvicorn, click, tomlkit, zeroconf, httpx'` (stderr discarded). Probe ok: exec as today. Probe fails: print `EmuSync: Python environment at $v is unusable (system Python changed?), rebuilding...` to stderr, run `python3 -m venv --clear "$v" && "$v/bin/python" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"`, re-probe, exec on success. On failure print a clear error (venv path, `python3 --version`, hint: needs network/python3-venv) and `exit 1`. The bare `exec python3` fallback stays only when no venv dir exists at all.
  - Files: src/emusync
  - Reuses: existing venv search loop; import list from src/gui/electron/server.ts `server:preflight`; `requirements.txt` already bundled next to the launcher (test_bundle.py `test_bundle_includes_entrypoints`).
  - New: probe + rebuild block (~12 lines bash). Nothing existing runs outside Electron, and Steam shortcuts invoke this launcher directly.
  - `# ponytail:` comment: no lock around the rebuild; two concurrent launches (or GUI + Steam) could race. Add `flock` on `$v.lock` if that is ever seen.
- [ ] 2. `src/gui/electron/runtimeSetup.ts` `provision()`: when `VENV_PYTHON` exists, run the same import probe via the existing `run()` helper; if it fails, `rmSync(VENV, { recursive: true, force: true })` and remove `HASH_STAMP`, so the existing create + pip path rebuilds it. Hoist the import list to one exported const in `runtime.ts` (`PY_DEPS_PROBE`) and use it in both `runtimeSetup.ts` and `server.ts` `server:preflight`.
  - Files: src/gui/electron/runtimeSetup.ts, src/gui/electron/runtime.ts, src/gui/electron/server.ts
  - Reuses: `run()`, existing venv create + pip install + stamp flow, failure-writes-no-stamp retry semantics.
  - New: one const + a 3-line probe branch. Covers GUI Play, which spawns `PYTHON` directly and relies on `ensureRuntime()` at startup (sync daemon / server start).
- [ ] 3. Tests: `src/tests/test_launcher.py` (new; bash launcher has no existing test). Build a temp layout `tmp/src/{emusync,emusync.py,requirements.txt}` + `tmp/.cache/.venv/bin/python`, with `emusync.py` printing a marker. Cases: (a) healthy venv (`bin/python` = small script exec'ing `sys.executable`, which has the deps) -> marker printed, exit 0; (b) broken venv (`bin/python` exits 1 on the probe) and `python3` on PATH a stub whose `-m venv` fails -> exit 1, stderr names the venv, marker NOT printed (no silent bare-python3 fallback); (c) no venv dir -> falls back to `python3` from PATH (stub runs the script) as before. Skip on Windows. No mocks of app logic; process-level stubs only, no SQLite involved.
  - Files: src/tests/test_launcher.py
  - Reuses: pytest `tmp_path`, `subprocess`.
  - New: test file, nothing existing covers the launcher. TS probe branch is not unit-testable (no TS test harness); noted in PR.
- [ ] 4. Docs: src/docs/GOTCHAS.md "AppImage runtime (#677)" section: add the Python-upgrade line and the launcher self-heal/no-silent-fallback rule (#741). src/docs/ARCHITECTURE.md line ~194: mention the import probe as a venv staleness trigger. CLAUDE.md Ops AppImage bullet: append "a venv that fails the dependency import probe is rebuilt by `ensureRuntime()` and the `src/emusync` launcher (#741)".
  - Files: src/docs/GOTCHAS.md, src/docs/ARCHITECTURE.md, CLAUDE.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Bundling a Python interpreter (GOTCHAS: not covered).
- Windows launcher (system python, no bootstrap).
- A Python-version stamp file (replaced by the import probe, see Design Alignment).

## Log
- 2026-11-16 bplan: plan written
