---
name: verify
description: Project-specific setup notes for driving the EmuSync Electron GUI in an isolated instance to verify a renderer/electron change end-to-end. Use as a supplement to the general verify skill when the change touches gui/.
---

# EmuSync GUI verify — environment notes

Two real environment gaps hit on a fresh worktree, worth fixing before attempting to drive the app:

## 1. A fresh `npm install` (via `bash install.sh`) does NOT give you a runnable Electron

npm's `install-scripts` safety gate blocks `electron`'s and `esbuild`'s postinstall scripts by default (`npm warn install-scripts ... blocked because they are not covered by allowScripts`). Without them, `node_modules/electron/dist/` has no binary and `require('electron')` throws `Error: Electron uninstall`.

Fix, in `gui/`:
```bash
npm install-scripts approve electron esbuild
npm rebuild electron esbuild   # often insufficient by itself — see below
```
If `node_modules/electron/path.txt` still doesn't exist after that, the postinstall script itself may silently no-op. Extract manually from npm's electron download cache (usually already warm from a prior install elsewhere on the machine):
```bash
find ~/.cache/electron -iname "electron-v<version>-linux-x64.zip"   # match node_modules/electron/package.json's version
unzip -o -q <that zip> -d node_modules/electron/dist
printf 'electron' > node_modules/electron/path.txt   # relative filename ONLY, not a path — index.js does path.join(__dirname, 'dist', <this content>)
chmod +x node_modules/electron/dist/electron
```
As of issue #410 this repo's `gui/package.json` now has an `allowScripts` block pre-approving both packages, so a fresh `npm install` should no longer hit this at all — if you still do, the lockfile/package.json drifted.

## 2. The npm-downloaded Electron's bundled Node throws on the `steamgriddb` ESM package

`electron-vite dev`'s built main bundle does `require("steamgriddb")` (a CJS `require`), which is an ESM-only package. Electron's *newer* bundled Node versions tolerate this; the npm-downloaded Electron pinned in `package.json` (31.7.7 as of this writing, bundling Node 20.18) does not — crashes with `Error [ERR_REQUIRE_ESM]`.

The Makefile's `dev-gui` target already documents the intended fix — a system-installed newer Electron:
```makefile
dev-gui:
	cd gui && npm run dev || (test -x /usr/lib/electron/electron && ELECTRON_EXEC_PATH=/usr/lib/electron/electron npm run dev)
```
**Update (#411):** `ELECTRON_EXEC_PATH=/usr/lib/electron/electron` (prefixed inline on `npx electron-vite dev`, no export needed) *does* get read by electron-vite's own `getElectronPath()` and it correctly spawns the system binary — the earlier "not honored" finding was a red herring, likely from testing it against `node_modules/electron/index.js`'s CJS shim (which wants `ELECTRON_OVERRIDE_DIST_PATH`, a different var, and only matters if something separately `require('electron')`s the npm package directly).

New blocker hit past that point: with the system Electron spawned as the process (confirmed via `ps`), the app's own main-process bundle's `require('electron')` resolved to the npm package's JS shim (`node_modules/electron/index.js`, which then throws `Electron failed to install correctly` since the npm package's `dist/` was never populated) instead of Electron's built-in native binding. Normally Electron's module loader intercepts the bare `'electron'` specifier and returns the native API regardless of `node_modules` contents — that interception didn't happen here. Untested hypotheses: version skew (system package reports `v24.18.0`, app pinned to `^31.7.7` — `require('electron')` interception may be conditional on a matching or newer major), or something about how `spawn()` invokes the binary (env/argv) suppresses Electron's normal bootstrap and it fell through to plain Node module resolution. Didn't chase further — out of scope for a one-line IPC-call swap; worth revisiting with a version-matched system Electron (or a properly populated npm `node_modules/electron/dist/`) before the next GUI-heavy change.

## Isolating from a live dev session

Never point a second `electron-vite dev` at the running instance's profile — use a dedicated `--user-data-dir` (e.g. `/tmp/emusync-verify-userdata`) and a separate `DISPLAY` via `Xvfb :N -screen 0 1280x800x24 &` so it can't collide with (or visibly disrupt) a GUI session the user has open. The real EmuSync server on :8765 is safe to point an isolated instance at — reads are non-destructive.

## Driving/observing without a screenshot pipeline

No Playwright/CDP client is wired into this repo. `--remote-debugging-port=<port>` gets you a CDP HTTP endpoint (`curl http://localhost:<port>/json` lists targets), but `Runtime.evaluate`/`Page.captureScreenshot` need a WebSocket client — none of `websocket-client` (pip), `ws` (npm), or `websocat` are installed in this environment as of writing. Either install one of those first, or fall back to on-disk evidence: Electron's `localStorage` backs onto `<user-data-dir>/Local Storage/leveldb/*.log`/`*.ldb`, greppable for known keys/values as weaker but real evidence that a code path executed.

## Status as of issue #410

Blocked on the ESM/Node-version issue (point 2) before reaching a driveable app within a reasonable timebox. If you get further than this, replace this section with what worked.
