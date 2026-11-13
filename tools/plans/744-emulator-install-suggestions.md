# Plan: #744 Link emulator suggestions and install missing RetroArch cores from the import wizard

Issue: #744
Branch: feature/744-emulator-install-suggestions
PR: #746
Status: implementing
Fix attempts: 0

## Goal
The import wizard's "No compatible emulator found" state links every suggestion to a download page and, on Linux x86_64 with RetroArch detected, installs a missing libretro core in one click and re-runs detection.

## Design Alignment
- **Visual Pattern**: Reuses the existing empty state in `EmulatorStep.tsx` (centered icon, muted 13px text, 12px left-aligned list). Suggestions become `<a target="_blank">` links (no new IPC: `window.ts` `setWindowOpenHandler` already sends http(s) to `shell.openExternal`). Core installs render as list rows, each "core name + `btn btn-ghost` Install" (same row shape as the guide's list editors); the busy state is `<span className="spinner" />` inside the button; errors are inline 12px danger text under the list.
- **Recommendations**: Add one guide line under Layout, "Empty state with actions", describing link + install rows.

## Steps
- [x] 1. Detection returns install targets. Export `coreInstallTargets(home, consoleKey)` from `detect.ts`: on `process.platform === "linux" && process.arch === "x64"`, return `{ retroarch: [{ type, label, coresDir }], cores: [{ lib, folder }] }`, built from `detectRetroArch(home)` and the console's `systemKeys` -> `rt.cachedSystemDefs[sys].cores` (dedupe by lib). Otherwise return empty arrays. `emulator:detect` adds an `install` field holding this value.
  - Files: src/gui/electron/emulator/detect.ts, src/gui/electron/emulator/ipc.ts
  - Reuses: detect.ts:detectRetroArch, the core-list walk already used in detectEmulatorsForConsole
  - New: small exported fn. Nothing existing returns RetroArch targets without an installed core.
- [x] 2. Core installer. New `src/gui/electron/emulator/installCore.ts` exporting `installCore(home, consoleKey, coresDir, lib)`. It validates that `lib` and `coresDir` both appear in `coreInstallTargets(home, consoleKey)` (trust boundary: renderer input), downloads `https://buildbot.libretro.com/nightly/linux/x86_64/latest/<lib>.so.zip` into a fresh `mkdtemp` dir, extracts it with `execFile(PYTHON, ["-m", "zipfile", "-e", zip, tmp])`, checks that `<lib>.so` exists with size > 0, then `mkdirSync(coresDir, recursive)`, `copyFileSync` to `<coresDir>/<lib>.so.part` and `renameSync` to `<lib>.so`. The temp dir is always removed in `finally`. Returns `{ ok: true } | { ok: false, error }`. IPC `emulator:installCore` registered in ipc.ts.
  - Files: src/gui/electron/emulator/installCore.ts (new), src/gui/electron/emulator/ipc.ts
  - Reuses: art.ts:download (https to `.tmp` + rename), runtime.ts:PYTHON (stdlib zipfile; adm-zip was removed in #679), coreInstallTargets from step 1
  - New: installCore.ts. No existing zip-extract or core-install code; it gets its own module to keep ipc.ts small.
- [x] 3. Preload + types. Add `emulator.installCore(consoleKey, coresDir, lib)` to preload.ts and emusync.d.ts. Extend the `detect` return type with `install: { retroarch: {type,label,coresDir}[]; cores: {lib,folder}[] }`.
  - Files: src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: existing `emulator` preload namespace
- [x] 4. Wizard state. `useConsoleImport.ts` stores `install` from both detect calls (initial auto-detect and `detectEmulators`), resets it on `backToConsole`, and exposes `installCore(coresDir, lib)`. That function calls the IPC and, on ok, calls `detectEmulators()` so the wizard advances; on failure it returns the error.
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: detectEmulators, existing setSuggestions pattern
- [x] 5. Empty-state UI. In `EmulatorStep.tsx`, map each suggestion to a URL via a small keyword table (`RetroArch`, `mGBA`, `Dolphin`, `PCSX2`, `PPSSPP`, `Azahar`, `Eden`, `melonDS`, `Flycast`; first matching standalone keyword wins, else RetroArch) and render it as a link. When `install.retroarch` is non-empty, render an "Install a core" list: one row per core x RetroArch target (label includes "(Flatpak)" when there are two targets), each with an Install button, a per-row spinner and an inline error. When RetroArch is absent, show only the links.
  - Files: src/gui/renderer/src/components/console-import/EmulatorStep.tsx
  - Reuses: existing empty-state markup, `btn btn-ghost`, `spinner` class, window open handler
  - New: URL table. Suggestions are free-text strings in `console_defs` and changing that schema just for links is not worth it.
- [x] 6. Tests: new `src/tests/test_emulator_suggestions.py`: (a) every `suggestions` entry in `_IMPORT_CONSOLES` contains at least one keyword from the `SUGGESTION_LINKS` table in EmulatorStep.tsx (source read as text, as in test_paths.py:122); (b) every `_IMPORT_SYSTEMS` core `lib` matches `^[a-z0-9_-]+_libretro$` (the buildbot URL and the installCore validation depend on it). Then `make lint`, both `tsc` projects (no new errors beyond the known list), and the manual script in Testing.
  - Files: src/tests/test_emulator_suggestions.py (new)
  - Reuses: test_paths.py source-read pattern, `cli.consoles_data` imports as in test_core_detection.py
  - New: test file. No existing test covers suggestions or core lib naming.
- [x] 7. Docs: ARCHITECTURE.md (new IPC `emulator:installCore`, detect `install` field, installCore.ts module); CLAUDE.md GUI rule line (core install: Linux x86_64 buildbot, validated against detected targets, `.part` + rename, zip via Python stdlib); design guide line from Design Alignment.
  - Files: src/docs/ARCHITECTURE.md, CLAUDE.md, .claude/frontend-design-guide.md

## Review fix
- [ ] R1. installCore downloads with `fetch` + `AbortSignal.timeout(120_000)` and writes the body with `writeFileSync`, replacing `art.ts:download` (no timeout, Node https.get; GOTCHAS: main process uses fetch). Non-OK status throws `HTTP <code>`.
  - Files: src/gui/electron/emulator/installCore.ts
  - Reuses: fetch + AbortSignal.timeout pattern from art.ts:168

## Testing
- **Test File**: src/tests/test_emulator_suggestions.py (+ manual script; no JS runner exists, per testing guide)
- **Test Cases**:
  - suggestion_links_cover_all_suggestions: every console suggestion maps to a link keyword in EmulatorStep.tsx
  - core_libs_are_buildbot_safe: every seeded core lib matches `^[a-z0-9_-]+_libretro$`
- **Manual script** (Linux x86_64, dev GUI against dev server):
  1. Move `snes9x_libretro.so` (and any other SNES core) out of the RetroArch cores dir. Import SNES: the empty state shows a RetroArch link plus one Install row per seeded SNES core.
  2. Click the RetroArch link: it opens in the system browser and the app does not navigate.
  3. Install Snes9x: spinner, then the wizard advances to emulator selection with "RetroArch · Snes9x". `<coresDir>/snes9x_libretro.so` exists and no `.part` file is left.
  4. Disconnect the network and install another core: an inline error appears, no file is added to the cores dir, and the mkdtemp dir is removed.
  5. Import PS2 with PCSX2 absent: a PCSX2 link only, no install rows.
  6. With Flatpak RetroArch also installed: rows are labeled per target, and the install lands in the Flatpak cores dir.
- **Edge Cases**:
  - Renderer sends an arbitrary lib or coresDir: rejected by installCore validation against coreInstallTargets.
  - HTTP 404 from buildbot (core not built for the platform): error shown, nothing written.
  - Cores dir missing: created with mkdirSync recursive.
- **Integration Points**:
  - `emulator:detect` consumers: the initial auto-detect and `detectEmulators` in useConsoleImport both read the new `install` field.
  - `art.ts:download` is shared with artwork fetches and stays unchanged.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (`emulator:installCore`). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Windows / non-x86_64 core install: GUI RetroArch detection is Linux-only and `.so`-only, so an installed `.dll` would not be detected. Links only. Needs Windows RetroArch detection first.
- Fetching `.info` files: seeded cores are detected by `.so` name alone (`findInstalledCores`), so `.info` is not needed.
- Standalone emulator install: #745.

## Log
Step 5: SUGGESTION_LINKS keyed by the suggestion's first word (every suggestion starts with its download target), not substring keyword search; PPSSPP/melonDS/Flycast entries dropped since they only appear as RetroArch cores.
Step 6: core lib regex allows hyphens (mesen-s_libretro is a real buildbot name). Verified the buildbot zip extracts to <lib>.so at root via python -m zipfile.
Step 7: CLAUDE.md rule line landed with step 3 (commit hook required it alongside preload.ts).
