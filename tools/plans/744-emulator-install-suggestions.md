# Plan: #744 Link emulator suggestions and install missing RetroArch cores from the import wizard

Issue: #744
Branch: feature/744-emulator-install-suggestions
PR: none
Status: planned
Fix attempts: 0

## Goal
The import wizard's "No compatible emulator found" state links every suggestion to a download page and, on Linux x86_64 with RetroArch detected, installs a missing libretro core in one click and re-runs detection.

## Design Alignment
- **Visual Pattern**: Reuses the existing empty state in `EmulatorStep.tsx` (centered icon, muted 13px text, 12px left-aligned list). Suggestions become `<a target="_blank">` links (no new IPC: `window.ts` `setWindowOpenHandler` already sends http(s) to `shell.openExternal`). Core installs render as list rows, each "core name + `btn btn-ghost` Install" (same row shape as the guide's list editors); the busy state is `<span className="spinner" />` inside the button; errors are inline 12px danger text under the list.
- **Recommendations**: Add one guide line under Layout, "Empty state with actions", describing link + install rows.

## Steps
- [ ] 1. Detection returns install targets. Export `coreInstallTargets(home, consoleKey)` from `detect.ts`: on `process.platform === "linux" && process.arch === "x64"`, return `{ retroarch: [{ type, label, coresDir }], cores: [{ lib, folder }] }`, built from `detectRetroArch(home)` and the console's `systemKeys` -> `rt.cachedSystemDefs[sys].cores` (dedupe by lib). Otherwise return empty arrays. `emulator:detect` adds an `install` field holding this value.
  - Files: src/gui/electron/emulator/detect.ts, src/gui/electron/emulator/ipc.ts
  - Reuses: detect.ts:detectRetroArch, the core-list walk already used in detectEmulatorsForConsole
  - New: small exported fn. Nothing existing returns RetroArch targets without an installed core.
- [ ] 2. Core installer. New `src/gui/electron/emulator/installCore.ts` exporting `installCore(home, consoleKey, coresDir, lib)`. It validates that `lib` and `coresDir` both appear in `coreInstallTargets(home, consoleKey)` (trust boundary: renderer input), downloads `https://buildbot.libretro.com/nightly/linux/x86_64/latest/<lib>.so.zip` into a fresh `mkdtemp` dir, extracts it with `execFile(PYTHON, ["-m", "zipfile", "-e", zip, tmp])`, checks that `<lib>.so` exists with size > 0, then `mkdirSync(coresDir, recursive)`, `copyFileSync` to `<coresDir>/<lib>.so.part` and `renameSync` to `<lib>.so`. The temp dir is always removed in `finally`. Returns `{ ok: true } | { ok: false, error }`. IPC `emulator:installCore` registered in ipc.ts.
  - Files: src/gui/electron/emulator/installCore.ts (new), src/gui/electron/emulator/ipc.ts
  - Reuses: art.ts:download (https to `.tmp` + rename), runtime.ts:PYTHON (stdlib zipfile; adm-zip was removed in #679), coreInstallTargets from step 1
  - New: installCore.ts. No existing zip-extract or core-install code; it gets its own module to keep ipc.ts small.
- [ ] 3. Preload + types. Add `emulator.installCore(consoleKey, coresDir, lib)` to preload.ts and emusync.d.ts. Extend the `detect` return type with `install: { retroarch: {type,label,coresDir}[]; cores: {lib,folder}[] }`.
  - Files: src/gui/electron/preload.ts, src/gui/renderer/src/emusync.d.ts
  - Reuses: existing `emulator` preload namespace
- [ ] 4. Wizard state. `useConsoleImport.ts` stores `install` from both detect calls (initial auto-detect and `detectEmulators`), resets it on `backToConsole`, and exposes `installCore(coresDir, lib)`. That function calls the IPC and, on ok, calls `detectEmulators()` so the wizard advances; on failure it returns the error.
  - Files: src/gui/renderer/src/components/console-import/useConsoleImport.ts
  - Reuses: detectEmulators, existing setSuggestions pattern
- [ ] 5. Empty-state UI. In `EmulatorStep.tsx`, map each suggestion to a URL via a small keyword table (`RetroArch`, `mGBA`, `Dolphin`, `PCSX2`, `PPSSPP`, `Azahar`, `Eden`, `melonDS`, `Flycast`; first matching standalone keyword wins, else RetroArch) and render it as a link. When `install.retroarch` is non-empty, render an "Install a core" list: one row per core x RetroArch target (label includes "(Flatpak)" when there are two targets), each with an Install button, a per-row spinner and an inline error. When RetroArch is absent, show only the links.
  - Files: src/gui/renderer/src/components/console-import/EmulatorStep.tsx
  - Reuses: existing empty-state markup, `btn btn-ghost`, `spinner` class, window open handler
  - New: URL table. Suggestions are free-text strings in `console_defs` and changing that schema just for links is not worth it.
- [ ] 6. Tests: defined by /tplan.
- [ ] 7. Docs: ARCHITECTURE.md (new IPC `emulator:installCore`, detect `install` field, installCore.ts module); CLAUDE.md GUI rule line (core install: Linux x86_64 buildbot, validated against detected targets, `.part` + rename, zip via Python stdlib); design guide line from Design Alignment.
  - Files: src/docs/ARCHITECTURE.md, CLAUDE.md, .claude/frontend-design-guide.md

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (`emulator:installCore`). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Windows / non-x86_64 core install: GUI RetroArch detection is Linux-only and `.so`-only, so an installed `.dll` would not be detected. Links only. Needs Windows RetroArch detection first.
- Fetching `.info` files: seeded cores are detected by `.so` name alone (`findInstalledCores`), so `.info` is not needed.
- Standalone emulator install: #745.

## Log
